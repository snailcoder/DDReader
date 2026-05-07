"""大模型字段抽取器：按 6 大类别调用 LLM 抽取结构化信息"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

from . import config, utils
from .llm_client import AsyncLLMClient, LLMClient

CHUNK_MAX_CHARS = 120000  # 适配 256K 上下文窗口

# 字段类别到章节关键词的映射
FIELD_CHAPTER_MAPPING = {
    "issuer_profile": {
        "keywords": ["发行人基本情况", "概览", "业务与技术"],
        "is_object": True,
    },
    "ownership_structure": {
        "keywords": ["发行人基本情况", "公司治理与独立性", "概览"],
        "is_object": True,
    },
    "financials": {
        "keywords": ["财务会计信息", "业务与技术", "管理层分析"],
        "is_object": False,
    },
    "fund_raising_projects": {
        "keywords": ["募集资金运用", "投资者保护", "未来发展规划"],
        "is_object": False,
    },
    "risk_items": {
        "keywords": ["风险因素", "重大事项提示"],
        "is_object": False,
    },
    "compliance_items": {
        "keywords": ["其他重要事项", "公司治理与独立性", "投资者保护"],
        "is_object": False,
    },
}


class LLMExtractor:
    """封装 6 大字段类别的抽取逻辑"""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()
        self.async_client = None

    def _get_async_client(self) -> AsyncLLMClient:
        if self.async_client is None:
            self.async_client = AsyncLLMClient()
        return self.async_client

    def _merge_texts_for_field(self, chapter_texts: Dict[str, str],
                                field_category: str) -> str:
        """为特定字段合并相关章节的文本"""
        mapping = FIELD_CHAPTER_MAPPING.get(field_category, {})
        keywords = mapping.get("keywords", [])

        parts = []
        total = 0
        max_total = CHUNK_MAX_CHARS

        for chapter_name, chapter_info in chapter_texts.items():
            text = chapter_info.get("text", "")
            if not text:
                continue

            # 检查章节是否与字段相关
            is_relevant = any(kw in chapter_name for kw in keywords)
            if not is_relevant:
                continue

            part = f"\n=== {chapter_name} ===\n{text}"
            if total + len(part) > max_total:
                remaining = max_total - total
                if remaining > 100:
                    parts.append(part[:remaining] + "\n...[截断]")
                break
            parts.append(part)
            total += len(part)

        return "\n".join(parts)

    def _merge_evidence_for_field(self, chapter_texts: Dict[str, str],
                                   field_category: str) -> List[Dict]:
        """为特定字段合并相关章节的证据"""
        mapping = FIELD_CHAPTER_MAPPING.get(field_category, {})
        keywords = mapping.get("keywords", [])

        all_evidence = []
        for chapter_name, chapter_info in chapter_texts.items():
            is_relevant = any(kw in chapter_name for kw in keywords)
            if is_relevant:
                evidence = chapter_info.get("evidence", [])
                all_evidence.extend(evidence)

        return all_evidence

    def extract_all(self, chapter_texts: Dict[str, Dict]) -> Tuple[Dict[str, Any], Dict[str, List[Dict]]]:
        """抽取全部 6 类字段（同步版本）

        Args:
            chapter_texts: 章节文本映射

        Returns:
            (抽取结果, 证据映射)
        """
        results = {}
        evidence_map = {}

        for field_category in FIELD_CHAPTER_MAPPING:
            text = self._merge_texts_for_field(chapter_texts, field_category)
            evidence = self._merge_evidence_for_field(chapter_texts, field_category)

            results[field_category] = self._extract_single(field_category, text)
            evidence_map[field_category] = evidence

        return results, evidence_map

    async def extract_all_async(self, chapter_texts: Dict[str, Dict]) -> Tuple[Dict[str, Any], Dict[str, List[Dict]]]:
        """抽取全部 6 类字段（异步并发版本）

        Args:
            chapter_texts: 章节文本映射

        Returns:
            (抽取结果, 证据映射)
        """
        evidence_map = {}
        texts = {}

        for field_category in FIELD_CHAPTER_MAPPING:
            texts[field_category] = self._merge_texts_for_field(chapter_texts, field_category)
            evidence_map[field_category] = self._merge_evidence_for_field(chapter_texts, field_category)

        tasks = [
            self._extract_async(field_category, texts[field_category])
            for field_category in FIELD_CHAPTER_MAPPING
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = {}
        for field_category, result in zip(FIELD_CHAPTER_MAPPING.keys(), results):
            if isinstance(result, Exception):
                print(f"[LLM] {field_category} 抽取失败: {result}")
                mapping = FIELD_CHAPTER_MAPPING[field_category]
                processed[field_category] = None if mapping["is_object"] else []
            else:
                processed[field_category] = result

        return processed, evidence_map

    def _extract_single(self, field_category: str, text: str) -> Any:
        """对单一字段类别调用 LLM 抽取"""
        mapping = FIELD_CHAPTER_MAPPING.get(field_category, {})
        is_object = mapping.get("is_object", False)

        if not text or len(text.strip()) < 50:
            return None if is_object else []

        prompt_template = config.EXTRACTION_PROMPTS.get(field_category)
        if not prompt_template:
            return None if is_object else []

        chunks = utils.chunk_text(text, max_chars=CHUNK_MAX_CHARS)
        print(f"[LLM] 开始抽取: {field_category} | 文本长度: {len(text)} 字符 | chunk 数: {len(chunks)}")

        all_results = []

        for idx, chunk in enumerate(chunks):
            print(f"[LLM]   -> 调用 {field_category} chunk {idx + 1}/{len(chunks)} | {len(chunk)} 字符")
            prompt = prompt_template.replace("{chapter_text}", chunk)
            try:
                result = self.client.chat_json(prompt, system_prompt=config.SYSTEM_PROMPT)
            except Exception as e:
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 失败: {e}")
                continue

            if result is None:
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 返回空")
                continue

            if isinstance(result, list):
                all_results.extend(result)
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回列表 {len(result)} 条")
            elif isinstance(result, dict):
                all_results.append(result)
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回 dict")
            else:
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回类型: {type(result).__name__}")

        # 合并结果
        if is_object:
            for r in reversed(all_results):
                if r and isinstance(r, dict) and any(v not in (None, "", [], {}) for v in r.values()):
                    print(f"[LLM] {field_category} 抽取完成 | 合并后 1 个对象")
                    return r
            print(f"[LLM] {field_category} 抽取完成 | 无有效结果")
            return None

        # 列表型：去重
        seen = set()
        deduped = []
        for item in all_results:
            if not item:
                continue
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        print(f"[LLM] {field_category} 抽取完成 | 合并去重后 {len(deduped)} 条")
        return deduped

    async def _extract_async(self, field_category: str, text: str) -> Any:
        """异步单类别抽取"""
        mapping = FIELD_CHAPTER_MAPPING.get(field_category, {})
        is_object = mapping.get("is_object", False)

        if not text or len(text.strip()) < 50:
            return None if is_object else []

        prompt_template = config.EXTRACTION_PROMPTS.get(field_category)
        if not prompt_template:
            return None if is_object else []

        chunks = utils.chunk_text(text, max_chars=CHUNK_MAX_CHARS)
        print(f"[LLM] 开始抽取: {field_category} | 文本长度: {len(text)} 字符 | chunk 数: {len(chunks)}")

        async def extract_chunk(idx: int, chunk: str) -> Any:
            print(f"[LLM]   -> 调用 {field_category} chunk {idx + 1}/{len(chunks)} | {len(chunk)} 字符")
            prompt = prompt_template.replace("{chapter_text}", chunk)
            try:
                result = await self._get_async_client().chat_json_async(
                    prompt, system_prompt=config.SYSTEM_PROMPT, max_retries=3
                )
            except Exception as e:
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 失败: {e}")
                return None

            if result is None:
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 返回空")
                return None

            if isinstance(result, list):
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回列表 {len(result)} 条")
            elif isinstance(result, dict):
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回 dict")
            else:
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回类型: {type(result).__name__}")
            return result

        tasks = [extract_chunk(idx, chunk) for idx, chunk in enumerate(chunks)]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = [r for r in all_results if not isinstance(r, Exception) and r is not None]

        # 展平嵌套列表（与 _extract_single 保持一致）
        flattened = []
        for r in valid_results:
            if isinstance(r, list):
                flattened.extend(r)
            elif isinstance(r, dict):
                flattened.append(r)
        valid_results = flattened

        if is_object:
            for r in reversed(valid_results):
                if r and isinstance(r, dict) and any(v not in (None, "", [], {}) for v in r.values()):
                    print(f"[LLM] {field_category} 抽取完成 | 合并后 1 个对象")
                    return r
            print(f"[LLM] {field_category} 抽取完成 | 无有效结果")
            return None

        seen = set()
        deduped = []
        for item in valid_results:
            if not item:
                continue
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        print(f"[LLM] {field_category} 抽取完成 | 合并去重后 {len(deduped)} 条")
        return deduped

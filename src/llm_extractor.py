"""大模型字段抽取器：按 6 大类别调用 LLM 抽取结构化信息"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from . import config, utils
from .llm_client import AsyncLLMClient, LLMClient


CHUNK_MAX_CHARS = 120000  # 适配 256K 上下文窗口


class LLMExtractor:
    """封装 6 大字段类别的抽取逻辑"""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()
        self.async_client = None

    def _get_async_client(self) -> AsyncLLMClient:
        if self.async_client is None:
            self.async_client = AsyncLLMClient()
        return self.async_client

    def extract_all(self, chapter_texts: Dict[str, str]) -> Dict[str, Any]:
        """按章节映射，抽取全部 6 类字段（同步版本，串行执行）"""
        results = {}

        issuer_text = self._merge_texts(chapter_texts, ["发行人基本情况", "概览", "业务与技术", "未分类"])
        results["issuer_profile"] = self._extract_single("issuer_profile", issuer_text)

        ownership_text = self._merge_texts(chapter_texts, ["发行人基本情况", "公司治理与独立性", "概览"])
        results["ownership_structure"] = self._extract_single("ownership_structure", ownership_text)

        financial_text = self._merge_texts(chapter_texts, ["财务会计信息", "业务与技术"])
        results["financials"] = self._extract_single("financials", financial_text)

        fundraising_text = self._merge_texts(chapter_texts, ["募集资金运用", "投资者保护"])
        results["fund_raising_projects"] = self._extract_single("fund_raising_projects", fundraising_text)

        risk_text = self._merge_texts(chapter_texts, ["风险因素"])
        results["risk_items"] = self._extract_single("risk_items", risk_text)

        compliance_text = self._merge_texts(chapter_texts, ["其他重要事项", "公司治理与独立性", "投资者保护"])
        results["compliance_items"] = self._extract_single("compliance_items", compliance_text)

        return results

    async def extract_all_async(self, chapter_texts: Dict[str, str]) -> Dict[str, Any]:
        """按章节映射，抽取全部 6 类字段（异步并发版本）"""
        issuer_text = self._merge_texts(chapter_texts, ["发行人基本情况", "概览", "业务与技术", "未分类"])
        ownership_text = self._merge_texts(chapter_texts, ["发行人基本情况", "公司治理与独立性", "概览"])
        financial_text = self._merge_texts(chapter_texts, ["财务会计信息", "业务与技术"])
        fundraising_text = self._merge_texts(chapter_texts, ["募集资金运用", "投资者保护"])
        risk_text = self._merge_texts(chapter_texts, ["风险因素"])
        compliance_text = self._merge_texts(chapter_texts, ["其他重要事项", "公司治理与独立性", "投资者保护"])

        tasks = [
            self._extract_async("issuer_profile", issuer_text),
            self._extract_async("ownership_structure", ownership_text),
            self._extract_async("financials", financial_text),
            self._extract_async("fund_raising_projects", fundraising_text),
            self._extract_async("risk_items", risk_text),
            self._extract_async("compliance_items", compliance_text),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = {}
        keys = ["issuer_profile", "ownership_structure", "financials", "fund_raising_projects", "risk_items", "compliance_items"]
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                print(f"[LLM] {key} 抽取失败: {result}")
                processed[key] = None if key in {"issuer_profile", "ownership_structure"} else []
            else:
                processed[key] = result

        return processed

    def _merge_texts(self, chapter_texts: Dict[str, str], categories: List[str]) -> str:
        """合并多个类别的章节文本，总长度不超过限制"""
        parts = []
        total = 0
        max_total = 120000
        for cat in categories:
            text = chapter_texts.get(cat, "")
            if not text:
                continue
            part = f"\n=== {cat} ===\n{text}"
            if total + len(part) > max_total:
                remaining = max_total - total
                if remaining > 100:
                    parts.append(part[:remaining] + "\n...[截断]")
                break
            parts.append(part)
            total += len(part)
        return "\n".join(parts)

    async def extract_all_async(self, chapter_texts: Dict[str, str]) -> Dict[str, Any]:
        """按章节映射，抽取全部 6 类字段（异步并发版本）"""
        issuer_text = self._merge_texts(chapter_texts, ["发行人基本情况", "概览", "业务与技术", "未分类"])
        ownership_text = self._merge_texts(chapter_texts, ["发行人基本情况", "公司治理与独立性", "概览"])
        financial_text = self._merge_texts(chapter_texts, ["财务会计信息", "业务与技术"])
        fundraising_text = self._merge_texts(chapter_texts, ["募集资金运用", "投资者保护"])
        risk_text = self._merge_texts(chapter_texts, ["风险因素"])
        compliance_text = self._merge_texts(chapter_texts, ["其他重要事项", "公司治理与独立性", "投资者保护"])

        tasks = [
            self._extract_async("issuer_profile", issuer_text),
            self._extract_async("ownership_structure", ownership_text),
            self._extract_async("financials", financial_text),
            self._extract_async("fund_raising_projects", fundraising_text),
            self._extract_async("risk_items", risk_text),
            self._extract_async("compliance_items", compliance_text),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = {}
        keys = ["issuer_profile", "ownership_structure", "financials", "fund_raising_projects", "risk_items", "compliance_items"]
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                print(f"[LLM] {key} 抽取失败: {result}")
                processed[key] = None if key in {"issuer_profile", "ownership_structure"} else []
            else:
                processed[key] = result

        return processed

    def _merge_texts(self, chapter_texts: Dict[str, str], categories: List[str]) -> str:
        """合并多个类别的章节文本，总长度不超过限制"""
        parts = []
        total = 0
        max_total = 12000
        for cat in categories:
            text = chapter_texts.get(cat, "")
            if not text:
                continue
            part = f"\n=== {cat} ===\n{text}"
            if total + len(part) > max_total:
                remaining = max_total - total
                if remaining > 100:
                    parts.append(part[:remaining] + "\n...[截断]")
                break
            parts.append(part)
            total += len(part)
        return "\n".join(parts)

    def _extract_single(self, field_category: str, text: str) -> Any:
        """对单一字段类别调用 LLM 抽取"""
        if not text or len(text.strip()) < 50:
            # 文本过短，返回空值或空列表
            if field_category in {"issuer_profile", "ownership_structure"}:
                return None
            return []

        prompt_template = config.EXTRACTION_PROMPTS.get(field_category)
        if not prompt_template:
            return None

        # 如果文本太长，切分后分别抽取再合并（对列表型字段）
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

            # 统一处理返回格式
            if isinstance(result, list):
                all_results.extend(result)
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回列表 {len(result)} 条")
            elif isinstance(result, dict):
                all_results.append(result)
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回 dict")
            else:
                print(f"[LLM]   <- {field_category} chunk {idx + 1} 完成 | 返回类型: {type(result).__name__}")

        # 去重和合并
        if field_category in {"issuer_profile", "ownership_structure"}:
            # 对象型：取最后一个非空结果
            for r in reversed(all_results):
                if r and isinstance(r, dict) and any(v not in (None, "", [], {}) for v in r.values()):
                    print(f"[LLM] {field_category} 抽取完成 | 合并后 1 个对象")
                    return r
            print(f"[LLM] {field_category} 抽取完成 | 无有效结果")
            return None

        # 列表型：去重（简单按字符串化去重）
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
        if not text or len(text.strip()) < 50:
            if field_category in {"issuer_profile", "ownership_structure"}:
                return None
            return []

        prompt_template = config.EXTRACTION_PROMPTS.get(field_category)
        if not prompt_template:
            return None

        chunks = utils.chunk_text(text, max_chars=CHUNK_MAX_CHARS)
        print(f"[LLM] 开始抽取: {field_category} | 文本长度: {len(text)} 字符 | chunk 数: {len(chunks)}")

        async def extract_chunk(idx: int, chunk: str) -> Any:
            print(f"[LLM]   -> 调用 {field_category} chunk {idx + 1}/{len(chunks)} | {len(chunk)} 字符")
            prompt = prompt_template.replace("{chapter_text}", chunk)
            try:
                result = await self._get_async_client().chat_json_async(prompt, system_prompt=config.SYSTEM_PROMPT, max_retries=3)
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

        if field_category in {"issuer_profile", "ownership_structure"}:
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

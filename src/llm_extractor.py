"""大模型字段抽取器：按 6 大类别调用 LLM 抽取结构化信息"""

import json
from typing import Any, Dict, List, Optional

from . import config, utils
from .llm_client import LLMClient


class LLMExtractor:
    """封装 6 大字段类别的抽取逻辑"""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()

    def extract_all(self, chapter_texts: Dict[str, str]) -> Dict[str, Any]:
        """按章节映射，抽取全部 6 类字段

        Args:
            chapter_texts: {"发行人基本情况": "...", "风险因素": "...", ...}

        Returns:
            {"issuer_profile": {...}, "ownership_structure": {...}, ...}
        """
        results = {}

        # 1. 发行人基础信息 -> 概览 / 发行人基本情况
        issuer_text = self._merge_texts(chapter_texts, ["发行人基本情况", "概览", "业务与技术", "未分类"])
        results["issuer_profile"] = self._extract_single("issuer_profile", issuer_text)

        # 2. 股权结构 -> 发行人基本情况 / 公司治理
        ownership_text = self._merge_texts(chapter_texts, ["发行人基本情况", "公司治理与独立性", "概览"])
        results["ownership_structure"] = self._extract_single("ownership_structure", ownership_text)

        # 3. 财务指标 -> 财务会计信息
        financial_text = self._merge_texts(chapter_texts, ["财务会计信息", "业务与技术"])
        results["financials"] = self._extract_single("financials", financial_text)

        # 4. 募投项目 -> 募集资金运用
        fundraising_text = self._merge_texts(chapter_texts, ["募集资金运用", "投资者保护"])
        results["fund_raising_projects"] = self._extract_single("fund_raising_projects", fundraising_text)

        # 5. 风险事项 -> 风险因素
        risk_text = self._merge_texts(chapter_texts, ["风险因素"])
        results["risk_items"] = self._extract_single("risk_items", risk_text)

        # 6. 合规事项 -> 其他重要事项 / 公司治理
        compliance_text = self._merge_texts(chapter_texts, ["其他重要事项", "公司治理与独立性", "投资者保护"])
        results["compliance_items"] = self._extract_single("compliance_items", compliance_text)

        return results

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
        chunks = utils.chunk_text(text, max_chars=6000)
        all_results = []

        for chunk in chunks:
            prompt = prompt_template.format(chapter_text=chunk)
            try:
                result = self.client.chat_json(prompt, system_prompt=config.SYSTEM_PROMPT)
            except Exception as e:
                print(f"[警告] {field_category} 抽取失败: {e}")
                continue

            if result is None:
                continue

            # 统一处理返回格式
            if isinstance(result, list):
                all_results.extend(result)
            elif isinstance(result, dict):
                all_results.append(result)

        # 去重和合并
        if field_category in {"issuer_profile", "ownership_structure"}:
            # 对象型：取最后一个非空结果
            for r in reversed(all_results):
                if r and isinstance(r, dict) and any(v not in (None, "", [], {}) for v in r.values()):
                    return r
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
        return deduped

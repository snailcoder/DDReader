"""章节-字段映射器：根据实际 TOC 标题动态匹配字段类别

混合策略：
1. TOC 语义匹配：jieba 分词 + 字符包含性 + 词重叠（Jaccard）相似度
2. LLM 备选：当语义匹配置信度偏低时用一次 LLM 调用做章节-字段映射
3. 静态回退：全部失败时返回空字典，调用方使用 FIELD_CHAPTER_MAPPING
"""

import re
from typing import Dict, List, Optional

from . import config
from .llm_client import LLMClient

# 候选字段类别-关键词（供语义匹配，越丰富越好）
FIELD_KEYWORDS = {
    "issuer_profile": [
        "发行人基本情况", "概览", "发行人简介", "公司基本情况",
        "发行人概况", "发行人及中介机构", "发行概况",
    ],
    "ownership_structure": [
        "发行人基本情况", "公司治理", "股权结构", "控股股东",
        "实际控制人", "股东", "公司治理与独立性",
    ],
    "financials": [
        "财务会计信息", "管理层分析", "财务报表", "财务指标",
        "财务", "审计", "会计",
    ],
    "fund_raising_projects": [
        "募集资金运用", "募集资金", "募投", "未来发展规划",
        "投资者保护", "资金运用",
    ],
    "risk_items": [
        "风险因素", "重大事项提示", "风险提示", "风险",
    ],
    "compliance_items": [
        "其他重要事项", "公司治理", "诉讼", "仲裁",
        "处罚", "担保", "关联交易", "合规",
    ],
}

# 当前静态映射关键词（作为相似度计算的补充）
_STATIC_KEYWORDS = {
    "issuer_profile": ["发行人基本情况", "概览", "业务与技术"],
    "ownership_structure": ["发行人基本情况", "公司治理与独立性", "概览"],
    "financials": ["财务会计信息", "业务与技术", "管理层分析"],
    "fund_raising_projects": ["募集资金运用", "投资者保护", "未来发展规划"],
    "risk_items": ["风险因素", "重大事项提示"],
    "compliance_items": ["其他重要事项", "公司治理与独立性", "投资者保护"],
}

SIMILARITY_THRESHOLD = 0.3

# LLM 映射 Prompt（备选方案）
CHAPTER_MAPPING_SYSTEM_PROMPT = """你是一个文档结构分析专家。给定文档的章节标题列表和预定义的字段类别，请将每个章节映射到最适合的字段类别。

字段类别定义：
- issuer_profile: 发行人基础信息（公司名称、法定代表人、注册资本、注册地址等）
- ownership_structure: 股权与控制关系（控股股东、实际控制人、持股比例、一致行动关系）
- financials: 财务指标（营业收入、净利润、研发费用、资产负债等财务数据）
- fund_raising_projects: 募投项目信息（项目名称、投资总额、募集资金用途、建设周期）
- risk_items: 风险事项（风险因素标题、描述、类别、严重程度）
- compliance_items: 合规事项（行政处罚、诉讼仲裁、关联交易、对外担保）

只返回 JSON，不要多余文字。"""

CHAPTER_MAPPING_USER_PROMPT = """以下为文档的实际大章标题列表：
{chapter_list}

请将每个大章映射到最匹配的字段类别。没有匹配的字段类别设为空列表。

输出格式：{{"issuer_profile": ["章节标题1", ...], "ownership_structure": [...], ...}}"""

try:
    import jieba
except ImportError:
    jieba = None


def _tokenize(text: str) -> set:
    """分词；jieba 不可用时退化到汉字/英文/数字级切分"""
    if jieba:
        return set(jieba.lcut(text))
    tokens = set()
    for ch in text:
        if ch.strip():
            tokens.add(ch)
    return tokens


def _compute_similarity(chapter_heading: str, keywords: list) -> float:
    """计算章节标题与一组关键词的相似度（0-1）"""
    heading_clean = chapter_heading.replace(" ", "").replace("\u3000", "")
    max_score = 0.0

    for kw in keywords:
        kw_clean = kw.replace(" ", "").replace("\u3000", "")
        if not kw_clean:
            continue

        # 1. 关键词包含在标题中（最高权重）
        if kw_clean in heading_clean:
            containment = len(kw_clean) / max(len(heading_clean), 1)
            max_score = max(max_score, 0.6 + 0.4 * containment)
            continue

        # 2. 标题包含在关键词中
        if heading_clean in kw_clean:
            containment = len(heading_clean) / max(len(kw_clean), 1)
            max_score = max(max_score, 0.5 + 0.3 * containment)
            continue

        # 3. 词重叠（Jaccard）
        heading_tokens = _tokenize(heading_clean)
        kw_tokens = _tokenize(kw_clean)
        if heading_tokens and kw_tokens:
            intersection = heading_tokens & kw_tokens
            union = heading_tokens | kw_tokens
            jaccard = len(intersection) / max(len(union), 1)
            max_score = max(max_score, jaccard)

    return max_score


def build_mapping_from_toc(chapter_headings: list) -> Dict[str, list]:
    """基于 TOC 章节标题构建动态字段映射。

    Returns:
        {field_category: [chapter_heading, ...]} 或 {}（全部未匹配）
    """
    if not chapter_headings:
        return {}

    mapping = {}
    any_matched = False

    for field_cat in FIELD_KEYWORDS:
        all_keywords = list(set(FIELD_KEYWORDS[field_cat] + _STATIC_KEYWORDS.get(field_cat, [])))
        matched = [h for h in chapter_headings
                   if _compute_similarity(h, all_keywords) >= SIMILARITY_THRESHOLD]
        if matched:
            mapping[field_cat] = matched
            any_matched = True

    return mapping if any_matched else {}


def build_mapping_from_llm(chapter_headings: list, llm_client: LLMClient) -> Dict[str, list]:
    """用一次 LLM 调用构建章节-字段映射（备选方案）。"""
    if not chapter_headings or not llm_client:
        return {}

    chapter_list_str = "\n".join(f"- {h}" for h in chapter_headings)
    user_prompt = CHAPTER_MAPPING_USER_PROMPT.replace("{chapter_list}", chapter_list_str)

    try:
        result = llm_client.chat_json(user_prompt, system_prompt=CHAPTER_MAPPING_SYSTEM_PROMPT)
        if isinstance(result, dict):
            heading_set = set(chapter_headings)
            return {k: [h for h in v if h in heading_set]
                    for k, v in result.items() if isinstance(v, list)}
    except Exception as e:
        print(f"[ChapterMapper] LLM 映射失败: {e}")

    return {}


class ChapterMapper:
    """章节-字段映射器。

    用法:
        mapper = ChapterMapper(chapter_headings)
        mapping = mapper.build(llm_client=optional_llm)
        if not mapping:
            # fall back to static FIELD_CHAPTER_MAPPING
    """

    def __init__(self, chapter_headings: list):
        self.chapter_headings = chapter_headings

    @property
    def has_toc(self) -> bool:
        return len(self.chapter_headings) > 0

    def build(self, llm_client: LLMClient = None,
              avg_confidence_threshold: float = 0.5) -> Dict[str, list]:
        """执行混合策略映射。

        Args:
            llm_client: 可选，提供 LLM 备选
            avg_confidence_threshold: TOC 匹配平均置信度低于此值时触发 LLM

        Returns:
            {field_category: [chapter_heading, ...]} 或 {}（触发静态回退）
        """
        mapping = build_mapping_from_toc(self.chapter_headings)
        if not mapping:
            return {}

        avg_conf = self._avg_confidence(mapping)
        if avg_conf >= avg_confidence_threshold:
            return mapping

        if llm_client:
            print(f"[ChapterMapper] TOC 置信度 {avg_conf:.2f} < {avg_confidence_threshold}，尝试 LLM")
            llm_map = build_mapping_from_llm(self.chapter_headings, llm_client)
            if llm_map:
                return llm_map

        return mapping

    def _avg_confidence(self, mapping: Dict[str, list]) -> float:
        if not mapping:
            return 0.0
        scores = []
        for field_cat, headings in mapping.items():
            all_kw = list(set(FIELD_KEYWORDS.get(field_cat, [])
                              + _STATIC_KEYWORDS.get(field_cat, [])))
            for h in headings:
                scores.append(_compute_similarity(h, all_kw))
        return sum(scores) / max(len(scores), 1)

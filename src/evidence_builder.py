"""证据索引构建器：从原始 mineru block 构建 evidence_index，并为所有 6 类字段关联 source_evidence_id

优化点：
1. 证据去重：同一段原文共享一个 evidence_id（wiki 规范）
2. 内容感知关联：根据字段内容匹配最相关的 evidence，替代 round-robin
"""

import re
from typing import Any, Dict, List, Tuple

try:
    import jieba
except ImportError:
    jieba = None


def _tokenize(text: str) -> set:
    """分词；jieba 不可用时退化到字符级切分"""
    if jieba:
        return set(jieba.lcut(text))
    tokens = set()
    for ch in text:
        if ch.strip():
            tokens.add(ch)
    return tokens


def _find_bbox(raw_blocks_by_page: Dict[int, List[Dict]], page_idx: int, evidence_text: str) -> List[int]:
    """在原始 block 中查找与 evidence 文本匹配的 bbox（增强版：多策略匹配）"""
    if not evidence_text:
        return []
    blocks_on_page = raw_blocks_by_page.get(page_idx, [])
    if not blocks_on_page:
        return []

    evidence_prefix = evidence_text[:200].lower()

    # 策略 1：前缀精确匹配
    for block in blocks_on_page:
        block_text = block.get("text", "") or ""
        if not block_text and block.get("type") == "table":
            block_text = block.get("table_body", "") or ""
            block_text = re.sub(r"<[^>]+>", "", block_text)

        if not block_text:
            continue

        block_prefix = block_text[:200].lower()
        if block_prefix in evidence_prefix or evidence_prefix in block_prefix:
            bbox = block.get("bbox", [])
            if bbox:
                return bbox

    # 策略 2：关键词交集匹配
    evidence_tokens = _tokenize(evidence_text[:500])
    best_score = 0
    best_bbox = []
    for block in blocks_on_page:
        block_text = block.get("text", "") or ""
        if not block_text and block.get("type") == "table":
            block_text = block.get("table_body", "") or ""
            block_text = re.sub(r"<[^>]+>", "", block_text)
        if not block_text:
            continue
        block_tokens = _tokenize(block_text[:500])
        if not block_tokens or not evidence_tokens:
            continue
        intersection = evidence_tokens & block_tokens
        score = len(intersection) / max(len(evidence_tokens), 1)
        if score > best_score:
            best_score = score
            best_bbox = block.get("bbox", [])

    if best_bbox and best_score > 0.3:
        return best_bbox

    # 策略 3：回退到页面第一个 block
    first = blocks_on_page[0]
    return first.get("bbox", [])


def _quote_key(quote: str) -> str:
    """生成用于去重的 quote 特征键（前 200 字符，去除空白）"""
    if not quote:
        return ""
    normalized = re.sub(r"\s+", "", quote[:200])
    return normalized


def build_evidence_index(
    chapter_texts: Dict[str, Dict],
    raw_blocks_by_page: Dict[int, List[Dict]],
) -> Tuple[List[Dict], Dict[str, List[str]]]:
    """构建全局 evidence_index（带去重），返回 (evidence_index, chapter_to_ev_ids)

    去重规则：如果两个证据对象引用了同一段原文（前 200 字符相同），
    则共享同一个 evidence_id，在 evidence_index 中只出现一次。

    过滤规则：以 # 开头的 markdown 标题块不进入 evidence_index。

    Args:
        chapter_texts: extract_chapter_texts 的输出
        raw_blocks_by_page: page_idx -> [raw_block, ...]

    Returns:
        (evidence_index, chapter_to_ev_ids)
    """
    evidence_index = []
    chapter_to_ev_ids: Dict[str, List[str]] = {}
    ev_counter = 0
    # quote -> evidence_id 映射，用于去重
    quote_to_ev_id: Dict[str, str] = {}

    for chapter_name, chapter_info in chapter_texts.items():
        if chapter_name not in chapter_to_ev_ids:
            chapter_to_ev_ids[chapter_name] = []

        for evidence in chapter_info.get("evidence", []):
            page_idx = evidence.get("page_idx", 0)
            quote_text = evidence.get("text", "")
            quote = (quote_text or "")[:300]

            # 跳过标题块（以 # 开头的 markdown 标题行不属于正文）
            if quote_text.strip().startswith('#'):
                continue

            qkey = _quote_key(quote)

            # 去重：相同 quote 复用 evidence_id
            if qkey and qkey in quote_to_ev_id:
                evidence_id = quote_to_ev_id[qkey]
            else:
                ev_counter += 1
                evidence_id = f"ev_{ev_counter:04d}"
                if qkey:
                    quote_to_ev_id[qkey] = evidence_id

                bbox = _find_bbox(raw_blocks_by_page, page_idx, quote_text)

                entry = {
                    "evidence_id": evidence_id,
                    "page_no": page_idx + 1,
                    "chapter": chapter_name,
                    "block_type": evidence.get("block_type", "text"),
                    "quote": quote,
                    "bbox": bbox,
                }
                evidence_index.append(entry)

            chapter_to_ev_ids[chapter_name].append(evidence_id)

    return evidence_index, chapter_to_ev_ids


def _compute_text_similarity(text_a: str, text_b: str) -> float:
    """计算两段文本的相似度（基于关键词交集）"""
    if not text_a or not text_b:
        return 0.0
    tokens_a = _tokenize(text_a[:500])
    tokens_b = _tokenize(text_b[:500])
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / max(min(len(tokens_a), len(tokens_b)), 1)


def _find_best_evidence_for_item(
    item: Dict[str, Any],
    field_name: str,
    evidence_index: List[Dict],
    chapter_to_ev_ids: Dict[str, List[str]],
    field_chapter_keywords: Dict[str, List[str]],
) -> str:
    """为单个字段项找到最匹配的 evidence_id

    匹配策略：
    1. 根据字段内容（名称/标题/描述）在匹配章节的 evidence 中查找最相关条目
    2. 回退到所属章节的第一个 evidence_id
    3. 最后回退到全局第一个 evidence_id
    """
    keywords = field_chapter_keywords.get(field_name, [])

    # 收集匹配章节的所有 evidence
    candidate_evidence = []
    for chapter, ev_ids in chapter_to_ev_ids.items():
        if any(kw in chapter for kw in keywords):
            for ev_id in ev_ids:
                for ev in evidence_index:
                    if ev["evidence_id"] == ev_id:
                        candidate_evidence.append(ev)
                        break

    if not candidate_evidence:
        # 无匹配章节，回退到全局第一个
        return evidence_index[0]["evidence_id"] if evidence_index else None

    # 构建搜索文本：从 item 中提取最有辨识度的字段
    search_text = ""
    if field_name == "issuer_profile":
        search_text = item.get("issuer_name") or item.get("registered_address") or ""
    elif field_name == "ownership_structure":
        search_text = str(item.get("controlling_shareholder", ""))
    elif field_name == "financials":
        search_text = item.get("field_name") or item.get("field_scope") or ""
    elif field_name == "fund_raising_projects":
        search_text = item.get("project_name") or ""
    elif field_name == "risk_items":
        search_text = item.get("risk_title") or item.get("risk_description") or ""
    elif field_name == "compliance_items":
        # 优先用 description（包含具体案情/当事人等，辨识度最高）
        search_text = (item.get("description") or item.get("counter_party") or item.get("item_type") or "")[:300]

    if search_text:
        # 找最相关的 evidence
        best_ev = None
        best_score = 0.0
        for ev in candidate_evidence:
            score = _compute_text_similarity(search_text, ev.get("quote", ""))
            if score > best_score:
                best_score = score
                best_ev = ev
        if best_ev and best_score > 0.1:
            return best_ev["evidence_id"]

    # 回退：返回匹配章节的第一个 evidence
    return candidate_evidence[0]["evidence_id"] if candidate_evidence else None


def attach_evidence_ids(
    result: Dict[str, Any],
    evidence_index: List[Dict],
    chapter_to_ev_ids: Dict[str, List[str]],
) -> Dict[str, Any]:
    """为 result 中所有 6 类字段关联 source_evidence_id（内容感知版）

    对象型字段：分配所属章节的第一个 evidence_id
    列表型字段：根据每项内容匹配最相关的 evidence_id

    Args:
        result: 后处理后的结果 dict
        evidence_index: build_evidence_index 返回的证据列表
        chapter_to_ev_ids: 章节名 -> evidence_id 列表

    Returns:
        关联后的 result（原地修改）
    """
    field_chapter_keywords = {
        "issuer_profile": ["发行人基本情况", "概览"],
        "ownership_structure": ["发行人基本情况", "公司治理"],
        "financials": ["财务会计信息", "管理层分析"],
        "fund_raising_projects": ["募集资金运用", "未来发展规划"],
        "risk_items": ["风险因素", "重大事项提示"],
        "compliance_items": ["其他重要事项"],
    }

    def _get_ev_ids_for_field(field_name: str) -> List[str]:
        keywords = field_chapter_keywords.get(field_name, [])
        matched = []
        for chapter, ev_ids in chapter_to_ev_ids.items():
            if any(kw in chapter for kw in keywords):
                matched.extend(ev_ids)
        return matched

    # 对象型字段（issuer_profile, ownership_structure）
    # issuer_profile: 顶层赋值 source_evidence_id
    ev_ids = _get_ev_ids_for_field("issuer_profile")
    if ev_ids and isinstance(result.get("issuer_profile"), dict):
        result["issuer_profile"]["source_evidence_id"] = ev_ids[0]

    # ownership_structure: 不在顶层赋值，改为对子数组元素逐项关联
    ownership = result.get("ownership_structure")
    if isinstance(ownership, dict):
        for sub_field in ("controlling_shareholder", "actual_controller", "top_shareholders"):
            items = ownership.get(sub_field, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    ev_id = _find_best_evidence_for_item(
                        item, "ownership_structure", evidence_index,
                        chapter_to_ev_ids, field_chapter_keywords,
                    )
                    item["source_evidence_id"] = ev_id

    # 列表型字段：逐项内容匹配
    for list_field in ("financials", "fund_raising_projects", "risk_items", "compliance_items"):
        items = result.get(list_field, [])
        if not items:
            continue
        for item in items:
            if isinstance(item, dict):
                ev_id = _find_best_evidence_for_item(
                    item, list_field, evidence_index,
                    chapter_to_ev_ids, field_chapter_keywords,
                )
                item["source_evidence_id"] = ev_id

    return result


def prune_evidence_index(result: Dict[str, Any]) -> None:
    """移除 evidence_index 中未被任何字段引用的条目（原地修改）

    在 attach_evidence_ids 之后调用，只保留 source_evidence_id 实际指向的条目。
    """
    referenced: set = set()

    # issuer_profile（对象型）
    ip = result.get("issuer_profile")
    if isinstance(ip, dict) and ip.get("source_evidence_id"):
        referenced.add(ip["source_evidence_id"])

    # ownership_structure 子列表
    ownership = result.get("ownership_structure") or {}
    for sub_field in ("controlling_shareholder", "actual_controller", "top_shareholders"):
        for item in (ownership.get(sub_field) or []):
            if isinstance(item, dict) and item.get("source_evidence_id"):
                referenced.add(item["source_evidence_id"])

    # 列表型字段
    for list_field in ("financials", "fund_raising_projects", "risk_items", "compliance_items"):
        for item in (result.get(list_field) or []):
            if isinstance(item, dict) and item.get("source_evidence_id"):
                referenced.add(item["source_evidence_id"])

    before = len(result.get("evidence_index") or [])
    result["evidence_index"] = [
        ev for ev in (result.get("evidence_index") or [])
        if ev.get("evidence_id") in referenced
    ]
    after = len(result["evidence_index"])
    if before != after:
        print(f"[EvidenceBuilder] 移除未引用证据 {before - after} 条，保留 {after} 条")

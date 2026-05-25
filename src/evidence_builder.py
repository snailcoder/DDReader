"""证据索引构建器：从原始 mineru block 构建 evidence_index，并为所有 6 类字段关联 source_evidence_id"""

import re
from typing import Any, Dict, List, Tuple


def _find_bbox(raw_blocks_by_page: Dict[int, List[Dict]], page_idx: int, evidence_text: str) -> List[int]:
    """在原始 block 中查找与 evidence 文本匹配的 bbox"""
    if not evidence_text:
        return []
    blocks_on_page = raw_blocks_by_page.get(page_idx, [])
    if not blocks_on_page:
        return []

    evidence_prefix = evidence_text[:100].lower()

    for block in blocks_on_page:
        block_text = block.get("text", "") or ""
        if not block_text and block.get("type") == "table":
            block_text = block.get("table_body", "") or ""
            block_text = re.sub(r"<[^>]+>", "", block_text)

        if not block_text:
            continue

        block_prefix = block_text[:100].lower()
        if block_prefix in evidence_prefix or evidence_prefix in block_prefix:
            bbox = block.get("bbox", [])
            if bbox:
                return bbox

    first = blocks_on_page[0]
    return first.get("bbox", [])


def build_evidence_index(
    chapter_texts: Dict[str, Dict],
    raw_blocks_by_page: Dict[int, List[Dict]],
) -> Tuple[List[Dict], Dict[str, List[str]]]:
    """构建全局 evidence_index，返回 (evidence_index, chapter_to_ev_ids)

    Args:
        chapter_texts: extract_chapter_texts 的输出
        raw_blocks_by_page: page_idx -> [raw_block, ...]

    Returns:
        (evidence_index, chapter_to_ev_ids)
        - evidence_index: 全局证据列表，每条含 evidence_id/page_no/chapter/block_type/quote/bbox
        - chapter_to_ev_ids: 章节名 -> [evidence_id, ...] 映射
    """
    evidence_index = []
    chapter_to_ev_ids: Dict[str, List[str]] = {}
    ev_counter = 0

    for chapter_name, chapter_info in chapter_texts.items():
        if chapter_name not in chapter_to_ev_ids:
            chapter_to_ev_ids[chapter_name] = []

        for evidence in chapter_info.get("evidence", []):
            ev_counter += 1
            evidence_id = f"ev_{ev_counter:04d}"

            page_idx = evidence.get("page_idx", 0)
            bbox = _find_bbox(raw_blocks_by_page, page_idx, evidence.get("text", ""))

            entry = {
                "evidence_id": evidence_id,
                "page_no": page_idx + 1,
                "chapter": chapter_name,
                "block_type": evidence.get("block_type", "text"),
                "quote": (evidence.get("text") or "")[:300],
                "bbox": bbox,
            }
            evidence_index.append(entry)
            chapter_to_ev_ids[chapter_name].append(evidence_id)

    return evidence_index, chapter_to_ev_ids


def attach_evidence_ids(
    result: Dict[str, Any],
    evidence_index: List[Dict],
    chapter_to_ev_ids: Dict[str, List[str]],
) -> Dict[str, Any]:
    """为 result 中所有 6 类字段关联 source_evidence_id

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
        "compliance_items": ["其他重要事项", "公司治理与独立性"],
    }

    def _get_ev_ids_for_field(field_name: str) -> List[str]:
        keywords = field_chapter_keywords.get(field_name, [])
        matched = []
        for chapter, ev_ids in chapter_to_ev_ids.items():
            if any(kw in chapter for kw in keywords):
                matched.extend(ev_ids)
        return matched

    # 对象型字段（issuer_profile, ownership_structure）
    for obj_field in ("issuer_profile", "ownership_structure"):
        ev_ids = _get_ev_ids_for_field(obj_field)
        if ev_ids and isinstance(result.get(obj_field), dict):
            result[obj_field]["source_evidence_id"] = ev_ids[0]

    # 列表型字段
    for list_field in ("financials", "fund_raising_projects", "risk_items", "compliance_items"):
        ev_ids = _get_ev_ids_for_field(list_field)
        items = result.get(list_field, [])
        if not ev_ids or not items:
            continue
        for i, item in enumerate(items):
            if isinstance(item, dict):
                item["source_evidence_id"] = ev_ids[i % len(ev_ids)]

    return result

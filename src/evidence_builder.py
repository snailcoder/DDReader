"""证据索引构建器：为抽取字段关联 source_evidence_id 和 evidence_index"""

from typing import Any, Dict, List, Optional


def build_evidence_index(chapter_evidence: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """构建全局 evidence_index

    Args:
        chapter_evidence: {"发行人基本情况": [block_evidence, ...], ...}

    Returns:
        evidence_index 列表
    """
    evidence_index = []
    global_idx = 0

    for category, blocks in chapter_evidence.items():
        for block in blocks:
            global_idx += 1
            ev_id = f"ev_{global_idx:04d}"
            record = {
                "evidence_id": ev_id,
                "page_no": block.get("page_no"),
                "chapter": category,
                "block_type": block.get("type"),
                "quote": (block.get("text") or "")[:300],
                "bbox": block.get("bbox", []),
            }
            evidence_index.append(record)
            # 将 ev_id 写回 block 以便后续关联
            block["_evidence_id"] = ev_id

    return evidence_index


def attach_evidence_ids(result: Dict[str, Any], chapter_evidence: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """为结果中的每个字段附加 source_evidence_id

    策略：根据字段类别，从对应章节的 evidence 中选取第一条作为 source_evidence_id
    """
    category_map = {
        "issuer_profile": "发行人基本情况",
        "ownership_structure": "发行人基本情况",
        "financials": "财务会计信息",
        "fund_raising_projects": "募集资金运用",
        "risk_items": "风险因素",
        "compliance_items": "其他重要事项",
    }

    for field_key, cat in category_map.items():
        cat_blocks = chapter_evidence.get(cat, [])
        default_ev_id = cat_blocks[0].get("_evidence_id") if cat_blocks else None

        field_data = result.get(field_key)
        if isinstance(field_data, dict):
            field_data["source_evidence_id"] = default_ev_id
        elif isinstance(field_data, list):
            for idx, item in enumerate(field_data):
                if isinstance(item, dict):
                    # 尽量分散关联到不同的 evidence
                    if idx < len(cat_blocks):
                        item["source_evidence_id"] = cat_blocks[idx].get("_evidence_id")
                    else:
                        item["source_evidence_id"] = default_ev_id

    # 为 issuer_profile 内的子字段也关联
    issuer = result.get("issuer_profile", {})
    if isinstance(issuer, dict):
        issuer["source_evidence_id"] = default_ev_id

    return result

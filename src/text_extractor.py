"""文本提取器：按章节聚合 paragraph/table/list，附带页码和 bbox 证据"""

from typing import Any, Dict, List, Tuple

from . import utils


def _title_similar(a: str, b: str) -> bool:
    """简单判断两个标题是否相似"""
    a = a.replace(" ", "").replace("..", "").replace(".", "")
    b = b.replace(" ", "").replace("..", "").replace(".", "")
    if len(a) < 4 or len(b) < 4:
        return a == b
    return a[:min(len(a), len(b))] == b[:min(len(a), len(b))]


def extract_chapter_blocks(content_list_v2: List[Any], parsed_chapters: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """利用 content_list_v2 为每个章节聚合原始 block，保留证据信息

    Returns:
        {
            "发行人基本情况": [
                {"type": "paragraph", "text": "...", "page_no": 3, "bbox": [...]},
                {"type": "table", "html": "<table>...</table>", "caption": "...", "page_no": 3, "bbox": [...]},
                ...
            ],
            ...
        }
    """
    # 先建立 heading -> category 映射
    heading_category = {}
    for cat, info in parsed_chapters.get("chapters", {}).items():
        for t in info.get("titles", []):
            heading_category[t] = cat

    # 遍历 content_list_v2，为每个 block 判断所属章节
    chapter_blocks: Dict[str, List[Dict[str, Any]]] = {}
    current_category = "未分类"

    for page_idx, page_blocks in enumerate(content_list_v2):
        page_no = page_idx + 1
        for block in page_blocks:
            block_type = block.get("type", "unknown")

            # 如果 block 是 title，尝试更新当前章节
            if block_type == "title":
                title_text = _extract_block_text(block)
                matched_cat = None
                for h, cat in heading_category.items():
                    if h in title_text or title_text in h or _title_similar(h, title_text):
                        matched_cat = cat
                        break
                if matched_cat:
                    current_category = matched_cat

            # 跳过 page_header / page_number / page_footnote
            if block_type in {"page_header", "page_number", "page_footnote", "image"}:
                continue

            # 构建证据记录
            evidence = {
                "type": block_type,
                "page_no": page_no,
                "bbox": block.get("bbox", []),
            }

            if block_type == "table":
                evidence["html"] = block.get("content", {}).get("html", "")
                evidence["caption"] = _extract_caption(block)
                evidence["footnote"] = _extract_footnote(block)
                evidence["text"] = _html_to_text(evidence["html"])
            elif block_type == "paragraph":
                evidence["text"] = _extract_block_text(block)
            elif block_type == "list":
                evidence["text"] = _extract_block_text(block)
            elif block_type == "title":
                evidence["text"] = title_text
            else:
                evidence["text"] = _extract_block_text(block)

            cat = current_category
            if cat not in chapter_blocks:
                chapter_blocks[cat] = []
            chapter_blocks[cat].append(evidence)

    return chapter_blocks


def _extract_block_text(block: Dict[str, Any]) -> str:
    """从 block 中提取纯文本"""
    content = block.get("content", {})
    texts = []

    # title
    if "title_content" in content:
        for part in content["title_content"]:
            texts.append(part.get("content", ""))
    # paragraph / list
    elif "paragraph_content" in content:
        for part in content["paragraph_content"]:
            texts.append(part.get("content", ""))
    # 兜底
    else:
        texts.append(str(content))

    return "".join(texts).strip()


def _extract_caption(block: Dict[str, Any]) -> str:
    """提取表格标题"""
    caption_parts = block.get("content", {}).get("table_caption", [])
    return "".join(p.get("content", "") for p in caption_parts).strip()


def _extract_footnote(block: Dict[str, Any]) -> str:
    """提取表格脚注"""
    footnote_parts = block.get("content", {}).get("table_footnote", [])
    return "".join(p.get("content", "") for p in footnote_parts).strip()


def _html_to_text(html: str) -> str:
    """简单将 HTML table 转为可读文本"""
    import re
    text = re.sub(r"<tr>", "\n| ", html)
    text = re.sub(r"<td[^>]*>", "", text)
    text = re.sub(r"</td>", " | ", text)
    text = re.sub(r"<th[^>]*>", "", text)
    text = re.sub(r"</th>", " | ", text)
    text = re.sub(r"<table>|</table>|<tbody>|</tbody>|<thead>|</thead>|<tfoot>|</tfoot>|<colgroup>|</colgroup>|<col[^>]*/?>", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def build_chapter_text_with_evidence(chapter_blocks: List[Dict[str, Any]], max_chars: int = 15000) -> Tuple[str, List[Dict[str, Any]]]:
    """将章节 block 聚合为一段文本（保留表格 HTML），同时返回证据列表"""
    parts = []
    evidence_list = []
    total_len = 0

    for idx, block in enumerate(chapter_blocks):
        if block["type"] == "table" and block.get("html"):
            segment = f"\n[表格 {idx+1}]:\n{block['html']}\n"
            if block.get("caption"):
                segment = f"\n[表格 {idx+1} 标题: {block['caption']}]\n{block['html']}\n"
            if block.get("footnote"):
                segment += f"[表格 {idx+1} 脚注: {block['footnote']}]\n"
        else:
            segment = block.get("text", "")
            if segment:
                segment += "\n"

        if total_len + len(segment) > max_chars:
            parts.append("\n...[后续内容因长度限制已截断]")
            break

        parts.append(segment)
        total_len += len(segment)

        evidence_list.append({
            "evidence_id": f"ev_{idx:04d}",
            "page_no": block.get("page_no"),
            "chapter": "",  # 由调用方填充
            "block_type": block.get("type"),
            "quote": block.get("text", "")[:200],
            "bbox": block.get("bbox", []),
        })

    return "".join(parts), evidence_list

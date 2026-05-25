"""文本提取器：按章节聚合文本，保留页码信息

适配新的三级章节结构（大章 -> 小节 -> 子节）
"""

import re
from typing import Dict, List, Optional, Tuple

from . import utils
from .chapter_parser import get_section_text, get_chapter_text


def extract_section_blocks(section: Dict) -> List[Dict]:
    """提取小节中的文本块

    Args:
        section: 小节，包含 heading, page_idx, text_list, subsections

    Returns:
        文本块列表，每个块包含:
        - text: 文本内容
        - page_idx: 页码
        - block_type: 块类型 (text/table)
    """
    blocks = []

    # 处理子节
    subsections = section.get("subsections", [])
    if subsections:
        for sub in subsections:
            for item in sub.get("text_list", []):
                text = item.get("text", "")
                if text.strip():
                    # 检测是否包含表格
                    if "<table>" in text:
                        # 提取表格
                        tables = re.findall(r"<table>.*?</table>", text, re.DOTALL)
                        for table in tables:
                            blocks.append({
                                "text": table,
                                "page_idx": item.get("page_idx", 0),
                                "block_type": "table",
                            })
                        # 提取非表格文本
                        non_table_text = re.sub(r"<table>.*?</table>", "", text, flags=re.DOTALL).strip()
                        if non_table_text:
                            blocks.append({
                                "text": non_table_text,
                                "page_idx": item.get("page_idx", 0),
                                "block_type": "text",
                            })
                    else:
                        blocks.append({
                            "text": text,
                            "page_idx": item.get("page_idx", 0),
                            "block_type": "text",
                        })
    else:
        # 没有子节，直接使用 text_list
        for item in section.get("text_list", []):
            text = item.get("text", "")
            if text.strip():
                if "<table>" in text:
                    tables = re.findall(r"<table>.*?</table>", text, re.DOTALL)
                    for table in tables:
                        blocks.append({
                            "text": table,
                            "page_idx": item.get("page_idx", 0),
                            "block_type": "table",
                        })
                    non_table_text = re.sub(r"<table>.*?</table>", "", text, flags=re.DOTALL).strip()
                    if non_table_text:
                        blocks.append({
                            "text": non_table_text,
                            "page_idx": item.get("page_idx", 0),
                            "block_type": "text",
                        })
                else:
                    blocks.append({
                        "text": text,
                        "page_idx": item.get("page_idx", 0),
                        "block_type": "text",
                    })

    return blocks


def build_section_text_with_evidence(blocks: List[Dict],
                                     max_chars: int = 15000) -> Tuple[str, List[Dict]]:
    """将文本块聚合为一段文本，同时返回证据列表

    Args:
        blocks: 文本块列表
        max_chars: 最大字符数

    Returns:
        (聚合文本, 证据列表)
    """
    text_parts = []
    evidence_list = []
    current_len = 0

    for i, block in enumerate(blocks):
        text = block.get("text", "")
        if not text.strip():
            continue

        # 检查长度限制
        if current_len + len(text) > max_chars:
            break

        # 添加文本
        if block.get("block_type") == "table":
            text_parts.append(f"[表格 {i+1}]: {text}")
        else:
            text_parts.append(text)

        current_len += len(text)

        # 构建证据
        evidence_id = f"ev_{i:04d}"
        evidence_list.append({
            "evidence_id": evidence_id,
            "page_idx": block.get("page_idx", 0),
            "block_type": block.get("block_type", "text"),
            "text": text[:300],  # 只保留前300字作为引用
        })

    full_text = "\n\n".join(text_parts)
    return full_text, evidence_list


def extract_chapter_texts(parsed_chapters: Dict) -> Dict[str, Dict]:
    """从解析结果中提取各章节的文本

    Args:
        parsed_chapters: parse_chapters 的返回结果

    Returns:
        章节文本映射，格式:
        {
            "章节标题": {
                "text": "章节文本",
                "evidence": [...],
                "page_range": (start, end)
            }
        }
    """
    result = {}

    for chapter in parsed_chapters.get("chapters", []):
        chapter_heading = chapter.get("heading", "")

        # 遍历小节
        for section in chapter.get("sections", []):
            section_heading = section.get("heading", "")

            # 提取文本块
            blocks = extract_section_blocks(section)

            if not blocks:
                continue

            # 构建文本和证据
            text, evidence = build_section_text_with_evidence(blocks)

            if text.strip():
                # 使用大章标题作为key
                key = chapter_heading
                if key not in result:
                    result[key] = {
                        "text": "",
                        "evidence": [],
                        "page_range": (chapter.get("page_idx", 0), chapter.get("page_idx", 0)),
                    }

                result[key]["text"] += "\n\n" + text
                result[key]["evidence"].extend(evidence)

                # 更新页码范围
                if evidence:
                    max_page = max(e.get("page_idx", 0) for e in evidence)
                    result[key]["page_range"] = (
                        result[key]["page_range"][0],
                        max_page,
                    )

    return result

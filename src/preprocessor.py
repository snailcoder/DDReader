"""预处理模块：加载 content_list.json，过滤无关类型，按页合并为 markdown 格式"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# 需要过滤的 block 类型
SKIP_TYPES = {"image", "header", "footer", "page_number", "aside_text", "page_footnote"}


def find_content_list_file(input_dir: str) -> Optional[Path]:
    """在输入目录中查找 *_content_list.json 文件"""
    d = Path(input_dir)
    matches = list(d.glob("*_content_list.json"))
    if matches:
        return matches[0]
    # 也尝试查找 content_list.json
    cl_path = d / "content_list.json"
    if cl_path.exists():
        return cl_path
    return None


def load_content_list(input_dir: str) -> List[Dict]:
    """加载 content_list.json 文件"""
    cl_path = find_content_list_file(input_dir)
    if not cl_path:
        raise FileNotFoundError(f"在 {input_dir} 中未找到 content_list.json 文件")
    with open(cl_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _convert_text_level_to_markdown(text: str, text_level: Optional[int]) -> str:
    """根据 text_level 添加 markdown 标题标记"""
    if not text_level or text_level <= 0:
        return text
    prefix = "#" * text_level
    return f"{prefix} {text}"


def _merge_page_content(blocks: List[Dict]) -> str:
    """将同一页的多个 block 合并为 markdown 格式文本"""
    parts = []
    for block in blocks:
        block_type = block.get("type", "text")
        text = block.get("text", "").strip()

        if not text:
            continue

        # 处理标题
        if block_type == "text":
            text_level = block.get("text_level")
            text = _convert_text_level_to_markdown(text, text_level)

        # 处理表格（如果有的话）
        if block_type == "table":
            html = block.get("html", "")
            if html:
                text = html

        parts.append(text)

    return "\n\n".join(parts)


def preprocess(input_dir: str) -> List[Dict]:
    """预处理 content_list.json

    Args:
        input_dir: mineru 解析后的文档目录

    Returns:
        预处理后的页面列表，每个元素包含:
        - page_idx: 页码（从0开始）
        - text: 该页的 markdown 格式文本
    """
    content_list = load_content_list(input_dir)

    # 按 page_idx 分组
    pages: Dict[int, List[Dict]] = {}
    for block in content_list:
        # 跳过不需要的类型
        block_type = block.get("type", "text")
        if block_type in SKIP_TYPES:
            continue

        page_idx = block.get("page_idx", 0)
        if page_idx not in pages:
            pages[page_idx] = []
        pages[page_idx].append(block)

    # 按页码排序，合并每页内容
    result = []
    for page_idx in sorted(pages.keys()):
        blocks = pages[page_idx]
        text = _merge_page_content(blocks)
        if text.strip():  # 只保留有内容的页面
            result.append({
                "page_idx": page_idx,
                "text": text,
            })

    return result


def get_first_page_text(preprocessed: List[Dict]) -> str:
    """获取第一页的文本内容（用于文档分类）"""
    if not preprocessed:
        return ""
    return preprocessed[0].get("text", "")


def get_total_pages(preprocessed: List[Dict]) -> int:
    """获取总页数"""
    if not preprocessed:
        return 0
    return max(p["page_idx"] for p in preprocessed) + 1

"""章节解析器：恢复目录层级，按大章节切分正文"""

import re
from typing import Any, Dict, List, Optional, Tuple


def _extract_md_headings(md_text: str) -> List[Dict[str, Any]]:
    """从 full.md 中提取标题层级结构

    返回列表，每个元素：
        {"level": int, "title": str, "line_no": int}
    """
    headings = []
    for line_no, line in enumerate(md_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("# "):
            headings.append({"level": 1, "title": stripped[2:].strip(), "line_no": line_no})
        elif stripped.startswith("## "):
            headings.append({"level": 2, "title": stripped[3:].strip(), "line_no": line_no})
        elif stripped.startswith("### "):
            headings.append({"level": 3, "title": stripped[4:].strip(), "line_no": line_no})
        elif stripped.startswith("#### "):
            headings.append({"level": 4, "title": stripped[5:].strip(), "line_no": line_no})
    return headings


def _match_chapter_category(title: str) -> Optional[str]:
    """将标题匹配到预定义的章节类别"""
    from . import config

    title = title.strip()
    # 先尝试匹配 "第X节" 前缀
    for category, keywords in config.CHAPTER_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                return category
    return None


def parse_toc_and_chapters(md_text: str, content_list_v2: List[Any]) -> Dict[str, Any]:
    """解析目录并切分章节

    Returns:
        {
            "toc": [...],               # 目录树
            "chapters": {               # 按类别聚合的章节
                "发行人基本情况": {"titles": [...], "text": "...", "page_ranges": [(start,end),...]},
                "风险因素": {...},
                ...
            },
            "raw_headings": [...]       # 原始标题列表
        }
    """
    headings = _extract_md_headings(md_text)

    # 构建目录树
    toc_tree = []
    stack = []
    for h in headings:
        node = {"title": h["title"], "level": h["level"], "line_no": h["line_no"], "category": _match_chapter_category(h["title"]), "children": []}
        while stack and stack[-1]["level"] >= h["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            toc_tree.append(node)
        stack.append(node)

    # 按章节类别聚合内容
    lines = md_text.splitlines()
    chapters: Dict[str, Dict[str, Any]] = {}

    # 为每个 heading 计算其文本范围（从当前行到下一个同级或更高级标题）
    for i, h in enumerate(headings):
        category = _match_chapter_category(h["title"])
        if not category:
            # 尝试从父节点继承类别
            for j in range(i - 1, -1, -1):
                if headings[j]["level"] < h["level"]:
                    parent_cat = _match_chapter_category(headings[j]["title"])
                    if parent_cat:
                        category = parent_cat
                    break

        if not category:
            category = "未分类"

        start_line = h["line_no"]
        end_line = len(lines) + 1
        for j in range(i + 1, len(headings)):
            if headings[j]["level"] <= h["level"]:
                end_line = headings[j]["line_no"]
                break

        chapter_text = "\n".join(lines[start_line - 1:end_line - 1])

        if category not in chapters:
            chapters[category] = {"titles": [], "texts": [], "page_ranges": []}

        chapters[category]["titles"].append(h["title"])
        chapters[category]["texts"].append(chapter_text)

    # 合并同类章节文本
    for cat in chapters:
        chapters[cat]["text"] = "\n\n".join(chapters[cat]["texts"])

    # 尝试从 content_list_v2 获取页码范围
    _enrich_page_ranges(chapters, content_list_v2, headings)

    return {
        "toc": toc_tree,
        "chapters": chapters,
        "raw_headings": headings,
    }


def _enrich_page_ranges(chapters: Dict[str, Any], content_list_v2: List[Any], headings: List[Dict]) -> None:
    """利用 content_list_v2 的 page-level 结构，估算各章节的页码范围"""
    if not content_list_v2:
        return

    # content_list_v2 是 page -> [blocks] 的列表
    # 为每个 page 记录它包含的 title block 文本
    page_titles: List[List[str]] = []
    for page_idx, page_blocks in enumerate(content_list_v2):
        titles = []
        for block in page_blocks:
            if block.get("type") == "title":
                text_parts = block.get("content", {}).get("title_content", [])
                title_text = "".join(p.get("content", "") for p in text_parts)
                titles.append(title_text.strip())
        page_titles.append(titles)

    # 将 md heading 映射到 page
    heading_pages = {}
    for h in headings:
        ht = h["title"]
        for page_idx, titles in enumerate(page_titles):
            for pt in titles:
                # 允许一定模糊匹配
                if ht in pt or pt in ht or _title_similar(ht, pt):
                    heading_pages[ht] = page_idx + 1  # 页码从1开始
                    break
            if ht in heading_pages:
                break

    # 为每个 chapter 记录 page range
    for cat in chapters:
        pages = []
        for t in chapters[cat]["titles"]:
            if t in heading_pages:
                pages.append(heading_pages[t])
        if pages:
            chapters[cat]["page_range"] = (min(pages), max(pages))
        else:
            chapters[cat]["page_range"] = (None, None)


def _title_similar(a: str, b: str) -> bool:
    """简单判断两个标题是否相似"""
    a = a.replace(" ", "").replace("..", "").replace(".", "")
    b = b.replace(" ", "").replace("..", "").replace(".", "")
    if len(a) < 4 or len(b) < 4:
        return a == b
    return a[:min(len(a), len(b))] == b[:min(len(a), len(b))]


def get_chapter_text(parsed_chapters: Dict[str, Any], category: str, max_chars: int = 15000) -> str:
    """获取指定类别的章节文本，若太长则截断"""
    chapters = parsed_chapters.get("chapters", {})
    if category not in chapters:
        return ""
    text = chapters[category].get("text", "")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[内容过长已截断]"
    return text


def get_all_chapter_categories(parsed_chapters: Dict[str, Any]) -> List[str]:
    """获取所有识别到的章节类别"""
    return list(parsed_chapters.get("chapters", {}).keys())

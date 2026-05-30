"""章节解析器：解析目录、切分大章、小节、子节

实现抽取方法.md中描述的流程：
1. 解析目录：从预处理结果中找到目录页，提取大章和小节
2. 切分大章：按页码切分
3. 切分小节：页面分裂+页面重组
4. 切分子节：正则或模型识别子节标题
"""

import re
from typing import Dict, List, Optional, Tuple

# 常见大章标题关键词（用于校验目录解析结果）
COMMON_CHAPTER_KEYWORDS = [
    "释义", "概览", "本次发行概况", "风险因素", "发行人基本情况",
    "业务与技术", "财务会计信息", "募集资金运用", "投资者保护",
    "公司治理", "独立性", "其他重要事项", "声明", "附件",
    "管理层分析", "未来发展规划",
]

# 大章标题正则：第X节/第X章 + 标题
CHAPTER_HEADING_PATTERN = re.compile(
    r"第[一二三四五六七八九十百千\d]+[节章]\s*[、.]?\s*\S+"
)

# 小节标题正则：一、二、三、... 十、十一、...
SECTION_HEADING_PATTERN = re.compile(
    r"^[一二三四五六七八九十百千]+[、．.]\s*\S+"
)

# 子节标题正则（全角括号）：（一）（二）...
SUBSECTION_PATTERN_FULL = re.compile(
    r"^[（\(][一二三四五六七八九十百千\d]+[）\)]\s*\S+"
)

# 子节标题正则（半角括号+数字）：(1) (2) ...
SUBSECTION_PATTERN_NUM = re.compile(
    r"^[（\(]\d+[）\)]\s*\S+"
)


def _find_toc_pages(preprocessed: List[Dict]) -> List[int]:
    """找到目录所在页面

    目录开始处通常有"目 录"或"目录"等关键字
    """
    toc_pages = []
    in_toc = False

    for page in preprocessed:
        text = page["text"]
        page_idx = page["page_idx"]

        # 检测目录开始
        if re.search(r"#\s*目\s*录", text) or "目 录" in text or "目录" in text:
            in_toc = True

        if in_toc:
            toc_pages.append(page_idx)

            # 检测目录结束（遇到正文开始的标志）
            # 正文通常以"第一节"或"发行人声明"等开始
            if re.search(r"第[一二三四五六七八九十]+[节章]", text):
                # 检查是否是目录中的条目还是正文开始
                # 如果页面内容较少，可能是目录；如果内容较多，可能是正文
                if len(text) > 1000:
                    toc_pages.pop()  # 最后一页不是目录
                    break

    return toc_pages


def _parse_toc_content(preprocessed: List[Dict], toc_pages: List[int]) -> List[Dict]:
    """解析目录内容，提取大章和小节

    Returns:
        目录树，格式:
        [
            {
                "heading": "第一节 释义",
                "page_idx": 8,
                "sections": [
                    {"heading": "一、一般释义", "page_idx": 8},
                    ...
                ]
            },
            ...
        ]
    """
    # 合并目录页面内容
    toc_text = ""
    for page in preprocessed:
        if page["page_idx"] in toc_pages:
            toc_text += page["text"] + "\n"

    # 提取大章标题和页码
    chapters = []
    current_chapter = None

    lines = toc_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 尝试匹配大章标题
        # 格式1：第X节 标题 ... 页码
        # 格式2：第X节 标题...页码（点号连接）
        chapter_match = re.search(
            r"(第[一二三四五六七八九十百千\d]+[节章]\s*[、.]?\s*\S+?)[\s.．·\t]{1,}(\d+)",
            line
        )
        if not chapter_match:
            # 尝试另一种格式：标题后直接跟页码
            chapter_match = re.search(
                r"(第[一二三四五六七八九十百千\d]+[节章]\s*[、.]?\s*\S+?)\s+(\d+)$",
                line
            )
        
        if chapter_match:
            heading = chapter_match.group(1).strip()
            page_idx = int(chapter_match.group(2))

            # 校验：标题中应该包含常见关键词
            if any(kw in heading for kw in COMMON_CHAPTER_KEYWORDS):
                if current_chapter:
                    chapters.append(current_chapter)
                current_chapter = {
                    "heading": heading,
                    "page_idx": page_idx,
                    "sections": [],
                }
                continue

        # 尝试匹配小节标题
        # 格式：一、标题 ... 页码
        section_match = re.search(
            r"([一二三四五六七八九十百千]+[、．.]\s*\S+?)[\s.．·\t]{1,}(\d+)",
            line
        )
        if not section_match:
            # 尝试另一种格式：标题后直接跟页码
            section_match = re.search(
                r"([一二三四五六七八九十百千]+[、．.]\s*\S+?)\s+(\d+)$",
                line
            )
        
        if section_match and current_chapter:
            heading = section_match.group(1).strip()
            page_idx = int(section_match.group(2))
            current_chapter["sections"].append({
                "heading": heading,
                "page_idx": page_idx,
            })

    # 添加最后一个大章
    if current_chapter:
        chapters.append(current_chapter)

    return chapters


def _validate_toc(chapters: List[Dict]) -> bool:
    """验证目录解析结果是否合理

    页码允许相同或小幅跳跃，只拒绝明显倒退（差值 > 5）
    """
    if not chapters:
        return False

    # 检查页码是否基本递增（允许相同或小倒退，拒绝大幅倒退）
    prev_page = -1
    for ch in chapters:
        if ch["page_idx"] < prev_page - 5:
            return False
        prev_page = ch["page_idx"]

    # 检查是否有至少一个大章包含常见关键词
    has_valid_chapter = any(
        any(kw in ch["heading"] for kw in COMMON_CHAPTER_KEYWORDS)
        for ch in chapters
    )

    return has_valid_chapter


def parse_toc(preprocessed: List[Dict]) -> List[Dict]:
    """解析目录

    Args:
        preprocessed: 预处理后的页面列表

    Returns:
        目录树
    """
    toc_pages = _find_toc_pages(preprocessed)
    if not toc_pages:
        return []

    chapters = _parse_toc_content(preprocessed, toc_pages)

    if not _validate_toc(chapters):
        return []

    return chapters


def split_chapters(preprocessed: List[Dict], toc: List[Dict]) -> List[Dict]:
    """按页码切分大章

    Args:
        preprocessed: 预处理后的页面列表
        toc: 目录树

    Returns:
        大章列表，每个大章包含 page_list
    """
    if not toc:
        return []

    chapters = []
    for i, ch_info in enumerate(toc):
        start_page = ch_info["page_idx"]

        # 结束页码是下一个大章的开始页码
        if i + 1 < len(toc):
            end_page = toc[i + 1]["page_idx"]
        else:
            end_page = max(p["page_idx"] for p in preprocessed) + 1

        # 收集该大章的页面
        page_list = []
        for page in preprocessed:
            if start_page <= page["page_idx"] < end_page:
                page_list.append({
                    "text": page["text"],
                    "page_idx": page["page_idx"],
                })

        # 从页面内容中提取小节标题（如果目录中没有）
        sections_info = ch_info.get("sections", [])
        if not sections_info:
            sections_info = _extract_sections_from_content(page_list)

        chapters.append({
            "heading": ch_info["heading"],
            "page_idx": start_page,
            "page_list": page_list,
            "sections_info": sections_info,
        })

    return chapters


def _extract_sections_from_content(page_list: List[Dict]) -> List[Dict]:
    """从页面内容中提取小节标题

    小节标题格式：一、xxx 或 一、xxx
    """
    sections = []
    seen_headings = set()

    for page in page_list:
        text = page["text"]
        page_idx = page["page_idx"]

        # 匹配小节标题（带#前缀或不带）
        # 格式：# 一、xxx 或 一、xxx
        matches = re.finditer(
            r"(?:^|\n)#?\s*([一二三四五六七八九十百千]+[、．.]\s*\S+)",
            text
        )

        for match in matches:
            heading = match.group(1).strip()
            if heading not in seen_headings:
                seen_headings.add(heading)
                sections.append({
                    "heading": heading,
                    "page_idx": page_idx,
                })

    return sections


def _split_page_by_sections(page_text: str, page_idx: int,
                            section_headings: List[str]) -> List[Dict]:
    """页面分裂：根据小节标题将一个页面分裂为多个部分

    Args:
        page_text: 页面文本
        page_idx: 页码
        section_headings: 该大章内所有小节标题列表

    Returns:
        分裂后的文本片段列表，每个包含 text, text_level, page_idx
    """
    if not section_headings:
        return [{"text": page_text, "text_level": 0, "page_idx": page_idx}]

    # 构建匹配模式
    # 匹配 # 标题 或 标题（没有#前缀但以中文数字开头）
    parts = []
    last_end = 0

    # 在文本中查找所有小节标题的位置
    for heading in section_headings:
        # 尝试多种格式匹配
        patterns = [
            re.escape(f"# {heading}"),  # # 一、xxx
            re.escape(f"## {heading}"),  # ## 一、xxx
            re.escape(heading),  # 一、xxx
        ]

        for pattern in patterns:
            match = re.search(pattern, page_text[last_end:])
            if match:
                # 标题前的内容
                before_text = page_text[last_end:last_end + match.start()].strip()
                if before_text:
                    parts.append({
                        "text": before_text,
                        "text_level": 0,
                        "page_idx": page_idx,
                    })

                # 标题本身
                parts.append({
                    "text": match.group().strip(),
                    "text_level": 2,
                    "page_idx": page_idx,
                })

                last_end = last_end + match.end()
                break

    # 最后剩余的内容
    remaining = page_text[last_end:].strip()
    if remaining:
        parts.append({
            "text": remaining,
            "text_level": 0,
            "page_idx": page_idx,
        })

    return parts if parts else [{"text": page_text, "text_level": 0, "page_idx": page_idx}]


def split_sections(chapter: Dict) -> List[Dict]:
    """大章内部切分小节（页面分裂+页面重组）

    Args:
        chapter: 大章，包含 heading, page_idx, page_list, sections_info

    Returns:
        小节列表，每个小节包含 heading, page_idx, text_list
    """
    page_list = chapter.get("page_list", [])
    sections_info = chapter.get("sections_info", [])

    if not page_list:
        return []

    # 提取小节标题
    section_headings = [s["heading"] for s in sections_info]

    # 页面分裂
    split_pages = []
    for page in page_list:
        parts = _split_page_by_sections(
            page["text"], page["page_idx"], section_headings
        )
        split_pages.extend(parts)

    # 页面重组
    sections = []
    current_section = None

    for item in split_pages:
        if item["text_level"] == 2:
            # 遇到二级标题，开始新的小节
            if current_section:
                sections.append(current_section)
            current_section = {
                "heading": item["text"].lstrip("#").strip(),
                "page_idx": item["page_idx"],
                "text_list": [],
            }
        else:
            # 正文内容
            if current_section is None:
                # 标题前的内容，创建一个无标题的小节
                current_section = {
                    "heading": "",
                    "page_idx": item["page_idx"],
                    "text_list": [],
                }
            current_section["text_list"].append({
                "text": item["text"],
                "page_idx": item["page_idx"],
            })

    # 添加最后一个小节
    if current_section:
        sections.append(current_section)

    return sections


def _find_subsections_by_regex(text: str) -> List[Tuple[int, str]]:
    """用正则表达式查找子节标题

    Returns:
        [(位置, 标题文本), ...]
    """
    results = []
    seen_positions = set()

    # 匹配全角括号：（一）（二）...
    for match in re.finditer(r"[（\(][一二三四五六七八九十百千]+[）\)]\s*\S+", text):
        pos = match.start()
        if pos not in seen_positions:
            seen_positions.add(pos)
            results.append((pos, match.group().strip()))

    # 匹配半角括号+数字：(1) (2) ...
    for match in re.finditer(r"[（\(]\d+[）\)]\s*\S+", text):
        pos = match.start()
        if pos not in seen_positions:
            seen_positions.add(pos)
            results.append((pos, match.group().strip()))

    # 按位置排序
    results.sort(key=lambda x: x[0])
    return results


def _split_section_by_subsections(text_list: List[Dict],
                                   method: str = "regex") -> List[Dict]:
    """将小节切分为子节

    Args:
        text_list: 小节的文本列表
        method: 切分方法，"regex" 或 "model"

    Returns:
        子节列表
    """
    # 合并所有文本
    full_text = "\n".join(item["text"] for item in text_list)

    if method == "regex":
        # 用正则查找子节标题
        subsection_positions = _find_subsections_by_regex(full_text)
    else:
        # 模型方法（TODO: 实现模型识别）
        subsection_positions = _find_subsections_by_regex(full_text)

    if not subsection_positions:
        return []

    # 根据子节标题位置切分文本
    subsections = []
    for i, (pos, heading) in enumerate(subsection_positions):
        # 确定子节文本范围
        if i + 1 < len(subsection_positions):
            end_pos = subsection_positions[i + 1][0]
        else:
            end_pos = len(full_text)

        subsection_text = full_text[pos:end_pos].strip()

        # 确定该子节所在的页码
        # 简单方法：使用第一个 text_list 元素的页码
        page_idx = text_list[0]["page_idx"] if text_list else 0

        subsections.append({
            "heading": heading,
            "page_idx": page_idx,
            "text_list": [{"text": subsection_text, "page_idx": page_idx}],
        })

    return subsections


def split_subsections(section: Dict, method: str = "regex") -> Dict:
    """小节内部切分子节

    Args:
        section: 小节，包含 heading, page_idx, text_list
        method: 切分方法，"regex" 或 "model"

    Returns:
        添加了 subsections 字段的小节
    """
    text_list = section.get("text_list", [])

    if not text_list:
        section["subsections"] = []
        return section

    # 切分子节
    subsections = _split_section_by_subsections(text_list, method)
    section["subsections"] = subsections

    return section


def parse_chapters(preprocessed: List[Dict],
                   split_subsection_method: str = "regex") -> Dict:
    """完整的章节解析流程

    Args:
        preprocessed: 预处理后的页面列表
        split_subsection_method: 子节切分方法，"regex" 或 "model"

    Returns:
        解析结果，格式:
        {
            "chapters": [
                {
                    "heading": "第一节 释义",
                    "page_idx": 8,
                    "sections": [
                        {
                            "heading": "一、一般释义",
                            "page_idx": 8,
                            "text_list": [...],
                            "subsections": [...]
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    """
    # 1. 解析目录
    toc = parse_toc(preprocessed)

    if not toc:
        # 如果没有目录，尝试直接按标题切分
        return {"chapters": []}

    # 2. 切分大章
    chapters = split_chapters(preprocessed, toc)

    # 3. 切分小节和子节
    result_chapters = []
    for chapter in chapters:
        # 切分小节
        sections = split_sections(chapter)

        # 切分子节
        for section in sections:
            section = split_subsections(section, split_subsection_method)

        result_chapters.append({
            "heading": chapter["heading"],
            "page_idx": chapter["page_idx"],
            "sections": sections,
        })

    return {"chapters": result_chapters}


def get_section_text(section: Dict, max_chars: int = 15000) -> str:
    """获取小节的完整文本

    Args:
        section: 小节
        max_chars: 最大字符数

    Returns:
        合并后的文本
    """
    parts = []

    # 如果有子节，优先使用子节文本
    subsections = section.get("subsections", [])
    if subsections:
        for sub in subsections:
            for item in sub.get("text_list", []):
                parts.append(item["text"])
    else:
        # 使用小节文本
        for item in section.get("text_list", []):
            parts.append(item["text"])

    full_text = "\n\n".join(parts)

    # 截断
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars]

    return full_text


def get_chapter_text(chapter: Dict, max_chars: int = 15000) -> str:
    """获取大章的完整文本

    Args:
        chapter: 大章
        max_chars: 最大字符数

    Returns:
        合并后的文本
    """
    parts = []
    for section in chapter.get("sections", []):
        section_text = get_section_text(section)
        if section_text:
            parts.append(section_text)

    full_text = "\n\n".join(parts)

    # 截断
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars]

    return full_text


def find_chapters_by_keyword(parsed: Dict, keyword: str) -> List[Dict]:
    """根据关键词查找相关章节

    Args:
        parsed: parse_chapters 的返回结果
        keyword: 关键词

    Returns:
        匹配的章节列表
    """
    results = []
    for chapter in parsed.get("chapters", []):
        if keyword in chapter.get("heading", ""):
            results.append(chapter)
        for section in chapter.get("sections", []):
            if keyword in section.get("heading", ""):
                results.append(chapter)
                break
    return results

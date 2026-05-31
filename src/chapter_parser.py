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
        # 格式1：第X节 标题 ... 页码（点线或空格分隔）
        # 使用 .+? 而非 \S+? 以捕获完整多词标题（如"财务会计信息与管理层分析"）
        chapter_match = re.search(
            r"(第[一二三四五六七八九十百千\d]+[节章].+?)[\s.．·\t·　]{2,}(\d+)\s*$",
            line
        )
        if not chapter_match:
            chapter_match = re.search(
                r"(第[一二三四五六七八九十百千\d]+[节章].+?)\s{2,}(\d+)\s*$",
                line
            )
        if not chapter_match:
            # 最后兜底：标题后直接跟空格+页码结尾
            chapter_match = re.search(
                r"(第[一二三四五六七八九十百千\d]+[节章].+?)\s+(\d+)$",
                line
            )
        # 兜底2：页码缺失（mineru 未识别出页码），行中仅有"第X节 标题"加点线
        if not chapter_match:
            chapter_match_no_page = re.search(
                r"(第[一二三四五六七八九十百千\d]+[节章][^#\n]+?)[\s.．·　]*$",
                line
            )
        else:
            chapter_match_no_page = None

        if chapter_match:
            heading = chapter_match.group(1).strip()
            page_idx = int(chapter_match.group(2))
        elif chapter_match_no_page:
            heading = chapter_match_no_page.group(1).strip()
            # 去掉末尾残留的点线符号
            heading = re.sub(r"[\s.．·　]+$", "", heading)
            page_idx = 0  # 页码未知，置 0
        else:
            heading = None
            page_idx = None

        if heading is not None:
            # 校验：标题中应该包含常见关键词（对比前去除空格，兼容 OCR 字间空格）
            heading_compact = heading.replace(" ", "").replace("\u3000", "")
            if any(kw in heading_compact for kw in COMMON_CHAPTER_KEYWORDS):
                if current_chapter:
                    chapters.append(current_chapter)
                current_chapter = {
                    "heading": heading_compact if chapter_match_no_page else heading,
                    "page_idx": page_idx,
                    "sections": [],
                }
                continue

        # 尝试匹配小节标题
        # 格式：一、标题 ... 页码（同样用 .+? 捕获完整标题）
        section_match = re.search(
            r"([一二三四五六七八九十百千]+[、．.].+?)[\s.．·\t·　]{2,}(\d+)\s*$",
            line
        )
        if not section_match:
            section_match = re.search(
                r"([一二三四五六七八九十百千]+[、．.].+?)\s{2,}(\d+)\s*$",
                line
            )
        if not section_match:
            section_match = re.search(
                r"([一二三四五六七八九十百千]+[、．.].+?)\s+(\d+)$",
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

    # 先找出所有标题在文本中的实际位置，再按位置升序排列
    # 避免按 TOC 顺序迭代导致 last_end 游标跳过内容
    found: List[Tuple[int, int, str]] = []  # (start, end, matched_text)
    for heading in section_headings:
        patterns = [
            re.escape(f"# {heading}"),
            re.escape(f"## {heading}"),
            re.escape(heading),
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text)
            if match:
                found.append((match.start(), match.end(), match.group().strip()))
                break

    if not found:
        return [{"text": page_text, "text_level": 0, "page_idx": page_idx}]

    # 按文本位置升序排列（去除重叠，保留最早出现的）
    found.sort(key=lambda x: x[0])
    deduped: List[Tuple[int, int, str]] = []
    last_end = 0
    for start, end, matched in found:
        if start >= last_end:
            deduped.append((start, end, matched))
            last_end = end

    parts: List[Dict] = []
    prev_end = 0
    for start, end, matched in deduped:
        before = page_text[prev_end:start].strip()
        if before:
            parts.append({"text": before, "text_level": 0, "page_idx": page_idx})
        parts.append({"text": matched, "text_level": 2, "page_idx": page_idx})
        prev_end = end

    remaining = page_text[prev_end:].strip()
    if remaining:
        parts.append({"text": remaining, "text_level": 0, "page_idx": page_idx})

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
    if not text_list:
        return []

    # 构建字符偏移 → page_idx 的映射，确保每个子节使用正确的页码
    page_breaks: List[Tuple[int, int]] = []  # [(起始偏移, page_idx), ...]
    parts_for_join: List[str] = []
    offset = 0
    for item in text_list:
        t = item.get("text", "")
        page_breaks.append((offset, item.get("page_idx", 0)))
        parts_for_join.append(t)
        offset += len(t) + 1  # +1 对应 "\n" 分隔符

    full_text = "\n".join(parts_for_join)

    def _get_page_for_offset(pos: int) -> int:
        """根据字符位置找到对应的 page_idx"""
        page_idx = page_breaks[0][1] if page_breaks else 0
        for off, pidx in page_breaks:
            if pos >= off:
                page_idx = pidx
            else:
                break
        return page_idx

    if method == "regex":
        subsection_positions = _find_subsections_by_regex(full_text)
    else:
        subsection_positions = _find_subsections_by_regex(full_text)

    if not subsection_positions:
        return []

    # 根据子节标题位置切分文本，并为每个子节分配准确的页码
    subsections = []
    for i, (pos, heading) in enumerate(subsection_positions):
        if i + 1 < len(subsection_positions):
            end_pos = subsection_positions[i + 1][0]
        else:
            end_pos = len(full_text)

        subsection_text = full_text[pos:end_pos].strip()
        page_idx = _get_page_for_offset(pos)

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


def _fallback_chapter_split(preprocessed: List[Dict]) -> List[Dict]:
    """当 TOC 解析失败时，从正文中识别大章标题进行 fallback 切分

    识别策略：
    - mineru 产出的标题行带有 # 前缀（text_level > 0 → _convert_text_level_to_markdown 添加的）
    - 直接扫描 "第X节/章" 格式的行作为大章边界

    Returns:
        大章列表（结构与 split_chapters 输出一致，含 page_list）
    """
    if not preprocessed:
        return []

    # 匹配带或不带 # 前缀的大章标题行
    HEADING_RE = re.compile(
        r"(?:^|\n)#{0,3}\s*(第[一二三四五六七八九十百千\d]+[节章]\s*\S+[^\n]*)"
    )

    chapters: List[Dict] = []
    current_chapter: Optional[Dict] = None

    for page in preprocessed:
        text = page["text"]
        page_idx = page["page_idx"]

        matches = list(HEADING_RE.finditer(text))
        if not matches:
            if current_chapter is not None:
                current_chapter["page_list"].append({"text": text, "page_idx": page_idx})
            continue

        prev_pos = 0
        for match in matches:
            # 标题前的正文归属当前章
            before = text[prev_pos:match.start()].strip()
            if before and current_chapter is not None:
                current_chapter["page_list"].append({"text": before, "page_idx": page_idx})

            heading = match.group(1).strip()
            # 过滤掉明显是目录条目的行（含页码后缀且整行较短）
            if re.search(r"\d+\s*$", heading) and len(heading) < 50:
                heading = re.sub(r"[\s.．·　\d]+$", "", heading).strip()

            if current_chapter is not None:
                chapters.append(current_chapter)
            current_chapter = {
                "heading": heading,
                "page_idx": page_idx,
                "page_list": [],
                "sections_info": [],
            }
            prev_pos = match.end()

        # 标题后的正文归属当前章
        remaining = text[prev_pos:].strip()
        if remaining and current_chapter is not None:
            current_chapter["page_list"].append({"text": remaining, "page_idx": page_idx})

    if current_chapter is not None:
        chapters.append(current_chapter)

    return chapters


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
        # Fallback 1：从正文标题行切分章节
        print("[ChapterParser] TOC 解析失败，尝试正文标题 fallback...")
        fallback_chapters = _fallback_chapter_split(preprocessed)
        if fallback_chapters:
            print(f"[ChapterParser] Fallback 识别到 {len(fallback_chapters)} 个章节")
            result_chapters = []
            for chapter in fallback_chapters:
                sections = split_sections(chapter)
                for section in sections:
                    section = split_subsections(section, split_subsection_method)
                result_chapters.append({
                    "heading": chapter["heading"],
                    "page_idx": chapter["page_idx"],
                    "sections": sections,
                })
            return {"chapters": result_chapters}

        # Fallback 2：全文作为单一虚拟章节，至少能送 LLM 抽取
        print("[ChapterParser] 使用全文虚拟章节 fallback")
        all_pages = [{"text": p["text"], "page_idx": p["page_idx"]} for p in preprocessed]
        virtual_chapter = {
            "heading": "全文",
            "page_idx": preprocessed[0]["page_idx"] if preprocessed else 0,
            "page_list": all_pages,
            "sections_info": [],
        }
        sections = split_sections(virtual_chapter)
        for section in sections:
            section = split_subsections(section, split_subsection_method)
        return {"chapters": [{
            "heading": "全文",
            "page_idx": virtual_chapter["page_idx"],
            "sections": sections,
        }]}

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

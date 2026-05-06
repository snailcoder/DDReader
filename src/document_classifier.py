"""文档分类器：识别文档类型，判断是否跳过"""

from typing import Dict, List, Tuple

from . import config


def classify_document(first_page_text: str) -> Tuple[str, float]:
    """基于第一页内容识别文档类型

    Args:
        first_page_text: 预处理后的第一页文本内容

    Returns:
        doc_type: 文档类型字符串
        confidence: 置信度（0-1）
    """
    text = first_page_text[:3000]  # 只看前3000字符

    scores = {}
    for doc_type, keywords in config.DOC_TYPE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        scores[doc_type] = score / max(len(keywords), 1)

    # 取最高分
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    # 如果所有分数都为0，默认归为"其他"
    if best_score == 0:
        return "其他", 0.0

    return best_type, best_score


def classify_document_from_preprocessed(preprocessed: List[Dict]) -> Tuple[str, float]:
    """基于预处理结果的第一页进行分类

    Args:
        preprocessed: 预处理后的页面列表

    Returns:
        doc_type: 文档类型字符串
        confidence: 置信度（0-1）
    """
    if not preprocessed:
        return "其他", 0.0

    first_page_text = preprocessed[0].get("text", "")
    return classify_document(first_page_text)


def should_skip(doc_type: str) -> bool:
    """判断是否需要跳过（仅输出骨架 JSON）"""
    return doc_type in config.SKIP_DOC_TYPES

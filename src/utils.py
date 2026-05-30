"""通用工具函数：解析金额/日期/比例、文本清理等"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def infer_exchange_and_board_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """从文本中推断交易所和板块（新版，支持从预处理后的文本推断）

    Args:
        text: 文本内容（通常取前5000字符）

    Returns:
        (exchange, board)
    """
    text_upper = text[:5000].upper()

    exchange = None
    board = None

    if "科创板" in text_upper or "上海证券交易所科创板" in text_upper:
        exchange = "上交所"
        board = "科创板"
    elif "创业板" in text_upper or "深圳证券交易所创业板" in text_upper:
        exchange = "深交所"
        board = "创业板"
    elif "主板" in text_upper:
        if "上海" in text_upper[:2000]:
            exchange = "上交所"
        else:
            exchange = "深交所"
        board = "主板"
    elif "北交所" in text_upper or "北京证券交易所" in text_upper:
        exchange = "北交所"
        board = "北交所"
    elif "上交所" in text_upper or "上海证券交易所" in text_upper:
        exchange = "上交所"
    elif "深交所" in text_upper or "深圳证券交易所" in text_upper:
        exchange = "深交所"

    return exchange, board


def parse_amount(text: str) -> Optional[Dict[str, Any]]:
    """从文本中解析金额，拆分为 value / unit / currency

    支持的格式示例：
        46,565.64 万元
        139,875.00万元
        5,700.00 万元
        10,657,504.92 元
        人民币 17.52 元
        1亿元 / 1.2亿
        -1,234.56 万元
        不适用

    返回值 unit 始终为 schema 允许的枚举值（万元/元/%），亿元自动换算为万元。
    """
    if not text or text.strip() in {"不适用", "-", "—", "", "None", "null"}:
        return None

    text = text.strip()

    currency = "CNY"
    if "美元" in text or "USD" in text or "$" in text:
        currency = "USD"
    elif "港元" in text or "港币" in text or "HKD" in text or "HK$" in text:
        currency = "HKD"
    elif "欧元" in text or "EUR" in text:
        currency = "EUR"

    def _parse_number(s: str) -> Optional[float]:
        s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None

    def _new_amount(value: float, unit: str, currency: str) -> Dict[str, Any]:
        if unit == "亿元":
            value = value * 10000
            unit = "万元"
        return {"value": value, "unit": unit, "currency": currency}

    # 匹配带负号的金额: -1,234.56 万元 / 1亿元 / 1.2亿
    pattern = r"(-?[\d,]+\.?\d*)\s*(亿元|万元|万|元|万美元|万港元|万欧元|%)"
    match = re.search(pattern, text)
    if match:
        num_str = match.group(1)
        raw_unit = match.group(2)
        value = _parse_number(num_str)
        if value is not None:
            if raw_unit == "万":
                raw_unit = "万元"
            return _new_amount(value, raw_unit, currency)

    # 匹配 "约1.2亿"、"1亿" 等无"元"后缀的"亿"
    m2 = re.search(r"(-?[\d,]+\.?\d*)\s*亿(?!元)", text)
    if m2:
        value = _parse_number(m2.group(1))
        if value is not None:
            return _new_amount(value, "亿元", currency)

    # 兜底：文本中包含"元"或"万"字样
    if "元" in text or "万" in text:
        num_match = re.search(r"(-?[\d,]+\.?\d*)", text)
        if num_match:
            value = _parse_number(num_match.group(1))
            if value is not None:
                unit = "元" if "元" in text and "万" not in text else "万元"
                return {"value": value, "unit": unit, "currency": currency}

    return None


def parse_date(text: str) -> Optional[str]:
    """将中文日期统一解析为 YYYY-MM-DD

    支持格式：
        2026年1月30日 → 2026-01-30
        2025年6月11日 → 2025-06-11
        2026年3月     → 2026-03-01
        2026年        → 2026-01-01
    """
    if not text:
        return None

    text = text.strip()

    # 年月日
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        year, month, day = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    # 年月
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
    if m:
        year, month = m.groups()
        return f"{year}-{int(month):02d}-01"

    # 纯数字日期 2026-01-30 / 2026/01/30
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        year, month, day = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    # 年
    m = re.search(r"(\d{4})\s*年", text)
    if m:
        return f"{m.group(1)}-01-01"

    return None


def parse_ratio(text: str) -> Optional[float]:
    """将百分比或比例文本转换为标准小数

    支持：23.56% → 0.2356
          25.00%  → 0.25
          10.00   → 0.1 (假设是百分比)
    """
    if not text:
        return None

    text = text.strip().replace(",", "")

    # 明确带 %
    if "%" in text:
        num_match = re.search(r"([\d.]+)", text)
        if num_match:
            try:
                return round(float(num_match.group(1)) / 100, 6)
            except ValueError:
                return None

    # 纯数字，但文本中有"比例""占比"等关键词，可能是百分比
    if re.search(r"比例|占比|份额|比率", text):
        num_match = re.search(r"([\d.]+)", text)
        if num_match:
            val = float(num_match.group(1))
            if val > 1:  # 可能是百分比数值
                return round(val / 100, 6)
            return round(val, 6)

    return None


def clean_markdown_text(text: str) -> str:
    """清理 markdown 中的图片引用、多余空行等"""
    # 去除图片引用 ![](...)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # 去除 markdown 链接，保留文本
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_tables_from_md(md_text: str) -> List[str]:
    """从 markdown 文本中提取所有 <table> HTML 片段"""
    tables = re.findall(r"<table>.*?</table>", md_text, re.DOTALL)
    return tables


def chunk_text(text: str, max_chars: int = 6000) -> List[str]:
    """将长文本切分为多个 chunk，优先在段落边界切分"""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current:
        chunks.append(current.strip())
    return chunks


def infer_stock_code(text: str) -> Optional[str]:
    """从文本中提取股票代码

    匹配规则：在"股票代码""证券代码""代码"等关键词后查找 6 位数字，
    可能带 .SH/.SZ/.BJ 后缀。
    """
    if not text:
        return None

    keywords = r"(?:股票代码|证券代码|A股代码|代码|股票简称)"
    patterns = [
        rf"{keywords}\s*[：:]\s*(\d{{6}})(?:\.(SH|SZ|BJ))?",
        rf"{keywords}\s*[：:]\s*(\d{{6}})",
        rf"(\d{{6}})\.(SH|SZ|BJ)",
    ]

    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            code = m.group(1)
            suffix = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            return f"{code}.{suffix}" if suffix else code

    return None


def build_document_id_from_dir(input_dir: str) -> str:
    """从目录中 content_list 文件名提取 document_id，保持与 content_list 前缀一致"""
    d = Path(input_dir)
    matches = list(d.glob("*_content_list.json"))
    if matches:
        # 取第一个匹配，去掉 _content_list.json 后缀
        return matches[0].stem.removesuffix("_content_list")
    return os.path.basename(os.path.normpath(input_dir))

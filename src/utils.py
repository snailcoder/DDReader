"""通用工具函数：读取 mineru 输出、解析金额/日期/比例、文本清理等"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_mineru_data(input_dir: str) -> Dict[str, Any]:
    """加载 mineru 解析后的全部数据文件

    Returns dict with keys: full_md, content_list_v2, layout_json
    """
    d = Path(input_dir)
    data = {}

    full_md_path = d / "full.md"
    if full_md_path.exists():
        with open(full_md_path, "r", encoding="utf-8") as f:
            data["full_md"] = f.read()
    else:
        data["full_md"] = ""

    clv2_path = d / "content_list_v2.json"
    if clv2_path.exists():
        with open(clv2_path, "r", encoding="utf-8") as f:
            data["content_list_v2"] = json.load(f)
    else:
        data["content_list_v2"] = []

    layout_path = d / "layout.json"
    if layout_path.exists():
        with open(layout_path, "r", encoding="utf-8") as f:
            data["layout_json"] = json.load(f)
    else:
        data["layout_json"] = {}

    return data


def parse_amount(text: str) -> Optional[Dict[str, Any]]:
    """从文本中解析金额，拆分为 value / unit / currency

    支持的格式示例：
        46,565.64 万元
        139,875.00万元
        5,700.00 万元
        10,657,504.92 元
        人民币 17.52 元
        不适用
    """
    if not text or text.strip() in {"不适用", "-", "—", "", "None", "null"}:
        return None

    text = text.strip()

    # 先尝试提取币种
    currency = "CNY"
    if "美元" in text or "USD" in text or "$" in text:
        currency = "USD"
    elif "港元" in text or "港币" in text or "HKD" in text or "HK$" in text:
        currency = "HKD"
    elif "欧元" in text or "EUR" in text:
        currency = "EUR"
    elif "人民币" in text or "元" in text:
        currency = "CNY"

    # 匹配数值 + 单位
    # 支持 1,234.56 或 1234.56 或 1,234
    pattern = r"([\d,]+\.?\d*)\s*(万元|亿元|元|万美元|万港元|万欧元|%)"
    match = re.search(pattern, text)
    if match:
        num_str = match.group(1).replace(",", "")
        unit = match.group(2)
        try:
            value = float(num_str)
        except ValueError:
            return None
        return {"value": value, "unit": unit, "currency": currency}

    # 兜底：如果文本中包含"元"或"万"等字样，但没有被上面匹配到，尝试只取数字
    if "元" in text or "万" in text:
        num_match = re.search(r"([\d,]+\.?\d*)", text)
        if num_match:
            num_str = num_match.group(1).replace(",", "")
            try:
                value = float(num_str)
            except ValueError:
                return None
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


def build_document_id_from_dir(input_dir: str) -> str:
    """从目录名提取 document_id"""
    return os.path.basename(os.path.normpath(input_dir))


def sanitize_json_string(raw: str) -> str:
    """清理模型返回的 JSON 字符串（去除 markdown 代码块标记等）"""
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    return raw.strip()


def infer_exchange_and_board(md_text: str) -> Tuple[Optional[str], Optional[str]]:
    """从文本中推断交易所和板块"""
    text_upper = md_text[:5000].upper()

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

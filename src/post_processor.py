"""后处理器：金额拆分、日期格式化、比例标准化、基础校验"""

import json
import re
from typing import Any, Dict, List, Optional

from . import utils


# exchange 和 board 的枚举值映射
_EXCHANGE_MAP = {
    "上海证券交易所": "上交所",
    "深圳证券交易所": "深交所",
    "北京证券交易所": "北交所",
    "上交所": "上交所",
    "深交所": "深交所",
    "北交所": "北交所",
}

_BOARD_MAP = {
    "主板": "主板",
    "创业板": "创业板",
    "科创板": "科创板",
    "北交所": "北交所",
}

# 公司名称后缀，用于生成 issuer_name_normalized
_SUFFIXES = ["股份有限公司", "有限责任公司", "有限公司", "公司"]


def _normalize_issuer_name(name: str) -> Optional[str]:
    """从公司全称去除后缀，生成规范化简称"""
    if not name:
        return None
    for suffix in _SUFFIXES:
        if name.endswith(suffix):
            normalized = name[: -len(suffix)]
            return normalized if normalized else None
    return None


def process_issuer_profile(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """后处理发行人基础信息"""
    if not raw or not isinstance(raw, dict):
        return {
            "issuer_name": None,
            "issuer_name_normalized": None,
            "stock_code": None,
            "exchange": None,
            "board": None,
            "legal_representative": None,
            "establishment_date": None,
            "registered_capital": {"value": None, "unit": "万元", "currency": "CNY"},
            "registered_address": None,
            "industry": None,
            "main_business": None,
            "source_evidence_id": None,
        }

    result = {k: raw.get(k) for k in [
        "issuer_name", "issuer_name_normalized", "stock_code",
        "exchange", "board", "legal_representative",
        "registered_address", "industry", "main_business", "source_evidence_id"
    ]}

    # 日期
    est_date = raw.get("establishment_date")
    if isinstance(est_date, str):
        parsed = utils.parse_date(est_date)
        result["establishment_date"] = parsed or est_date
    else:
        result["establishment_date"] = est_date

    # 注册资本
    cap = raw.get("registered_capital")
    if isinstance(cap, dict):
        result["registered_capital"] = {
            "value": _to_float(cap.get("value")),
            "unit": cap.get("unit") or "万元",
            "currency": cap.get("currency") or "CNY",
        }
    elif isinstance(cap, str):
        parsed = utils.parse_amount(cap)
        result["registered_capital"] = parsed or {"value": None, "unit": "万元", "currency": "CNY"}
    else:
        result["registered_capital"] = {"value": None, "unit": "万元", "currency": "CNY"}

    # issuer_name_normalized fallback：从 issuer_name 自动生成
    if not result.get("issuer_name_normalized") and result.get("issuer_name"):
        result["issuer_name_normalized"] = _normalize_issuer_name(result["issuer_name"])

    # exchange 枚举映射
    exchange_raw = result.get("exchange")
    if exchange_raw and exchange_raw in _EXCHANGE_MAP:
        result["exchange"] = _EXCHANGE_MAP[exchange_raw]
    elif exchange_raw and exchange_raw not in ("上交所", "深交所", "北交所"):
        # 尝试模糊匹配
        for key, val in _EXCHANGE_MAP.items():
            if key in exchange_raw:
                result["exchange"] = val
                break

    # board 枚举映射
    board_raw = result.get("board")
    if board_raw and board_raw in _BOARD_MAP:
        result["board"] = _BOARD_MAP[board_raw]
    elif board_raw and board_raw not in ("主板", "创业板", "科创板", "北交所"):
        for key, val in _BOARD_MAP.items():
            if key in board_raw:
                result["board"] = val
                break

    return result


def process_ownership_structure(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """后处理股权结构"""
    if not raw or not isinstance(raw, dict):
        return {
            "controlling_shareholder": [],
            "actual_controller": [],
            "concerted_action_flag": False,
            "top_shareholders": [],
        }

    result = {
        "controlling_shareholder": _process_shareholder_list(raw.get("controlling_shareholder", [])),
        "actual_controller": _process_controller_list(raw.get("actual_controller", [])),
        "concerted_action_flag": bool(raw.get("concerted_action_flag", False)),
        "top_shareholders": _process_shareholder_list(raw.get("top_shareholders", [])),
    }
    return result


def _process_shareholder_list(items: List[Any]) -> List[Dict[str, Any]]:
    """处理股东/前十大股东列表"""
    if not items:
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ratio = item.get("shareholding_ratio")
        if isinstance(ratio, dict):
            ratio = _to_float(ratio.get("value"))
        elif isinstance(ratio, str):
            ratio = utils.parse_ratio(ratio)
        elif isinstance(ratio, (int, float)):
            if ratio > 1:
                ratio = round(ratio / 100, 6)
        result.append({
            "name": item.get("name") or None,
            "shareholding_ratio": ratio,
            "direct_or_indirect": item.get("direct_or_indirect") or None,
            "rank": item.get("rank") or None,
            "source_evidence_id": item.get("source_evidence_id") or None,
        })
    return result


def _process_controller_list(items: List[Any]) -> List[Dict[str, Any]]:
    """处理实际控制人列表"""
    if not items:
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        result.append({
            "name": item.get("name") or None,
            "control_type": item.get("control_type") or None,
            "source_evidence_id": item.get("source_evidence_id") or None,
        })
    return result


def process_financials(raw: Any) -> List[Dict[str, Any]]:
    """后处理财务指标列表"""
    raw = _coerce_to_list(raw)
    if not raw:
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        processed = {
            "field_name": item.get("field_name") or None,
            "field_scope": item.get("field_scope") or None,
            "chapter": item.get("chapter") or None,
            "source_evidence_id": item.get("source_evidence_id") or None,
        }

        # period
        period = item.get("period")
        if isinstance(period, str):
            parsed = utils.parse_date(period)
            processed["period"] = parsed or period
        else:
            processed["period"] = period

        # value + unit
        val = item.get("value")
        if isinstance(val, dict):
            val = _to_float(val.get("value"))
        unit = item.get("unit") or "万元"
        currency = item.get("currency") or "CNY"

        if isinstance(val, str):
            # 尝试解析金额
            amount_parsed = utils.parse_amount(val)
            if amount_parsed:
                processed["value"] = amount_parsed["value"]
                processed["unit"] = amount_parsed["unit"]
                processed["currency"] = amount_parsed["currency"]
            else:
                # 尝试解析纯数字
                num = _to_float(val)
                processed["value"] = num
                processed["unit"] = unit
                processed["currency"] = currency
        elif isinstance(val, (int, float)):
            processed["value"] = val
            processed["unit"] = unit
            processed["currency"] = currency
        else:
            processed["value"] = None
            processed["unit"] = unit
            processed["currency"] = currency

        result.append(processed)
    return result


def process_fund_raising_projects(raw: Any) -> List[Dict[str, Any]]:
    """后处理募投项目列表"""
    raw = _coerce_to_list(raw)
    if not raw:
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append({
            "project_name": item.get("project_name") or None,
            "project_type": item.get("project_type") or "其他",
            "total_investment": _process_amount_field(item.get("total_investment")),
            "planned_use_of_raised_funds": _process_amount_field(item.get("planned_use_of_raised_funds")),
            "construction_period": item.get("construction_period") or None,
            "implementation_entity": item.get("implementation_entity") or None,
            "source_evidence_id": item.get("source_evidence_id") or None,
        })
    return result


def process_risk_items(raw: Any) -> List[Dict[str, Any]]:
    """后处理风险事项列表"""
    raw = _coerce_to_list(raw)
    if not raw:
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append({
            "risk_title": item.get("risk_title") or None,
            "risk_category": item.get("risk_category") or "其他",
            "risk_description": item.get("risk_description") or None,
            "severity_level": item.get("severity_level") or "中",
            "source_evidence_id": item.get("source_evidence_id") or None,
        })
    return result


def process_compliance_items(raw: Any) -> List[Dict[str, Any]]:
    """后处理合规事项列表"""
    raw = _coerce_to_list(raw)
    if not raw:
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append({
            "item_type": item.get("item_type") or "其他",
            "counter_party": item.get("counter_party") or None,
            "occurrence_date": utils.parse_date(item.get("occurrence_date")) if item.get("occurrence_date") else None,
            "amount": _process_amount_field(item.get("amount")),
            "description": item.get("description") or None,
            "period": utils.parse_date(item.get("period")) if item.get("period") else None,
            "source_evidence_id": item.get("source_evidence_id") or None,
        })
    return result


def _process_amount_field(raw: Any) -> Optional[Dict[str, Any]]:
    """通用处理金额字段"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        value = _to_float(raw.get("value"))
        unit = raw.get("unit") or "万元"
        if unit == "亿元":
            if value is not None:
                value = value * 10000
            unit = "万元"
        return {
            "value": value,
            "unit": unit,
            "currency": raw.get("currency") or "CNY",
        }
    if isinstance(raw, str):
        parsed = utils.parse_amount(raw)
        if parsed:
            return parsed
        num = _to_float(raw)
        if num is not None:
            return {"value": num, "unit": "万元", "currency": "CNY"}
    if isinstance(raw, (int, float)):
        return {"value": float(raw), "unit": "万元", "currency": "CNY"}
    return None


def _coerce_to_list(val: Any) -> list:
    """将非 list 输入（dict / None 等）安全转为 list，防止迭代 dict keys"""
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return [val]
    return []


def _to_float(val: Any) -> Optional[float]:
    """安全转换为 float"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.strip().replace(",", "")
        # "1亿元" -> 10000.0, "1万元" -> 1.0
        yi_match = re.search(r"([\d.]+)\s*亿元?", s)
        if yi_match:
            try:
                return float(yi_match.group(1)) * 10000
            except ValueError:
                return None
        wan_match = re.search(r"([\d.]+)\s*万", s)
        if wan_match and "亿" not in s:
            try:
                return float(wan_match.group(1))
            except ValueError:
                return None
        s = re.sub(r"[元%]", "", s).strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def validate_result(result: Dict[str, Any]) -> List[str]:
    """基础业务校验，返回错误/警告列表"""
    warnings = []

    # 1. 募投金额汇总校验
    projects = result.get("fund_raising_projects", [])
    total_planned = 0.0
    for p in projects:
        amt = p.get("planned_use_of_raised_funds", {})
        if amt and amt.get("value"):
            total_planned += amt["value"]
    if projects and total_planned == 0:
        warnings.append("募投项目拟使用募集资金总额为 0，请检查抽取结果")

    # 2. 发行人名称非空校验
    issuer = result.get("issuer_profile", {})
    if not issuer.get("issuer_name"):
        warnings.append("发行人名称为空")

    # 3. 股权结构：控股股东持股比例合法性
    shareholders = result.get("ownership_structure", {}).get("controlling_shareholder", [])
    for sh in shareholders:
        ratio = sh.get("shareholding_ratio")
        if ratio is not None and (ratio < 0 or ratio > 1):
            warnings.append(f"控股股东 {sh.get('name')} 持股比例 {ratio} 不合法（应在 0-1 之间）")

    # 4. 财务指标：同名指标在不同口径下应有不同 field_scope
    financials = result.get("financials", [])
    field_names = {}
    for f in financials:
        name = f.get("field_name")
        scope = f.get("field_scope")
        if name:
            key = f"{name}_{scope}"
            field_names[key] = field_names.get(key, 0) + 1

    # 5. 控股股东持股比例总和校验（应 ≤ 1）
    total_ratio = sum(sh.get("shareholding_ratio", 0) or 0 for sh in shareholders)
    if total_ratio > 1.01:  # 允许少量浮点误差
        warnings.append(f"控股股东持股比例合计 {total_ratio:.2%}，超过 100%，请检查抽取结果")

    # 6. 所有财务指标的 field_name 非空（schema 标记为 required）
    for i, f in enumerate(financials):
        if not f.get("field_name"):
            warnings.append(f"财务指标第 {i+1} 条缺少 field_name（schema 标记为必填）")
        unit = f.get("unit")
        if unit and unit not in ("万元", "元", "%"):
            warnings.append(f"财务指标 {f.get('field_name')} 的 unit='{unit}' 不在 schema 枚举内（允许：万元/元/%）")

    # 7. source_evidence_id 非空校验（Day 1 修复后应全部覆盖）
    evidence_fields = ["issuer_profile", "ownership_structure"]
    list_fields = ["financials", "fund_raising_projects", "risk_items", "compliance_items"]
    for field in evidence_fields:
        data = result.get(field)
        if isinstance(data, dict) and data:
            if not data.get("source_evidence_id"):
                warnings.append(f"{field} 缺少 source_evidence_id")
    for field in list_fields:
        items = result.get(field, [])
        null_count = sum(1 for item in items if not item.get("source_evidence_id"))
        if null_count > 0:
            warnings.append(f"{field} 中有 {null_count}/{len(items)} 条缺少 source_evidence_id")

    return warnings


def validate_against_schema(result: Dict[str, Any], schema_path: str = "schema.json") -> List[str]:
    """验证输出是否符合 schema.json，返回错误列表"""
    try:
        import jsonschema
    except ImportError:
        return ["警告：未安装 jsonschema 包，跳过 schema 校验（pip install jsonschema）"]

    from pathlib import Path
    schema_file = Path(schema_path)
    if not schema_file.exists():
        return [f"警告：schema 文件不存在 {schema_path}，跳过校验"]

    with open(schema_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(result):
        path_str = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "<root>"
        errors.append(f"{path_str}: {error.message}")

    return errors

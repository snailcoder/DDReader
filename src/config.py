"""全局配置：API 参数、模型设置、Prompt 模板、字段 Schema 定义"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 自动加载项目根目录下的 .env 文件
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path, override=True)

# ==================== InternLM API 配置 ====================
# 参考用户实测可用的端点:
# curl --location 'https://chat.intern-ai.org.cn/api/v1/chat/completions' \
#   --header 'Authorization: Bearer <token>' \
#   --header 'Content-Type: application/json' \
#   --data '{"model": "intern-latest", "messages": [...]}'
API_BASE = os.getenv("API_BASE", "https://chat.intern-ai.org.cn/api/v1")
API_KEY = os.getenv("API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "intern-latest")
MAX_TOKENS = 8192
TEMPERATURE = 0.1
REQUEST_TIMEOUT = 120

# ==================== 文档分类规则 ====================
# 文档类型关键词映射
DOC_TYPE_KEYWORDS = {
    "招股说明书": [
        "招股说明书",
        "首次公开发行股票",
        "募集说明书",
    ],
    "提示性公告": [
        "招股说明书提示性公告",
        "提示性公告",
    ],
    "上市公告书": [
        "上市公告书",
        "上市公告",
    ],
    "H股公告": [
        "H股招股说明书",
        "刊发H股",
        "H股发行",
        "香港公开发售",
    ],
    "补充披露文件": [
        "补充披露",
        "补充公告",
    ],
}

SKIP_DOC_TYPES = {"提示性公告"}  # 这些类型只输出骨架 JSON

# ==================== 章节关键词映射（用于定位大章节） ====================
CHAPTER_KEYWORDS = {
    "发行人基本情况": [
        "概览",
        "发行人基本情况",
        "公司基本情况",
        "发行人及本次发行的中介机构基本情况",
        "发行人基本情况",
        "发行人简介",
    ],
    "风险因素": [
        "风险因素",
        "风险",
        "第三节",
        "重大事项提示",
    ],
    "业务与技术": [
        "业务与技术",
        "主营业务",
        "行业",
        "第五节",
    ],
    "财务会计信息": [
        "财务会计信息",
        "管理层分析",
        "财务报表",
        "财务指标",
        "第六节",
        "第八节",
    ],
    "募集资金运用": [
        "募集资金",
        "募投",
        "募集资金运用",
        "第七节",
        "第九节",
    ],
    "公司治理与独立性": [
        "公司治理",
        "独立性",
        "董事会",
        "监事会",
        "第八节",
        "第十节",
    ],
    "投资者保护": [
        "投资者保护",
        "第九节",
        "第十一节",
    ],
    "其他重要事项": [
        "其他重要事项",
        "诉讼",
        "仲裁",
        "处罚",
        "担保",
        "关联交易",
        "第十节",
        "第十二节",
    ],
    "声明": [
        "声明",
        "第十一节",
        "第十三节",
    ],
    "附件": [
        "附件",
        "第十二节",
        "第十四节",
    ],
}

# ==================== 字段抽取 Prompt 模板 ====================

SYSTEM_PROMPT = """你是一位专业的金融文档信息抽取专家，擅长从中文招股说明书、募集说明书等金融长文档中抽取结构化信息。

你的工作原则：
1. 严格根据输入文本内容抽取，不编造、不推测、不扩展。
2. 对无法找到的信息，输出 null 或空字符串，不得臆造。
3. 所有数值字段必须保留原文中的精确值。
4. 金额字段必须拆分为 {"value": 数值, "unit": "万元/元", "currency": "CNY"} 的格式。
5. 日期字段统一为 YYYY-MM-DD 格式，若原文只有年月则补全为 YYYY-MM-01。
6. 比例字段统一输出为标准小数（如 23.56% 输出为 0.2356）。
7. 每个字段必须附带来源章节名称和原文证据片段。
8. 输出必须是合法的 JSON，不要包含任何解释性文字。
"""

ISSUER_PROFILE_PROMPT = """请从以下招股说明书文本中抽取【发行人基础信息】。

需要抽取的字段（全部必填，在文本中找到为止，不能留 null）：
- issuer_name: 公司全称（中文完整名称）
- issuer_name_normalized: 规范化公司名称（去掉"股份有限公司"、"有限公司"、"有限责任公司"等后缀的简称）
- stock_code: 股票代码（如 688123.SH、300999.SZ、601318 等，在文本中搜索"股票代码""证券代码""代码"后的数字）
- exchange: 交易所（上交所/深交所/北交所，根据文本中提到的交易所名称判断）
- board: 上市板块（主板/创业板/科创板/北交所）
- legal_representative: 法定代表人（在"法定代表人"后面找）
- establishment_date: 成立日期，格式 YYYY-MM-DD（在"成立日期""成立时间""设立日期"后找）
- registered_capital: 注册资本，格式 {"value": 数值, "unit": "万元", "currency": "CNY"}
- registered_address: 注册地址（在"注册地址""住所"后找完整地址）
- industry: 所属行业（在"所属行业""行业分类"后找，如"计算机、通信和其他电子设备制造业"）
- main_business: 主营业务（从"主营业务""经营范围""主要业务"等描述中提取）

注意：
- 所有字段都必须尽力查找，不允许随意设为 null。确实找不到再设为 null。
- stock_code 格式为 6 位数字，可能带 .SH/.SZ 后缀。
- registered_capital 的 value 必须是纯数字（不含逗号），unit 统一为"万元"（如原文是"亿元"则换算为万元）。
- 输出合法 JSON，不要 markdown 代码块标记。

文本内容：
{chapter_text}
"""

OWNERSHIP_PROMPT = """请从以下招股说明书文本中抽取【股权与控制关系】。

需要抽取的字段：
- controlling_shareholder: 控股股东列表，每个元素包含 name（名称）、shareholding_ratio（持股比例，小数）、direct_or_indirect（直接/间接）
- actual_controller: 实际控制人列表，每个元素包含 name（名称）、control_type（控制类型：一致行动协议/表决权委托/控股/其他）
- concerted_action_flag: 是否存在一致行动关系（true/false）
- top_shareholders: 前十大股东列表，每个元素包含 name（名称）、shareholding_ratio（持股比例，小数）、rank（排名）

注意：
- 持股比例统一转换为标准小数（如 25.00% 转换为 0.25）。
- 若信息不完整，缺失字段设为 null。
- 输出合法 JSON，不要 markdown 代码块标记。

文本内容：
{chapter_text}
"""

FINANCIALS_PROMPT = """请从以下招股说明书文本中抽取【财务指标】。

需要抽取的字段为列表，每个元素包含：
- field_name: 字段名称（如 营业收入、净利润、扣非净利润、研发费用、毛利率、资产总额、负债总额、经营活动现金流 等）
- field_scope: 字段口径/来源（如 合并利润表、合并资产负债表、现金流量表、研发投入指标、管理层分析 等）
- period: 统计期间，格式 YYYY-MM-DD（年报取当年 12-31，半年报取 6-30）
- value: 数值（纯数字，不带逗号、单位）
- unit: 单位（万元/元/%）
- currency: 币种（默认 CNY）
- chapter: 来源章节名称

注意：
- 金额必须拆分为数值和单位。如 "5,700.00 万元" → value=5700.0, unit="万元"。
- 表格中的多个期间数据都要抽取，每个期间作为一条独立记录。
- 同名指标在不同口径下要分别输出（如 合并利润表的净利润 vs 募投预算的研发费用）。
- 输出合法 JSON 数组，不要 markdown 代码块标记。

文本内容：
{chapter_text}
"""

FUNDRAISING_PROMPT = """请从以下招股说明书文本中抽取【募投项目信息】。

需要抽取的字段为列表，每个元素包含：
- project_name: 项目名称
- project_type: 项目类型（扩产/研发/补充流动资金/偿还银行贷款/其他）
- total_investment: 项目投资总额，格式 {"value": 数值, "unit": "万元", "currency": "CNY"}
- planned_use_of_raised_funds: 拟使用募集资金金额，格式同上
- construction_period: 建设周期（如 "36个月"）
- implementation_entity: 实施主体

注意：
- 金额必须拆分为数值和单位。
- 每个募投项目独立输出一条记录。
- 输出合法 JSON 数组，不要 markdown 代码块标记。

文本内容：
{chapter_text}
"""

RISK_PROMPT = """请从以下招股说明书文本中抽取【风险事项】。

需要抽取的字段为列表，每个元素包含：
- risk_title: 风险因素标题
- risk_category: 风险类别（财务风险/经营风险/法律风险/行业风险/技术风险/政策风险/其他）
- risk_description: 风险描述（取原文中对该风险的详细说明，限 300 字内）
- severity_level: 严重程度（高/中/低），若文本未明确则根据描述判断

注意：
- 只抽取明确列为"风险"的条目，不抽取一般经营分析。
- 输出合法 JSON 数组，不要 markdown 代码块标记。

文本内容：
{chapter_text}
"""

COMPLIANCE_PROMPT = """请从以下招股说明书文本中抽取【合规事项】。

包括以下类型：行政处罚、诉讼仲裁、关联交易、对外担保、重大诉讼、其他。

需要抽取的字段为列表，每个元素包含：
- item_type: 事项类型
- counter_party: 交易对手方/当事人
- occurrence_date: 发生日期，格式 YYYY-MM-DD（如无法确定则为 null）
- amount: 金额，格式 {"value": 数值, "unit": "万元", "currency": "CNY"}（如无数值则为 null）
- description: 事项描述
- period: 关联期间（如关联交易对应的报告期）

注意：
- 只抽取报告期内发生的、对发行人有实质影响的合规事项。
- 输出合法 JSON 数组，不要 markdown 代码块标记。

文本内容：
{chapter_text}
"""

# Prompt 映射表
EXTRACTION_PROMPTS = {
    "issuer_profile": ISSUER_PROFILE_PROMPT,
    "ownership_structure": OWNERSHIP_PROMPT,
    "financials": FINANCIALS_PROMPT,
    "fund_raising_projects": FUNDRAISING_PROMPT,
    "risk_items": RISK_PROMPT,
    "compliance_items": COMPLIANCE_PROMPT,
}

# ==================== 空骨架 Schema ====================
EMPTY_SKELETON = {
    "document_id": "",
    "document_type": "",
    "issuer_profile": {
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
    },
    "ownership_structure": {
        "controlling_shareholder": [],
        "actual_controller": [],
        "concerted_action_flag": False,
        "top_shareholders": [],
    },
    "financials": [],
    "fund_raising_projects": [],
    "risk_items": [],
    "compliance_items": [],
    "evidence_index": [],
}

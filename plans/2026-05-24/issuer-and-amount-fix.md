# Day 2: issuer_profile 抽取 + amount 单位 + 批模式浅拷贝修复

## 目标
修复 issuer_profile 一致性缺失、parse_amount 输出非法 enum、批模式浅拷贝 bug。

## 问题定位

### 2.1 issuer_profile 字段抽取不全
- `issuer_name_normalized`：所有文档均为 null（LLM prompt 未要求规范化名称）
- `stock_code`：所有文档均为 null（未专门抽取股票代码）
- `registered_capital.value`：部分为 null（LLM 正确提取了文本但 post_processor 未转换）
- `legal_representative` / `establishment_date` / `registered_address`：部分文档缺失

**根因**：LLM prompt（`ISSUER_PROFILE_PROMPT`）对非必填字段的描述不够明确，LLM 倾向于跳过不确定的字段。

### 2.2 parse_amount 输出非法"亿元"
- `utils.py:parse_amount` 正则匹配 `([\d,]+\.?\d*)\s*(万元|亿元|元)`，匹配后保留原始 unit
- schema `unit` enum 只允许 `"万元"` / `"元"` / `"%"`，`"亿元"` 不合法
- 影响：财务指标、募投项目、合规事项中所有大额金额

### 2.3 批模式浅拷贝 bug
- `pipeline.py:67`: `result = dict(config.EMPTY_SKELETON)` 是浅拷贝
- 嵌套 dict（如 `issuer_profile`）是共享引用
- 实际运行时因每份文档走独立 `run_pipeline` 尚未触发，但批模式潜在 bug

## 修复方案

### Step 1: 增强 issuer_profile LLM prompt

**文件**: `src/config.py`

修改 `ISSUER_PROFILE_PROMPT`：

```
1. 公司全称（issuer_name）：必填，文档中的完整中文名称
2. 规范化公司名称（issuer_name_normalized）：必填，去掉"股份有限公司"、"有限公司"等后缀的简称
3. 股票代码（stock_code）：必填，如 688123.SH、300999.SZ
4. 交易所（exchange）：必填，上交所/深交所/北交所
5. 上市板块（board）：必填，主板/创业板/科创板/北交所
6. 法定代表人（legal_representative）：必填
7. 成立日期（establishment_date）：必填，格式 YYYY-MM-DD
8. 注册资本（registered_capital）：必填，拆分为 {value, unit, currency}
9. 注册地址（registered_address）：必填
10. 所属行业（industry）：必填
11. 主营业务（main_business）：必填
```

新增字段描述强调"必填"，并在每个字段后附加提示。

### Step 2: 修复 parse_amount 亿元→万元 转换

**文件**: `src/utils.py`

在 `parse_amount` 函数中，检测到 unit 为 "亿元" 时转换：

```python
def parse_amount(text):
    """解析金额字符串，返回 {value, unit, currency}"""
    # ... 现有匹配逻辑 ...
    if unit == "亿元":
        value = value * 10000  # 1亿元 = 10000万元
        unit = "万元"
    # 兼容 "亿" 缩写
    if "亿" in text and unit == "元":
        # 如 "1亿元" → value=1, unit=亿元 → 已在上一步处理
        pass
    return {"value": value, "unit": unit, "currency": "CNY"}
```

同时增强正则，支持：
- "1.2亿" → value=1.2, 转换为 12000 万元
- "46,565.64 万元" → value=46565.64
- "约 5000 万元" → value=5000
- 负数："-1,234.56 万元" → value=-1234.56

### Step 3: 修复浅拷贝

**文件**: `src/pipeline.py`

```python
import copy

# line 67 修改:
result = copy.deepcopy(config.EMPTY_SKELETON)
```

### Step 4: 补充 stock_code 抽取

**文件**: `src/pipeline.py` 或新增函数 `infer_stock_code`

从文档文本中匹配股票代码模式：
- 上交所: `\d{6}\.SH` 或 `\d{6}` 出现在"证券代码"、"股票代码"、"代码" 等语境
- 深交所: `\d{6}\.SZ`

在 pipeline 中，从第一页或 issuer_profile 相关章节扫描文本，抽取后设置到 `result["issuer_profile"]["stock_code"]`。

## 验证方法

1. 运行 pipeline 处理 3 份不同招股说明书
2. 检查输出 JSON：
   - `issuer_profile` 所有字段均非 null
   - `registered_capital.unit` 为 "万元"（而非 "亿元"）
   - 所有 `financials.value` 单位正确（非"亿元"）
   - 批模式下 `EMPTY_SKELETON` 没有被前一份文档污染

## 涉及文件

| 文件 | 修改类型 |
|------|---------|
| `src/config.py` | 增强 `ISSUER_PROFILE_PROMPT` |
| `src/utils.py` | 修复 `parse_amount`（亿元→万元、负数、模糊匹配） |
| `src/pipeline.py` | 浅拷贝修复 + stock_code 抽取 |
| `src/post_processor.py` | 在 `process_financials` / `process_fund_raising` 中二次确保 unit 合法 |

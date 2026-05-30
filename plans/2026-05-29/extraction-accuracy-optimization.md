# 抽取字段完整性与准确性优化

## 目标

对比 wiki 文档（抽取示例.md、证据索引.md）与实际代码/输出结果，修复 6 个系统性问题，提升字段覆盖率和证据关联准确性。

## 问题定位

### 2.1 列表型字段 source_evidence_id 全部为 null（严重）

**现象**：financials、fund_raising_projects、risk_items、compliance_items 的 `source_evidence_id` 在所有结果文件中 100% 为 null。

**根因**：`evidence_builder.py:attach_evidence_ids` 使用 round-robin 分配 evidence_id 给列表型字段，但 `_get_ev_ids_for_field` 返回的列表为空或匹配逻辑失败，导致赋值未生效。

**验证数据**（5 份结果文件）：
```
financials:      32/32 null, 28/28 null, 0/0, 0/0, 0/0
fund_raising:    3/3 null, 2/2 null, 0/0, 0/0, 0/0
risk_items:      35/35 null, 18/18 null, 0/0, 0/0, 0/0
compliance:      3/3 null, 17/17 null, 0/0, 0/0, 0/0
```

### 2.2 证据索引无去重（高）

**现象**：wiki 要求"如果两个证据对象引用了同一段原文，则共享同一个 evidence_id，在 evidence_index 中只出现一次"。当前代码为每个 block 创建独立 evidence_id。

**影响**：一份文档 587 条证据，实际有效证据远少于此，浪费存储且违反规范。

### 2.3 schema 与 wiki/prompt 不一致（高）

**现象**：`top_shareholders` 的 schema 缺少 `direct_or_indirect` 字段，但 wiki 示例和 prompt 都要求它。

**影响**：所有结果中 top_shareholders 的 `direct_or_indirect` 全部为 null。

### 2.4 registered_address 始终为 null（高）

**现象**：所有结果文件中 `registered_address` 均为 null。

**根因**：LLM 在复杂表格中遗漏该字段，prompt 缺少表格搜索指引。

### 2.5 stock_code / issuer_name_normalized 始终为 null（高）

**现象**：所有结果文件中这两个字段均为 null。

**根因**：LLM 未执行后缀去除、未在表格中搜索股票代码。缺少后处理 fallback。

### 2.6 concerted_action_flag 始终为 False（中）

**现象**：所有结果文件中均为 False，即使文档中明确提到一致行动协议。

**根因**：prompt 缺少"曾经存在也应标记"的指引。

---

## 修复方案

### Step 1: schema.json — 添加 direct_or_indirect

**文件**: `schema.json`

在 `top_shareholders.items.properties` 中添加 `direct_or_indirect` 字段，与 `controlling_shareholder` 保持一致。

```json
"direct_or_indirect": {
  "type": ["string", "null"],
  "enum": ["直接", "间接"],
  "description": "直接持股或间接持股"
}
```

**状态**: ✅ 已完成

### Step 2: evidence_builder.py — 证据去重 + 内容感知关联

**文件**: `src/evidence_builder.py`

#### 2a. 证据去重

在 `build_evidence_index` 中增加 `quote_to_ev_id` 字典，按 quote 前 200 字符去重。相同 quote 复用 evidence_id，不重复创建 entry。

```python
qkey = _quote_key(quote)
if qkey and qkey in quote_to_ev_id:
    evidence_id = quote_to_ev_id[qkey]  # 复用
else:
    ev_counter += 1
    evidence_id = f"ev_{ev_counter:04d}"
    quote_to_ev_id[qkey] = evidence_id
    # 创建新 entry...
```

#### 2b. 内容感知关联

移除 round-robin 逻辑，新增 `_find_best_evidence_for_item` 函数：

1. 根据字段内容（field_name / project_name / risk_title 等）构建搜索文本
2. 在匹配章节的 evidence 中用关键词交集计算相似度
3. 选择最相关的 evidence_id
4. 回退策略：匹配章节第一个 evidence → 全局第一个 evidence

```python
def _find_best_evidence_for_item(item, field_name, evidence_index, chapter_to_ev_ids, field_chapter_keywords):
    # 1. 收集匹配章节的 evidence
    # 2. 从 item 提取搜索文本
    # 3. 计算相似度，选最佳
    # 4. 回退
```

#### 2c. bbox 匹配增强

`_find_bbox` 改为三策略：
1. 前缀精确匹配（200 字符）
2. 关键词交集匹配（jieba 分词，相似度 > 0.3）
3. 回退到页面第一个 block

**状态**: ✅ 已完成

### Step 3: config.py — 增强 prompt

**文件**: `src/config.py`

#### 3a. ISSUER_PROFILE_PROMPT

- `registered_address`：增加"在表格中搜索'注册地址''住所''注册地'等字段"的指引
- `stock_code`：增加"在表格中搜索'股票代码''证券代码''A股代码'等关键词"的指引
- `issuer_name_normalized`：增加去除后缀的示例（如"深圳北芯生命科技股份有限公司"→"深圳北芯生命科技"）
- `exchange`/`board`：明确枚举值要求（上交所/深交所/北交所）

#### 3b. OWNERSHIP_PROMPT

- `concerted_action_flag`：增加判断指引——搜索"一致行动""一致行动协议""共同控制"等关键词；报告期内曾存在一致行动协议（即使已解除）也应设为 true；"不谋求控制权"的承诺不等于一致行动关系
- `top_shareholders`：增加 `direct_or_indirect` 字段要求

**状态**: ✅ 已完成

### Step 4: post_processor.py — fallback 逻辑 + 枚举映射

**文件**: `src/post_processor.py`

#### 4a. issuer_name_normalized fallback

新增 `_normalize_issuer_name` 函数，从 issuer_name 自动去除后缀：

```python
_SUFFIXES = ["股份有限公司", "有限责任公司", "有限公司", "公司"]

def _normalize_issuer_name(name):
    for suffix in _SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return None
```

在 `process_issuer_profile` 中：如果 LLM 未返回 issuer_name_normalized，自动从 issuer_name 生成。

#### 4b. exchange/board 枚举映射

新增 `_EXCHANGE_MAP` 和 `_BOARD_MAP`，在 `process_issuer_profile` 中对 LLM 返回的值做标准化：

```python
_EXCHANGE_MAP = {
    "上海证券交易所": "上交所",
    "深圳证券交易所": "深交所",
    "北京证券交易所": "北交所",
}
```

**状态**: ✅ 已完成

### Step 5: text_extractor.py — 放宽证据文本长度限制

**文件**: `src/text_extractor.py`

将 `build_section_text_with_evidence` 的 `max_chars` 从 15000 提升到 50000，避免长章节证据丢失。

**状态**: ✅ 已完成

---

## 涉及文件

| 文件 | 修改类型 | 状态 |
|------|---------|------|
| `schema.json` | 添加字段 | ✅ 已完成 |
| `src/evidence_builder.py` | 重写：去重 + 内容感知匹配 | ✅ 已完成 |
| `src/config.py` | 增强 prompt | ✅ 已完成 |
| `src/post_processor.py` | 添加 fallback + 枚举映射 | ✅ 已完成 |
| `src/text_extractor.py` | 修改参数 | ✅ 已完成 |

## 验证方法

1. 对 `data/mineru-output/v1` 中的文档重新运行 pipeline
2. 检查输出 JSON：
   - `financials[].source_evidence_id` 不再为 null
   - `fund_raising_projects[].source_evidence_id` 不再为 null
   - `risk_items[].source_evidence_id` 不再为 null
   - `compliance_items[].source_evidence_id` 不再为 null
   - `evidence_index` 中无重复 quote
   - `issuer_profile.registered_address` 不再为 null
   - `issuer_profile.stock_code` 不再为 null
   - `issuer_profile.issuer_name_normalized` 不再为 null
   - `issuer_profile.exchange` / `board` 符合 schema 枚举
   - `ownership_structure.concerted_action_flag` 在有一致行动协议时为 true
   - `ownership_structure.top_shareholders[].direct_or_indirect` 不再为 null
3. 运行 `validate_against_schema` 确认无 schema 错误

## 待办（未实施）

以下优化点在本次修改中未实施，留作后续：

- **stock_code 后处理 fallback**：如果 LLM 未返回 stock_code，从原始文本中用 `utils.infer_stock_code` 提取
- **registered_address 后处理 fallback**：从 issuer_name 关联的注册信息中提取
- **_find_bbox 健壮性**：当前已增强为三策略匹配，但跨页 bbox 定位仍需优化
- **证据关联精确度**：当前基于关键词相似度匹配，未来可考虑用 LLM 做 evidence-field 关联

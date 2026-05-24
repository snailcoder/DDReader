# Day 3: TOC 解析优化 + 死代码清理 + schema 校验

## 目标
优化 TOC 解析使得适配更多中文模板、清理约 250 行死代码、增加输出 schema 校验。

## 问题定位

### 3.1 TOC 解析正则脆弱
- `chapter_parser.py:110`: `r"(.+?)[\s.]{2,}(\d+)"` — 要求标题和页码之间至少有 2 个空格或点号
- 中文目录常见格式：全角点号"．．．．"、制表符、无分隔符（标题直接跟页码）、右对齐空格
- `_validate_toc` 要求 page_idx 严格递增 — 但有些目录项指向同一页
- TOC 结束检测阈值 2000 chars — 对不同格式文档不稳定

### 3.2 死代码

| 文件 | 死代码内容 | 行数 |
|------|-----------|------|
| `config.py` | `CHAPTER_KEYWORDS` 从未被使用（`llm_extractor.py` 有 `FIELD_CHAPTER_MAPPING` 替代） | ~70 |
| `evidence_builder.py` | 全部 72 行（计划 day1 重写，day3 确认清理旧代码） | 72 |
| `text_extractor.py` | `get_text_for_field()` 从未被调用 | ~40 |
| `utils.py` | `load_mineru_data()` / `sanitize_json_string()` / duplicate `infer_exchange_and_board` | ~50 |
| `llm_client.py` | `LLMClient` 同步类（生产环境只用 AsyncLLMClient） | ~60 |
| `pipeline.py` | 同步 `run_pipeline` vs 异步 `run_pipeline_async` 大量重复（~180 行重复） | ~180 |

### 3.3 无 schema 输出校验
- pipeline 直接输出 LLM 返回 + post_process 后的 JSON
- 没有任何一步检查输出是否符合 `schema.json`
- `post_processor.py:validate_result` 仅 4 项弱校验

## 修复方案

### Step 1: 增强 TOC 解析

**文件**: `src/chapter_parser.py`

1. **宽松正则**：
```python
# 支持更多分隔符形式
TOC_LINE_PATTERN = re.compile(
    r"(.+?)[\s.．·\t]{1,}(\d+)$"  # 半角点 + 全角点 + 中间点 + tab
)
```

2. **page_idx 非严格递增处理**：允许相同或小幅跳跃
```python
def _validate_toc(toc_entries):
    prev_page = -1
    for entry in toc_entries:
        if entry["page_idx"] < prev_page:  # 只拒绝倒退
            return False
        prev_page = entry["page_idx"]
    return True
```

3. **TOC 结束检测自适应**：同时检查 "目 录" / "目录" 起始 + "第X节" / "第X章" + "第一节" 作为结束标志

4. **subsection 去重**：`_find_subsections_by_regex` 中全角/半角括号匹配分别触发时去重

### Step 2: 清理死代码

**文件**: 多处

- `config.py`: 删除 `CHAPTER_KEYWORDS` 定义（保留其他配置）
- `text_extractor.py`: 删除 `get_text_for_field()`
- `utils.py`: 删除 `load_mineru_data()`, `sanitize_json_string()`, 重复的 `infer_exchange_and_board`
- `llm_client.py`: 保留 `LLMClient`（可能有用），标记 `@deprecated`
- `pipeline.py`: 抽取 sync/async 公共逻辑到 `_prepare_pipeline()` 和 `_finalize_pipeline()` 辅助函数

### Step 3: 增加 jsonschema 输出校验

**文件**: `src/post_processor.py` 新增 `validate_against_schema()`

```python
import json
import jsonschema

def validate_against_schema(result: dict, schema_path: str = "schema.json") -> List[str]:
    """验证输出是否符合 schema.json，返回错误列表"""
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(result):
        errors.append(f"{error.path}: {error.message}")
    return errors
```

在 `pipeline.py` 的 `run_pipeline_async` 末尾调用，收集错误并写入日志/输出。

添加 `jsonschema` 到 `requirements.txt`。

### Step 4: 增强 validate_result

**文件**: `src/post_processor.py`

新增检查项：
- 跨募投项目总投资金额汇总 + 募集资金汇总是否匹配
- 持股比例是否总和 ≤ 1（或 100%）
- 所有 `field_name` 非空（schema 标记为 required）
- 所有 `unit` 值是否在 schema 枚举内
- source_evidence_id 非空（Day 1 修复后的增强校验）

## 验证方法

1. 用 3 份不同版式招股说明书测试 TOC 解析：
   - 科创板（1-1-N 页码格式）
   - 创业板
   - 深交所主板
2. 确认目录结构正确解析（3 级章节标题）
3. 代码 lint 检查无 import 残留
4. 运行 pipeline 观察 validate_against_schema 输出

## 涉及文件

| 文件 | 修改类型 |
|------|---------|
| `src/chapter_parser.py` | TOC 正则宽松、去重、page_idx 校验放宽 |
| `src/config.py` | 删除死代码 `CHAPTER_KEYWORDS` |
| `src/text_extractor.py` | 删除 `get_text_for_field()` |
| `src/utils.py` | 删除 3 个死函数 |
| `src/post_processor.py` | 新增 `validate_against_schema` + 增强 `validate_result` |
| `src/pipeline.py` | 提取公共逻辑、调用 schema 校验 |
| `requirements.txt` | 添加 `jsonschema` |

# Day 1: 证据可追溯系统修复

## 目标
修复 source_evidence_id 未正确关联 + bbox 为空 + evidence_builder.py 死代码的致命问题。

## 问题定位

### 1.1 evidence_builder.py 是死代码 (pipeline.py)
- `pipeline.py` import 了 `build_evidence_index` 和 `attach_evidence_ids` 但从未调用
- pipeline 内联重写了简单版 `_build_evidence_index`（lines 130-146）和 `_attach_evidence_ids`（lines 166-196）
- 内联版 `_attach_evidence_ids` 只处理了 `issuer_profile` 和 `ownership_structure` 两类字段，其他 4 类无 source_evidence_id

### 1.2 bbox 全空
- 内联 `_build_evidence_index` 构建 evidence 时没有从 mineru 原始 block 中提取 bbox 坐标
- `quote` 字段存在，但 `bbox` 被设为 `[]`

## 修复方案

### Step 1: 让 pipeline 实际调用 evidence_builder.py

**文件**: `src/pipeline.py`

修改 `run_pipeline` 和 `run_pipeline_async` 中原本内联的证据构建逻辑，替换为调用 `evidence_builder.py` 的函数：

```python
# 替换这部分内联代码:
# evidence_index = _build_evidence_index(...)
# result = _attach_evidence_ids(result, evidence_index)
# 为:
from .evidence_builder import build_evidence_index, attach_evidence_ids

evidence_index = build_evidence_index(chapter_texts, raw_blocks_by_page)
result = attach_evidence_ids(result, evidence_index, raw_blocks_by_page)
```

### Step 2: 修复 evidence_builder.py

**文件**: `src/evidence_builder.py`

当前代码（72 行）需要重写：

```python
def build_evidence_index(chapter_texts: Dict[str, str], raw_blocks_by_page: Dict[int, List[dict]]) -> List[dict]:
    """
    从 chapter_texts 和原始 mineru block 数据构建 evidence_index。
    每个 evidence 必须包含：evidence_id, page_no, chapter, block_type, quote, bbox
    """
    evidence_index = []
    ev_counter = 0
    
    for chapter_key, chapter_data in chapter_texts.items():
        # chapter_data 包含 page_info 和 text
        for block in chapter_data.get("blocks", []):
            ev_counter += 1
            evidence_id = f"ev_{ev_counter:04d}"
            
            # 从原始 block 提取 bbox
            raw_block = find_raw_block(block, raw_blocks_by_page)
            bbox = raw_block.get("bbox", []) if raw_block else []
            
            evidence_index.append({
                "evidence_id": evidence_id,
                "page_no": block.get("page_idx", 0) + 1,  # mineru 0-indexed → 1-indexed
                "chapter": chapter_key,
                "block_type": raw_block.get("type", "text") if raw_block else "text",
                "quote": block.get("text", "")[:200],  # 截断避免过长
                "bbox": bbox
            })
    
    return evidence_index


def attach_evidence_ids(result: dict, evidence_index: List[dict], raw_blocks_by_page: Dict[int, List[dict]]) -> dict:
    """
    为 result 中所有 6 类字段匹配 source_evidence_id。
    - 对象型字段（issuer_profile, ownership_structure 的子字段）：按字段名+章节匹配
    - 数组型字段（financials, fund_raising_projects, risk_items, compliance_items）：按条目内容匹配
    """
    category_map = {
        "issuer_profile": ("issuer_profile", "object"),
        "ownership_structure": ("ownership_structure", "object"),
        "financials": ("financials", "array"),
        "fund_raising_projects": ("fund_raising_projects", "array"),
        "risk_items": ("risk_items", "array"),
        "compliance_items": ("compliance_items", "array"),
    }
    # ... 匹配逻辑
    return result
```

### Step 3: 传递 raw_blocks_by_page 给 pipeline

`preprocessor.py` 在 `load_content_list` 中已经解析了完整的 `content_list`（含 blocks）。需要增加一个函数或返回额外数据：

```python
def load_content_list_with_blocks(input_dir: str) -> Tuple[str, Dict[int, List[dict]]]:
    """返回 (merged_markdown, raw_blocks_by_page)"""
    content_list = load_content_list(input_dir)
    raw_blocks_by_page = {}
    for item in content_list:
        page_idx = item.get("page_idx")
        if page_idx not in raw_blocks_by_page:
            raw_blocks_by_page[page_idx] = []
        raw_blocks_by_page[page_idx].append(item)
    merged = preprocessor.merge_pages(content_list)
    return merged, raw_blocks_by_page
```

### Step 4: 传递 raw_blocks 数据到 pipeline 并用于 evidence 构建

修改 `run_pipeline` / `run_pipeline_async` 签名，传入 `raw_blocks_by_page`。

## 验证方法

1. 对任意招股说明书运行 pipeline
2. 检查输出 JSON：
   - `evidence_index[].bbox` 不再是 `[]`
   - `issuer_profile.source_evidence_id` 不为 null
   - `financials[].source_evidence_id` 不为 null
   - `risk_items[].source_evidence_id` 不为 null
   - `compliance_items[].source_evidence_id` 不为 null
   - `fund_raising_projects[].source_evidence_id` 不为 null

## 涉及文件

| 文件 | 修改类型 |
|------|---------|
| `src/evidence_builder.py` | 重写 |
| `src/pipeline.py` | 调用 evidence_builder.py，传递 raw_blocks |
| `src/preprocessor.py` | 新增 `load_content_list_with_blocks()` |
| `src/text_extractor.py` | 在 `extract_chapter_texts` 返回值中保留 block 级元数据 |

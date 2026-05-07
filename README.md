# 金融长文档字段抽取 Pipeline

本项目基于 **InternLM** 大模型，实现从 mineru 解析后的 PDF 文档（招股说明书、募集说明书等）中自动抽取银行授信尽调所需的结构化字段。

## 项目结构

```
├── src/                          # 核心代码
│   ├── config.py                 # API 配置、Prompt 模板、Schema 定义
│   ├── utils.py                  # 通用工具（数据加载、金额/日期解析、文本清理等）
│   ├── preprocessor.py           # 预处理模块（加载 content_list.json，按页合并为 markdown）
│   ├── document_classifier.py    # 文档分类器（招股说明书 / 提示性公告 / H股公告等）
│   ├── chapter_parser.py         # 目录解析 + 章节切分（大章→小节→子节三级结构）
│   ├── text_extractor.py         # 按章节聚合文本，保留页码证据
│   ├── llm_client.py             # InternLM API 客户端（OpenAI SDK 兼容）
│   ├── llm_extractor.py          # 6 大字段类别的大模型抽取器
│   ├── post_processor.py         # 金额拆分、日期格式化、比例标准化、基础业务校验
│   ├── evidence_builder.py       # 证据索引构建与 source_evidence_id 关联
│   ├── pipeline.py               # 主 Pipeline（串联全部步骤）
│   └── run.py                    # 手动运行入口
├── data/mineru-output/           # mineru 解析后的文档目录（每份一个子目录）
├── schema.json                   # 输出数据结构的 JSON Schema
├── docs/DDReader.wiki/           # 需求与设计文档
└── README.md                     # 本文档
```

## 环境准备

### 1. Python 虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai python-dotenv
```

### 2. API Key 配置

```bash
export INTERNLM_API_KEY="your-api-key-here"
```

或在运行脚本时通过 `--api_key` 参数传入。

## 使用方法

### 单文档运行

```bash
python src/run.py --input_dir data/mineru-output/1224957012_3cab4602.pdf-4b9a8df8-3003-4e38-bdeb-b3f983ffd76f --output_dir results/
```

### 批量手动运行（遍历全部文档）

```bash
for d in data/mineru-output/*/; do
    python src/run.py --input_dir "$d" --output_dir results/
done
```

### 输出结果

每个文档会在 `--output_dir` 下生成一个 JSON 文件，文件名格式为 `{document_id}.json`，内容严格符合 `schema.json` 定义的结构，包含：

- `document_id`: 文档唯一标识
- `document_type`: 文档类型（招股说明书 / 提示性公告 / H股公告 / 其他）
- `issuer_profile`: 发行人基础信息（公司名称、注册地址、注册资本、法定代表人等）
- `ownership_structure`: 股权与控制关系（控股股东、实际控制人、前十大股东、一致行动关系）
- `financials`: 财务指标列表（营业收入、净利润、研发费用、毛利率等，含口径和期间）
- `fund_raising_projects`: 募投项目列表（项目名称、投资总额、拟使用募集资金、建设周期）
- `risk_items`: 风险事项列表（风险标题、类别、描述、严重程度）
- `compliance_items`: 合规事项列表（行政处罚、诉讼仲裁、关联交易、对外担保）
- `evidence_index`: 证据索引（页码、章节、原文片段、bbox 坐标）

### 提示性公告处理

如果文档被识别为"提示性公告"等短文档，Pipeline 将直接输出**空字段的骨架 JSON**（所有字段为 null 或空列表），不再调用大模型抽取。

## Pipeline 流程说明

```
输入：mineru-output 下任一 PDF 解析目录
  │
  ▼
1. 预处理器（preprocessor）
      └── 加载 *_content_list.json，过滤 image/header/footer/page_number 等无关类型
          按 page_idx 分组，合并为 markdown 格式（使用 text_level 字段添加标题标记）
  │
  ▼
2. 文档分类器（document_classifier）
      └── 基于第一页内容识别文档类型
          识别为「招股说明书/提示性公告/H股公告/其他」
  │
  ▼
3. 章节解析器（chapter_parser）
      └── 解析目录：从预处理结果中找到目录页，提取大章标题和页码
          切分大章：按目录中的页码切分
          切分小节：页面分裂 + 页面重组
          切分子节：正则识别（一）（二）等子节标题（可选）
          输出三级结构：大章 → 小节 → 子节
  │
  ▼
4. 文本提取器（text_extractor）
      └── 对每个章节，聚合对应的文本内容
          保留表格 HTML、段落文本，同时记录 page_idx 作为证据
  │
  ▼
5. 大模型字段抽取器（llm_extractor）
      └── 调用 InternLM API，按 6 大字段类别分批次/分章节调用：
          - 发行人基础信息（概览、发行人基本情况章节）
          - 股权与控制关系（发行人基本情况、公司治理章节）
          - 财务指标（财务会计信息、业务与技术章节）
          - 募投项目（募集资金运用章节）
          - 风险事项（风险因素章节）
          - 合规事项（其他重要事项、公司治理章节）
  │
  ▼
6. 后处理器（post_processor）
      └── 金额标准化："46,565.64 万元" → {"value": 46565.64, "unit": "万元", "currency": "CNY"}
          日期格式化：YYYY-MM-DD
          比例标准化：小数表示
          基础校验：募投金额汇总一致性、控股股东持股比例合法性、发行人名称非空等
  │
  ▼
7. 证据索引构建器（evidence_builder）
      └── 为每个抽取字段匹配 source_evidence_id
          关联到 evidence_index 中的 page_no / chapter / quote
  │
  ▼
输出：{doc_id}.json（符合 schema.json 的结构化结果）
```

## 关键设计决策

| 问题 | 决策 |
|------|------|
| **数据源** | 使用 `*_content_list.json`（mineru 解析的 block 列表），按页合并为 markdown 格式 |
| **预处理** | 过滤 image/header/footer/page_number 等无关类型，使用 text_level 字段区分标题层级 |
| **目录解析** | 从预处理结果中找到目录页，用正则匹配 `第X节 标题...页码` 格式提取大章信息 |
| **章节切分** | 三级结构：大章（按目录页码切分）→ 小节（页面分裂+页面重组）→ 子节（正则识别） |
| **页面分裂** | 对每个页面，根据目录中的小节标题位置，将页面分裂为多个片段 |
| **页面重组** | 遍历分裂后的片段，按二级标题重组为小节 |
| **表格处理** | 保留 HTML `<table>` 原样送入大模型，比纯文本更易让模型理解行列关系 |
| **大模型调用** | 使用 InternLM API（OpenAI-compatible 接口），模型 `intern-latest` |
| **抽取策略** | 分章节独立调用，每次 Prompt 只聚焦 1~2 个字段类别，降低幻觉和超长上下文压力 |
| **证据索引** | 每个抽取字段携带 `source_evidence_id`，指向 `evidence_index` 中的 `page_no` / `chapter` / `quote` |

## 数据格式说明

### content_list.json 格式

mineru 解析输出的 `*_content_list.json` 是一个一维列表，每个元素代表文档中的一行/一块内容：

```json
{
    "type": "text",           // 类型：text/image/header/page_number/table 等
    "text": "文本内容",        // 文本内容
    "text_level": 1,          // 标题层级（1=一级标题，2=二级标题，无则为正文）
    "bbox": [x1, y1, x2, y2], // 边界框坐标
    "page_idx": 0             // 页码（从0开始）
}
```

### 章节结构

解析后的章节结构为三级嵌套：

```json
{
    "chapters": [
        {
            "heading": "第八节 财务会计信息与管理层分析",
            "page_idx": 264,
            "sections": [
                {
                    "heading": "一、财务报表",
                    "page_idx": 264,
                    "text_list": [{"text": "...", "page_idx": 264}],
                    "subsections": [
                        {
                            "heading": "（一）合并资产负债表",
                            "page_idx": 264,
                            "text_list": [{"text": "...", "page_idx": 264}]
                        }
                    ]
                }
            ]
        }
    ]
}
```

## 注意事项

1. **API 调用费用**：每份完整招股说明书大约需要 6~10 次 LLM API 调用（6 个字段类别 × 1~2 个文本 chunk），请确保 API 余额充足。
2. **文本长度限制**：单条 Prompt 文本长度限制在 120000 字符左右，超长章节会自动切分，分别调用后合并结果。
3. **准确率**：当前版本采用"规则切分 + 大模型抽取"的两阶段策略，对格式规范的文档效果较好；对跨页表格、复杂财务附注等难点，仍需人工复核。
4. **扩展**：如需接入其他模型，只需在 `llm_client.py` 中替换 `OpenAI` 客户端即可，上层接口保持不变。

## 参考文档

- 抽取方法设计文档：`docs/DDReader.wiki/抽取方法.md`
- 字段分布概况：`docs/DDReader.wiki/字段分布概况.md`
- 输出数据结构定义：`schema.json`
- InternLM API 文档：https://internlm.intern-ai.org.cn/api/document

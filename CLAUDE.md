# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DDReader ("DrDD") is a Python pipeline that extracts structured fields from Chinese financial documents (IPO prospectuses, bond prospectuses, listing announcements, etc.). It uses an LLM (InternLM/DeepSeek via OpenAI-compatible API) to extract 6 categories of structured data and outputs JSON conforming to `schema.json`. Despite living under a GOPATH directory, this is a pure Python project with no Go code.

## Common Commands

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run CLI (single document)
```bash
python src/run.py --input_dir data/mineru-output/<doc_dir> --output_dir results/
```

### Run CLI (batch)
```bash
python src/run.py --input_dir data/mineru-output/ --output_dir results/
```

### Start API server
```bash
uvicorn src.api:app --host 0.0.0.0 --port 8001
```

### Docker Compose (full stack: mineru-api + drdd-api)
```bash
docker compose --profile full up
```

### Verify deployment
```bash
bash scripts/verify_deployment.sh
```

### Environment setup
Copy `.env.example` to `.env` and set `INTERNLM_API_KEY` (or use `--api_key` CLI flag).

## Architecture

The system is a 7-stage pipeline orchestrated by `src/pipeline.py`:

```
mineru-output JSON → Preprocessor → Classifier → ChapterParser → TextExtractor → LLMExtractor → PostProcessor → EvidenceBuilder → Output JSON
```

**Key stages:**

1. **Preprocessor** (`preprocessor.py`) — Loads `*_content_list.json`, filters out image/header/footer blocks, merges by page into markdown.
2. **Document Classifier** (`document_classifier.py`) — Keyword scoring on first 3000 chars. Short docs (announcements) skip LLM and return a skeleton JSON.
3. **Chapter Parser** (`chapter_parser.py`, 642 lines — largest file) — TOC regex parsing + 3-level chapter splitting (chapter → section → subsection). Subsection splitting uses Chinese numeral regex patterns.
4. **Chapter Mapper** (`chapter_mapper.py`) — Maps chapter headings to field categories via jieba + Jaccard similarity. Falls back to static keywords or a single LLM call if confidence is low.
5. **Text Extractor** (`text_extractor.py`) — Aggregates text per chapter, separates table HTML from paragraphs, preserves page evidence.
6. **LLM Extractor** (`llm_extractor.py`) — Calls LLM for 6 field categories independently. Supports sync and async (30 concurrent, 2s rate limit). Auto-chunks text exceeding 120K chars. Deduplicates across chunks.
7. **Post-Processor** (`post_processor.py`) + **Evidence Builder** (`evidence_builder.py`) — Normalizes amounts/dates/ratios, validates business rules, builds evidence_index with bbox coordinates from raw mineru blocks.

**Two runtime modes:**
- **CLI** (`src/run.py`): `python src/run.py --input_dir <dir> --output_dir results/`
- **HTTP API** (`src/api.py`): FastAPI on port 8001. PDFs go to mineru-api (port 8000) first; JSONs go directly to the pipeline.

**Two entry points in pipeline.py:** `run_pipeline()` (sync) and `run_pipeline_async()` (async, used by the API server).

## Key Files

| File | Purpose |
|------|---------|
| `src/config.py` | API config, prompt templates, schema skeleton, doc type rules |
| `src/chapter_parser.py` | TOC parsing + 3-level chapter splitting (most complex module) |
| `src/llm_extractor.py` | LLM field extraction with chunking and deduplication |
| `src/post_processor.py` | Amount/date/ratio normalization, business validation |
| `src/evidence_builder.py` | Evidence index construction and source_evidence_id attachment |
| `src/pipeline.py` | Main orchestrator (sync + async entry points) |
| `schema.json` | JSON Schema (draft-07) defining output structure |

## Important Design Decisions

- **Data source**: Only `*_content_list.json` from mineru output (not `full.md` or other formats).
- **Tables**: Preserved as HTML `<table>` in prompts — easier for the LLM to understand row/column relationships.
- **Extraction strategy**: Per-chapter independent LLM calls, each prompt focuses on 1-2 field categories to reduce hallucination.
- **Evidence traceability**: Every extracted field carries a `source_evidence_id` linking to `evidence_index` with page_no, chapter, and original quote.
- **Short document skip**: Documents classified as announcements return a skeleton JSON with null/empty fields — no LLM calls made.
- **Exchange/board inference**: `utils.infer_exchange_and_board_from_text()` extracts exchange, board, and stock code from the first page. These are preserved as fallbacks if the LLM doesn't fill them.

## Language Note

The codebase, comments, and documentation are primarily in Chinese. The pipeline processes Chinese financial documents. When making changes, follow the existing Chinese naming conventions for print statements and comments.

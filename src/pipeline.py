"""主 Pipeline：串联全部步骤，生成最终 JSON

新流程：
1. 预处理：加载 content_list.json，按页合并为 markdown
2. 文档分类：基于第一页内容
3. 章节解析：解析目录，切分大章→小节→子节
4. 文本提取：按章节聚合文本
5. LLM 抽取：调用大模型抽取 6 类字段
6. 后处理：金额/日期/比例标准化
7. 证据索引：构建证据索引
"""

import asyncio
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import config, utils
from .chapter_mapper import ChapterMapper
from .chapter_parser import parse_chapters, get_section_text
from .document_classifier import classify_document_from_preprocessed, should_skip
from .evidence_builder import build_evidence_index, attach_evidence_ids
from .llm_extractor import LLMExtractor
from .post_processor import (
    process_compliance_items,
    process_financials,
    process_fund_raising_projects,
    process_issuer_profile,
    process_ownership_structure,
    process_risk_items,
    validate_result,
    validate_against_schema,
)
from .preprocessor import preprocess, get_first_page_text, get_total_pages, load_raw_blocks_map
from .text_extractor import extract_chapter_texts


def run_pipeline(input_dir: str, output_dir: Optional[str] = None,
                 llm_extractor: Optional[LLMExtractor] = None,
                 split_subsection_method: str = "regex") -> Dict[str, Any]:
    """端到端 Pipeline 主入口

    Args:
        input_dir: mineru 解析输出目录
        output_dir: 结果输出目录，为 None 则不保存文件
        llm_extractor: 可注入自定义 LLMExtractor（用于测试）
        split_subsection_method: 子节切分方法，"regex" 或 "model"

    Returns:
        符合 schema 的结构化结果字典
    """
    print(f"[Pipeline] 开始处理: {input_dir}")

    # 1. 预处理
    print("[Pipeline] 预处理 content_list.json...")
    preprocessed = preprocess(input_dir)
    raw_blocks_by_page = load_raw_blocks_map(input_dir)
    total_pages = get_total_pages(preprocessed)
    print(f"[Pipeline] 预处理完成，共 {total_pages} 页")

    doc_id = utils.build_document_id_from_dir(input_dir)

    # 2. 文档分类
    first_page_text = get_first_page_text(preprocessed)
    doc_type, confidence = classify_document_from_preprocessed(preprocessed)
    print(f"[Pipeline] 文档类型识别: {doc_type} (置信度: {confidence:.2f})")

    # 初始化骨架
    result = copy.deepcopy(config.EMPTY_SKELETON)
    result["document_id"] = doc_id
    result["document_type"] = doc_type

    # 推断交易所、板块、股票代码
    exchange, board = utils.infer_exchange_and_board_from_text(first_page_text)
    if exchange:
        result["issuer_profile"]["exchange"] = exchange
    if board:
        result["issuer_profile"]["board"] = board
    stock_code = utils.infer_stock_code(first_page_text)
    if stock_code:
        result["issuer_profile"]["stock_code"] = stock_code

    # 3. 如果是提示性公告等，直接返回骨架
    if should_skip(doc_type):
        print(f"[Pipeline] 文档类型为 {doc_type}，跳过抽取，输出骨架 JSON")
        if output_dir:
            _save_result(result, output_dir, doc_id)
        return result

    # 4. 解析目录与章节
    print("[Pipeline] 解析章节结构...")
    parsed = parse_chapters(preprocessed, split_subsection_method)
    chapters = parsed.get("chapters", [])
    print(f"[Pipeline] 识别到 {len(chapters)} 个大章")

    for ch in chapters:
        sections = ch.get("sections", [])
        print(f"  - {ch['heading']}: {len(sections)} 个小节")

    # 5. 提取章节文本
    print("[Pipeline] 提取章节文本...")
    chapter_texts = extract_chapter_texts(parsed)

    # 6a. 构建动态章节-字段映射
    chapter_headings = [ch["heading"] for ch in chapters]
    field_mapping = ChapterMapper(chapter_headings).build()
    if field_mapping:
        print(f"[Pipeline] 使用动态章节-字段映射（{sum(len(v) for v in field_mapping.values())} 条映射）")
    else:
        print("[Pipeline] 未匹配到章节-字段映射，使用静态关键词映射")

    # 6b. 大模型字段抽取
    print("[Pipeline] 调用大模型抽取字段...")
    extractor = llm_extractor or LLMExtractor()
    extracted, _ = extractor.extract_all(chapter_texts, field_mapping=field_mapping or None)

    # 打印抽取结果摘要
    issuer_name = extracted.get("issuer_profile", {}).get("issuer_name") if extracted.get("issuer_profile") else None
    financials_count = len(extracted.get("financials", []) or [])
    projects_count = len(extracted.get("fund_raising_projects", []) or [])
    risks_count = len(extracted.get("risk_items", []) or [])
    compliance_count = len(extracted.get("compliance_items", []) or [])
    print(
        f"[Pipeline] 抽取结果摘要: "
        f"issuer={issuer_name or 'N/A'} | "
        f"财务指标={financials_count}条 | "
        f"募投项目={projects_count}条 | "
        f"风险事项={risks_count}条 | "
        f"合规事项={compliance_count}条"
    )

    # 7. 后处理
    print("[Pipeline] 后处理抽取结果...")
    # 保存 step 2 推断的值（LLM 的 issuer_profile 会覆盖它们）
    _inferred_exchange = result["issuer_profile"].get("exchange")
    _inferred_board = result["issuer_profile"].get("board")
    _inferred_stock_code = result["issuer_profile"].get("stock_code")
    _inferred_registered_address = result["issuer_profile"].get("registered_address")

    result["issuer_profile"] = process_issuer_profile(extracted.get("issuer_profile"))
    result["ownership_structure"] = process_ownership_structure(extracted.get("ownership_structure"))
    result["financials"] = process_financials(extracted.get("financials"))
    result["fund_raising_projects"] = process_fund_raising_projects(extracted.get("fund_raising_projects"))
    result["risk_items"] = process_risk_items(extracted.get("risk_items"))
    result["compliance_items"] = process_compliance_items(extracted.get("compliance_items"))

    # 恢复 step 2 推断的值（优先于 LLM 结果，因为 LLM 可能漏填）
    if _inferred_exchange and not result["issuer_profile"].get("exchange"):
        result["issuer_profile"]["exchange"] = _inferred_exchange
    if _inferred_board and not result["issuer_profile"].get("board"):
        result["issuer_profile"]["board"] = _inferred_board
    if _inferred_stock_code and not result["issuer_profile"].get("stock_code"):
        result["issuer_profile"]["stock_code"] = _inferred_stock_code
    if _inferred_registered_address and not result["issuer_profile"].get("registered_address"):
        result["issuer_profile"]["registered_address"] = _inferred_registered_address

    # 8. 构建证据索引
    print("[Pipeline] 构建证据索引...")
    evidence_index, chapter_to_ev_ids = build_evidence_index(chapter_texts, raw_blocks_by_page)
    result["evidence_index"] = evidence_index

    # 9. 关联证据 ID
    attach_evidence_ids(result, evidence_index, chapter_to_ev_ids)

    # 10. 基础校验
    print("[Pipeline] 运行基础校验...")
    warnings = validate_result(result)
    if warnings:
        for w in warnings:
            print(f"[Pipeline] 校验警告: {w}")

    # 11. Schema 格式校验
    print("[Pipeline] 运行 schema 格式校验...")
    schema_errors = validate_against_schema(result)
    if schema_errors:
        for err in schema_errors:
            print(f"[Pipeline] Schema 错误: {err}")

    # 12. 保存结果
    if output_dir:
        _save_result(result, output_dir, doc_id)

    print("[Pipeline] 处理完成")
    return result


def _save_result(result: Dict[str, Any], output_dir: str, doc_id: str) -> None:
    """保存结果为 JSON 文件"""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / f"{doc_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[Pipeline] 结果已保存: {file_path}")


async def run_pipeline_async(input_dir: str, output_dir: Optional[str] = None,
                             llm_extractor: Optional[LLMExtractor] = None,
                             split_subsection_method: str = "regex") -> Dict[str, Any]:
    """端到端 Pipeline 主入口（异步并发版本）"""

    print(f"[Pipeline] 开始处理: {input_dir}")

    # 1. 预处理
    print("[Pipeline] 预处理 content_list.json...")
    preprocessed = preprocess(input_dir)
    raw_blocks_by_page = load_raw_blocks_map(input_dir)
    total_pages = get_total_pages(preprocessed)
    print(f"[Pipeline] 预处理完成，共 {total_pages} 页")

    doc_id = utils.build_document_id_from_dir(input_dir)

    # 2. 文档分类
    first_page_text = get_first_page_text(preprocessed)
    doc_type, confidence = classify_document_from_preprocessed(preprocessed)
    print(f"[Pipeline] 文档类型识别: {doc_type} (置信度: {confidence:.2f})")

    # 初始化骨架
    result = copy.deepcopy(config.EMPTY_SKELETON)
    result["document_id"] = doc_id
    result["document_type"] = doc_type

    # 推断交易所、板块、股票代码
    exchange, board = utils.infer_exchange_and_board_from_text(first_page_text)
    if exchange:
        result["issuer_profile"]["exchange"] = exchange
    if board:
        result["issuer_profile"]["board"] = board
    stock_code = utils.infer_stock_code(first_page_text)
    if stock_code:
        result["issuer_profile"]["stock_code"] = stock_code

    # 3. 如果是提示性公告等，直接返回骨架
    if should_skip(doc_type):
        print(f"[Pipeline] 文档类型为 {doc_type}，跳过抽取，输出骨架 JSON")
        if output_dir:
            _save_result(result, output_dir, doc_id)
        return result

    # 4. 解析目录与章节
    print("[Pipeline] 解析章节结构...")
    parsed = parse_chapters(preprocessed, split_subsection_method)
    chapters = parsed.get("chapters", [])
    print(f"[Pipeline] 识别到 {len(chapters)} 个大章")

    for ch in chapters:
        sections = ch.get("sections", [])
        print(f"  - {ch['heading']}: {len(sections)} 个小节")

    # 5. 提取章节文本
    print("[Pipeline] 提取章节文本...")
    chapter_texts = extract_chapter_texts(parsed)

    # 6a. 构建动态章节-字段映射
    chapter_headings = [ch["heading"] for ch in chapters]
    field_mapping = ChapterMapper(chapter_headings).build()
    if field_mapping:
        print(f"[Pipeline] 使用动态章节-字段映射（{sum(len(v) for v in field_mapping.values())} 条映射）")
    else:
        print("[Pipeline] 未匹配到章节-字段映射，使用静态关键词映射")

    # 6b. 大模型字段抽取（异步并发）
    print("[Pipeline] 调用大模型抽取字段（异步并发）...")
    extractor = llm_extractor or LLMExtractor()
    extracted, _ = await extractor.extract_all_async(chapter_texts, field_mapping=field_mapping or None)

    # 打印抽取结果摘要
    issuer_name = extracted.get("issuer_profile", {}).get("issuer_name") if extracted.get("issuer_profile") else None
    financials_count = len(extracted.get("financials", []) or [])
    projects_count = len(extracted.get("fund_raising_projects", []) or [])
    risks_count = len(extracted.get("risk_items", []) or [])
    compliance_count = len(extracted.get("compliance_items", []) or [])
    print(
        f"[Pipeline] 抽取结果摘要: "
        f"issuer={issuer_name or 'N/A'} | "
        f"财务指标={financials_count}条 | "
        f"募投项目={projects_count}条 | "
        f"风险事项={risks_count}条 | "
        f"合规事项={compliance_count}条"
    )

    # 7. 后处理
    print("[Pipeline] 后处理抽取结果...")
    # 保存 step 2 推断的值（LLM 的 issuer_profile 会覆盖它们）
    _inferred_exchange = result["issuer_profile"].get("exchange")
    _inferred_board = result["issuer_profile"].get("board")
    _inferred_stock_code = result["issuer_profile"].get("stock_code")
    _inferred_registered_address = result["issuer_profile"].get("registered_address")

    result["issuer_profile"] = process_issuer_profile(extracted.get("issuer_profile"))
    result["ownership_structure"] = process_ownership_structure(extracted.get("ownership_structure"))
    result["financials"] = process_financials(extracted.get("financials"))
    result["fund_raising_projects"] = process_fund_raising_projects(extracted.get("fund_raising_projects"))
    result["risk_items"] = process_risk_items(extracted.get("risk_items"))
    result["compliance_items"] = process_compliance_items(extracted.get("compliance_items"))

    # 恢复 step 2 推断的值（优先于 LLM 结果，因为 LLM 可能漏填）
    if _inferred_exchange and not result["issuer_profile"].get("exchange"):
        result["issuer_profile"]["exchange"] = _inferred_exchange
    if _inferred_board and not result["issuer_profile"].get("board"):
        result["issuer_profile"]["board"] = _inferred_board
    if _inferred_stock_code and not result["issuer_profile"].get("stock_code"):
        result["issuer_profile"]["stock_code"] = _inferred_stock_code
    if _inferred_registered_address and not result["issuer_profile"].get("registered_address"):
        result["issuer_profile"]["registered_address"] = _inferred_registered_address

    # 8. 构建证据索引
    print("[Pipeline] 构建证据索引...")
    evidence_index, chapter_to_ev_ids = build_evidence_index(chapter_texts, raw_blocks_by_page)
    result["evidence_index"] = evidence_index

    # 9. 关联证据 ID
    attach_evidence_ids(result, evidence_index, chapter_to_ev_ids)

    # 10. 基础校验
    print("[Pipeline] 运行基础校验...")
    warnings = validate_result(result)
    if warnings:
        for w in warnings:
            print(f"[Pipeline] 校验警告: {w}")

    # 11. Schema 格式校验
    print("[Pipeline] 运行 schema 格式校验...")
    schema_errors = validate_against_schema(result)
    if schema_errors:
        for err in schema_errors:
            print(f"[Pipeline] Schema 错误: {err}")

    # 12. 保存结果
    if output_dir:
        _save_result(result, output_dir, doc_id)

    print("[Pipeline] 处理完成")
    return result

"""主 Pipeline：串联全部步骤，生成最终 JSON"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from . import config, utils
from .chapter_parser import parse_toc_and_chapters, get_chapter_text
from .document_classifier import classify_document, should_skip
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
)
from .text_extractor import extract_chapter_blocks, build_chapter_text_with_evidence


def run_pipeline(input_dir: str, output_dir: Optional[str] = None, llm_extractor: Optional[LLMExtractor] = None) -> Dict[str, Any]:
    """端到端 Pipeline 主入口

    Args:
        input_dir: mineru 解析输出目录
        output_dir: 结果输出目录，为 None 则不保存文件
        llm_extractor: 可注入自定义 LLMExtractor（用于测试）

    Returns:
        符合 schema 的结构化结果字典
    """
    print(f"[Pipeline] 开始处理: {input_dir}")

    # 1. 加载数据
    mineru_data = utils.load_mineru_data(input_dir)
    md_text = mineru_data["full_md"]
    content_list_v2 = mineru_data["content_list_v2"]

    if not md_text:
        print("[Pipeline] 警告: full.md 为空")

    doc_id = utils.build_document_id_from_dir(input_dir)

    # 2. 文档分类
    doc_type, confidence = classify_document(md_text)
    print(f"[Pipeline] 文档类型识别: {doc_type} (置信度: {confidence:.2f})")

    # 初始化骨架
    result = dict(config.EMPTY_SKELETON)
    result["document_id"] = doc_id
    result["document_type"] = doc_type

    # 推断交易所和板块（从全文前5000字）
    exchange, board = utils.infer_exchange_and_board(md_text)
    if exchange:
        result["issuer_profile"]["exchange"] = exchange
    if board:
        result["issuer_profile"]["board"] = board

    # 3. 如果是提示性公告等，直接返回骨架
    if should_skip(doc_type):
        print(f"[Pipeline] 文档类型为 {doc_type}，跳过抽取，输出骨架 JSON")
        if output_dir:
            _save_result(result, output_dir, doc_id)
        return result

    # 4. 解析目录与章节
    print("[Pipeline] 解析章节结构...")
    parsed = parse_toc_and_chapters(md_text, content_list_v2)
    categories = list(parsed["chapters"].keys())
    print(f"[Pipeline] 识别到章节类别: {categories}")

    # 5. 提取章节 block 证据
    print("[Pipeline] 提取章节 block 证据...")
    chapter_blocks = extract_chapter_blocks(content_list_v2, parsed)

    # 6. 为每个类别构建文本 + 证据
    chapter_texts = {}
    chapter_evidence = {}
    for cat, blocks in chapter_blocks.items():
        text, evidence_list = build_chapter_text_with_evidence(blocks, max_chars=15000)
        chapter_texts[cat] = text
        chapter_evidence[cat] = evidence_list

    # 7. 大模型字段抽取
    print("[Pipeline] 调用大模型抽取字段...")
    extractor = llm_extractor or LLMExtractor()
    extracted = extractor.extract_all(chapter_texts)

    # 7.5 打印抽取结果摘要
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

    # 8. 后处理
    print("[Pipeline] 后处理抽取结果...")
    result["issuer_profile"] = process_issuer_profile(extracted.get("issuer_profile"))
    result["ownership_structure"] = process_ownership_structure(extracted.get("ownership_structure"))
    result["financials"] = process_financials(extracted.get("financials"))
    result["fund_raising_projects"] = process_fund_raising_projects(extracted.get("fund_raising_projects"))
    result["risk_items"] = process_risk_items(extracted.get("risk_items"))
    result["compliance_items"] = process_compliance_items(extracted.get("compliance_items"))

    # 9. 构建证据索引并关联
    print("[Pipeline] 构建证据索引...")
    evidence_index = build_evidence_index(chapter_blocks)
    result["evidence_index"] = evidence_index
    result = attach_evidence_ids(result, chapter_blocks)

    # 10. 基础校验
    print("[Pipeline] 运行基础校验...")
    warnings = validate_result(result)
    if warnings:
        for w in warnings:
            print(f"[Pipeline] 校验警告: {w}")

    # 11. 保存结果
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


async def run_pipeline_async(input_dir: str, output_dir: Optional[str] = None, llm_extractor: Optional[LLMExtractor] = None) -> Dict[str, Any]:
    """端到端 Pipeline 主入口（异步并发版本）"""

    print(f"[Pipeline] 开始处理: {input_dir}")

    mineru_data = utils.load_mineru_data(input_dir)
    md_text = mineru_data["full_md"]
    content_list_v2 = mineru_data["content_list_v2"]

    if not md_text:
        print("[Pipeline] 警告: full.md 为空")

    doc_id = utils.build_document_id_from_dir(input_dir)

    doc_type, confidence = classify_document(md_text)
    print(f"[Pipeline] 文档类型识别: {doc_type} (置信度: {confidence:.2f})")

    result = dict(config.EMPTY_SKELETON)
    result["document_id"] = doc_id
    result["document_type"] = doc_type

    exchange, board = utils.infer_exchange_and_board(md_text)
    if exchange:
        result["issuer_profile"]["exchange"] = exchange
    if board:
        result["issuer_profile"]["board"] = board

    if should_skip(doc_type):
        print(f"[Pipeline] 文档类型为 {doc_type}，跳过抽取，输出骨架 JSON")
        if output_dir:
            _save_result(result, output_dir, doc_id)
        return result

    print("[Pipeline] 解析章节结构...")
    parsed = parse_toc_and_chapters(md_text, content_list_v2)
    categories = list(parsed["chapters"].keys())
    print(f"[Pipeline] 识别到章节类别: {categories}")

    print("[Pipeline] 提取章节 block 证据...")
    chapter_blocks = extract_chapter_blocks(content_list_v2, parsed)

    chapter_texts = {}
    chapter_evidence = {}
    for cat, blocks in chapter_blocks.items():
        text, evidence_list = build_chapter_text_with_evidence(blocks, max_chars=15000)
        chapter_texts[cat] = text
        chapter_evidence[cat] = evidence_list

    print("[Pipeline] 调用大模型抽取字段（异步并发）...")
    extractor = llm_extractor or LLMExtractor()
    extracted = await extractor.extract_all_async(chapter_texts)

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

    print("[Pipeline] 后处理抽取结果...")
    result["issuer_profile"] = process_issuer_profile(extracted.get("issuer_profile"))
    result["ownership_structure"] = process_ownership_structure(extracted.get("ownership_structure"))
    result["financials"] = process_financials(extracted.get("financials"))
    result["fund_raising_projects"] = process_fund_raising_projects(extracted.get("fund_raising_projects"))
    result["risk_items"] = process_risk_items(extracted.get("risk_items"))
    result["compliance_items"] = process_compliance_items(extracted.get("compliance_items"))

    print("[Pipeline] 构建证据索引...")
    # 9. 构建证据索引并关联
    evidence_index = build_evidence_index(chapter_blocks)
    result["evidence_index"] = evidence_index
    result = attach_evidence_ids(result, chapter_blocks)

    print("[Pipeline] 运行基础校验...")
    warnings = validate_result(result)
    if warnings:
        for w in warnings:
            print(f"[Pipeline] 校验警告: {w}")

    if output_dir:
        _save_result(result, output_dir, doc_id)

    print("[Pipeline] 处理完成")
    return result

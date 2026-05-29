"""手动运行入口脚本"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.pipeline import run_pipeline, run_pipeline_async


def is_document_dir(directory: Path) -> bool:
    """判断目录是否为单个文档目录（包含 content_list.json 文件）"""
    # 检查是否有 *_content_list.json 文件
    if list(directory.glob("*_content_list.json")):
        return True
    # 检查是否有 content_list.json 文件
    if (directory / "content_list.json").exists():
        return True
    return False


def find_document_dirs(input_dir: Path) -> List[Path]:
    """查找输入目录下所有包含 content_list.json 的文档目录（递归）"""
    doc_dirs = set()
    for item in input_dir.rglob("*_content_list.json"):
        doc_dirs.add(item.parent)
    for item in input_dir.rglob("content_list.json"):
        doc_dirs.add(item.parent)
    return sorted(doc_dirs)


def main():
    parser = argparse.ArgumentParser(description="金融长文档字段抽取 Pipeline")
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        help="mineru 解析输出目录路径，支持单个文档目录或包含多个文档的父目录",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="results",
        help="结果输出目录，默认 results/",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="InternLM API Key（默认读取环境变量 INTERNLM_API_KEY）",
    )
    parser.add_argument(
        "--async_mode",
        action="store_true",
        default=True,
        help="使用异步并发模式（大幅提升请求效率）",
    )

    args = parser.parse_args()

    if args.api_key:
        import os
        os.environ["INTERNLM_API_KEY"] = args.api_key

    input_path = Path(args.input_dir)

    # 检测是单个文档目录还是父目录
    if is_document_dir(input_path):
        # 单个文档目录，按原有逻辑处理
        doc_dirs = [input_path]
    else:
        # 父目录，查找所有文档子目录
        doc_dirs = find_document_dirs(input_path)
        if not doc_dirs:
            print(f"错误：在 {args.input_dir} 下未找到任何包含 content_list.json 的文档目录")
            sys.exit(1)
        print(f"找到 {len(doc_dirs)} 个文档目录，开始批量处理...")

    # 处理所有文档目录
    results = []
    for i, doc_dir in enumerate(doc_dirs, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(doc_dirs)}] 处理文档: {doc_dir.name}")
        print(f"{'='*60}")

        try:
            if args.async_mode:
                print("使用异步并发模式")
                result = asyncio.run(run_pipeline_async(str(doc_dir), args.output_dir))
            else:
                print("使用同步模式")
                result = run_pipeline(str(doc_dir), args.output_dir)

            results.append({
                "document_id": result['document_id'],
                "document_type": result['document_type'],
                "status": "success"
            })
            print(f"处理完成，document_id={result['document_id']}, document_type={result['document_type']}")
        except Exception as e:
            print(f"处理失败: {e}")
            results.append({
                "document_id": doc_dir.name,
                "document_type": "unknown",
                "status": "failed",
                "error": str(e)
            })

    # 打印汇总信息
    if len(doc_dirs) > 1:
        print(f"\n{'='*60}")
        print(f"批量处理完成，共处理 {len(doc_dirs)} 个文档")
        print(f"{'='*60}")
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = sum(1 for r in results if r['status'] == 'failed')
        print(f"成功: {success_count} 个")
        print(f"失败: {failed_count} 个")
        if failed_count > 0:
            print("\n失败的文档:")
            for r in results:
                if r['status'] == 'failed':
                    print(f"  - {r['document_id']}: {r.get('error', '未知错误')}")


if __name__ == "__main__":
    main()

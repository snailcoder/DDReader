"""手动运行入口脚本"""

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.pipeline import run_pipeline, run_pipeline_async


def main():
    parser = argparse.ArgumentParser(description="金融长文档字段抽取 Pipeline")
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        help="mineru 解析输出目录路径，例如 data/mineru-output/xxx",
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

    if args.async_mode:
        result = asyncio.run(run_pipeline_async(args.input_dir, args.output_dir))
    else:
        result = run_pipeline(args.input_dir, args.output_dir)

    print(f"\n处理完成，document_id={result['document_id']}, document_type={result['document_type']}")


if __name__ == "__main__":
    main()

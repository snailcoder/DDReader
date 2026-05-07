# 运行 DrDD 管道
# 支持单个文档目录或包含多个文档的父目录
# 用法: ./run.sh <目录路径>
python src/run.py --output_dir=results/ --input_dir "$1"

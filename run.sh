# 运行 DrDD 管道
# 支持单个文档目录或包含多个文档的父目录
# 用法: ./run.sh <目录路径>
input_dir="$1"
output_dir="$2"
python src/run.py --input_dir "$input_dir" --output_dir="$output_dir"

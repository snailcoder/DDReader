# 金融长文档字段抽取 Pipeline —— 部署手册

## 快速部署检查清单

- [ ] Python 3.10+ 已安装
- [ ] `python3 -m venv .venv` 虚拟环境已创建
- [ ] `source .venv/bin/activate` 已激活
- [ ] `pip install openai python-dotenv` 已完成
- [ ] `uv pip install -U "mineru[all]"` mineru 已安装
- [ ] 或 `docker compose --profile full up -d` Docker 部署就绪
- [ ] `.env` 文件中已配置有效的 API Key
- [ ] `python src/run.py --input_dir data/mineru-output/<id> --output_dir results/` CLI 模式验证通过
- [ ] （可选）`mineru-api --host 127.0.0.1 --port 8000` 解析服务已启动
- [ ] （可选）`uvicorn src.api:app --host 0.0.0.0 --port 8001` API 服务已启动
- [ ] `curl http://localhost:8001/health` 健康检查通过

## 一、系统架构

```
┌──────────┐    PDF    ┌──────────┐  content_list.json  ┌──────────┐  JSON  ┌──────────┐
│  PDF 文件 │ ────────> │ mineru   │ ──────────────────> │ DrDD API │ ──────> │ 客户端   │
│           │          │ (解析)   │                     │ (抽取)   │        │          │
└──────────┘           └──────────┘                     └──────────┘        └──────────┘
                              ^                                ^
                              │                                │
                              │                          ┌─────┴──────┐
                              │                          │  LLM API   │
                              │                          │ (第三方)    │
                              │                          └────────────┘
                        本地部署服务                        外部或自部署
```

系统包含三个组件：

| 组件 | 角色 | 部署方式 |
|------|------|---------|
| **mineru** | PDF → `*_content_list.json` 解析 | 本地进程或服务（`mineru-api`） |
| **DrDD Pipeline** | 章节解析 + LLM 字段抽取 → 结构化 JSON | CLI 脚本或 FastAPI 服务 |
| **LLM API** | 大模型推理（DeepSeek / InternLM 等） | 第三方 API（需 API Key） |

---

## 二、环境要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Linux / macOS / Windows | Linux / macOS |
| Python | 3.10+ | 3.12+ |
| 内存 | 8 GB | 16 GB |
| 磁盘 | 20 GB（含 mineru 模型） | 50 GB+（SSD 更佳） |
| GPU（可选） | — | 8 GB+ VRAM（加速 mineru 解析） |

---

## 三、安装步骤

### 3.1 克隆项目

```bash
git clone <repo_url> /path/to/DrDD
cd /path/to/DrDD
```

### 3.2 Python 虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.3 安装 mineru（PDF 解析引擎）

```bash
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple
pip install uv -i https://mirrors.aliyun.com/pypi/simple
uv pip install -U "mineru[all]" -i https://mirrors.aliyun.com/pypi/simple
```

> 国内用户推荐使用阿里云镜像加速。如遇网络问题，可尝试 `export UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple`。

### 3.4 安装 DrDD Pipeline 依赖

```bash
pip install openai python-dotenv
```

验证安装：

```bash
python -c "from src.pipeline import run_pipeline; print('OK')"
```

### 3.5 安装 API 服务依赖（可选，仅 API 模式需要）

```bash
pip install fastapi uvicorn httpx python-multipart
```

### 3.6 配置 API Key

创建或编辑项目根目录下的 `.env` 文件（参考 `.env.example`）：

```ini
# DeepSeek（当前配置）
API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
API_BASE=https://api.deepseek.com
MODEL_NAME=deepseek-chat

# 或 InternLM
# API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# API_BASE=https://chat.intern-ai.org.cn/api/v1
# MODEL_NAME=intern-latest
```

也支持通过环境变量设置：

```bash
export API_KEY="sk-..."
export API_BASE="https://api.deepseek.com"
export MODEL_NAME="deepseek-chat"
```

### 3.7 Docker 部署（可选）

```bash
# 1. 编辑配置
cp .env.example .env
# 编辑 .env 填入 API_KEY

# 2. 启动完整服务（含 mineru-api）
docker compose --profile full up -d

# 3. 仅启动 DrDD API（需自行启动 mineru-api）
docker compose up -d drdd-api
```

---

## 四、CLI 模式使用（无需 API 服务）

### 4.1 准备输入数据

mineru 解析 PDF 后，每个文档生成一个独立目录，内含 `*_content_list.json`：

```bash
# GPU 环境
mineru -p /path/to/招股说明书.pdf -o /path/to/output/

# CPU 环境
mineru -p /path/to/招股说明书.pdf -o /path/to/output/ -b pipeline
```

输出目录示例：

```
output/
└── 招股说明书_1224957012/
    └── 1224957012_xxx_content_list.json
```

### 4.2 单文档抽取

```bash
python src/run.py \
  --input_dir /path/to/output/招股说明书_1224957012 \
  --output_dir results/
```

输出：`results/招股说明书_1224957012.json`

### 4.3 批量抽取

传入父目录，自动遍历所有子目录：

```bash
python src/run.py \
  --input_dir /path/to/output/ \
  --output_dir results/
```

### 4.4 快捷脚本

```bash
./run.sh /path/to/output/招股说明书_1224957012
```

---

## 五、API 模式部署

### 5.1 启动 mineru 解析服务

mineru 内置 FastAPI 服务，作为 PDF 解析的独立后端：

```bash
# 默认端口 8000
mineru-api --host 127.0.0.1 --port 8000
```

环境变量：

```bash
# 任务结果保留时间（秒，默认 86400 = 24 小时）
export MINERU_API_TASK_RETENTION_SECONDS=86400

# 启用 API 文档
export MINERU_API_ENABLE_FASTAPI_DOCS=true
```

验证服务：`curl http://127.0.0.1:8000/health`

### 5.2 启动 DrDD API 服务

**方式一：Docker（推荐）**

```bash
docker compose up -d drdd-api
```

**方式二：本地 Python 直接启动**

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8001 --workers 2
```

或开发模式（代码修改后自动重载）：

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8001 --reload
```

DrDD API 环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINERU_API_URL` | `http://127.0.0.1:8000` | mineru-api 服务地址 |
| `MINERU_PARSE_BACKEND` | `pipeline` | mineru 解析后端（`pipeline` / `vlm` / `hybrid`） |
| `DRDD_BASE_DIR` | `系统临时目录/drdd` | 数据根目录（任务数据、工作目录） |
| `DRDD_TASKS_DIR` | `{DRDD_BASE_DIR}/tasks` | 任务元数据和结果持久化目录 |

### 5.3 访问 Web 前端

启动后打开 `http://localhost:8001` 即可访问前端页面：
- 上传 PDF → mineru 解析 → 字段抽取 → 结构化展示
- 上传 `*_content_list.json` → 跳过 mineru → 直接字段抽取（适用于已有解析结果的文档）

### 5.5 部署验证脚本

```bash
bash scripts/verify_deployment.sh
```

脚本自动检查：Python 版本、依赖、API Key 配置、mineru-api 连通性、DrDD API 健康状态，并提交示例 JSON 进行端到端验证。

```bash
# 健康检查
curl http://127.0.0.1:8001/health
# 预期返回: {"status": "ok", "version": "1.0.0"}
```

---

## 六、API 接口说明

### 6.1 提交抽取任务

```bash
curl -X POST http://127.0.0.1:8001/extract \
  -F "file=@/path/to/招股说明书.pdf"
```

成功响应（202 Accepted）：

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 6.2 查询任务状态

```bash
curl http://127.0.0.1:8001/status/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

处理中：

```json
{
  "status": "processing"
}
```

完成：

```json
{
  "status": "done",
  "result": {
    "document_id": "招股说明书_1224957012",
    "document_type": "招股说明书",
    "issuer_profile": { ... },
    "financials": [ ... ],
    "risk_items": [ ... ],
    "evidence_index": [ ... ]
  }
}
```

失败：

```json
{
  "status": "failed",
  "error": "mineru 解析失败: PDF 文件损坏"
}
```

### 6.3 完整使用示例

```bash
# 1. 提交任务
TASK_ID=$(curl -s -X POST http://localhost:8001/extract \
  -F "file=@招股说明书.pdf" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
echo "Task ID: $TASK_ID"

# 2. 轮询结果
while true; do
  RESP=$(curl -s http://localhost:8001/status/$TASK_ID)
  STATUS=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "Status: $STATUS"
  if [ "$STATUS" = "done" ] || [ "$STATUS" = "failed" ]; then
    echo "$RESP" | python3 -m json.tool > result.json
    break
  fi
  sleep 5
done

# 3. 查看结果
cat result.json
```

---

## 七、环境变量参考

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `API_KEY` | `""` | LLM API 密钥（必填） |
| `API_BASE` | `https://chat.intern-ai.org.cn/api/v1` | LLM API 地址 |
| `MODEL_NAME` | `intern-latest` | 模型名称 |
| `API_BASE`（从 `.env` 读取） | — | 通过 `dotenv` 自动加载 |
| `MINERU_API_URL` | `http://127.0.0.1:8000` | mineru-api 服务地址（DrDD API 使用） |
| `MINERU_PARSE_BACKEND` | `pipeline` | mineru 解析后端（DrDD API 使用） |
| `DRDD_BASE_DIR` | `系统临时目录/drdd` | DrDD 数据根目录（任务、工作数据） |
| `DRDD_TASKS_DIR` | `{DRDD_BASE_DIR}/tasks` | 任务元数据和结果的持久化目录 |
| `MINERU_API_TASK_RETENTION_SECONDS` | `86400` | mineru-api 任务保留时间 |
| `MINERU_API_ENABLE_FASTAPI_DOCS` | `true` | 是否启用 mineru API 文档 |

---

## 八、运维注意事项

### 8.1 进程管理

推荐使用 `tmux` 或 `supervisor` 管理长期运行的服务进程：

```bash
# tmux 示例
tmux new -s mineru   # Terminal 1: mineru-api
tmux new -s drdd     # Terminal 2: DrDD API

# supervisor 配置（/etc/supervisor/conf.d/drdd.conf）
# [program:drdd-api]
# command=/path/to/.venv/bin/uvicorn src.api:app --host 0.0.0.0 --port 8001
# directory=/path/to/DrDD
# user=www-data
# autostart=true
# autorestart=true
```

### 8.2 日志查看

- DrDD Pipeline 日志：输出到 stdout（CLI 模式）或 uvicorn 日志（API 模式）
- mineru-api 日志：默认输出到 stdout

### 8.3 临时文件

- DrDD API 数据存储在 `DRDD_BASE_DIR`（默认系统临时目录 `/tmp/drdd/`），包含：
  - `work/` — 处理中的任务文件（任务完成后自动清理）
  - `tasks/` — 已完成任务的元数据与结果 JSON（长期保留）
- mineru-api 处理结果存储在 `./output` 目录（默认 24 小时后自动清理）

### 8.4 资源监控

- LLM API 调用有 30 并发限流 + 2s 最小间隔，避免触发限频
- mineru GPU 模式需要约 6 GB+ VRAM，CPU 模式需要 16 GB+ 内存

### 8.5 GPU/CPU 切换

```bash
# GPU（默认，需 NVIDIA GPU + CUDA）
mineru-api --host 0.0.0.0 --port 8000

# CPU 模式（指定 pipeline 后端）
mineru-api --host 0.0.0.0 --port 8000 -b pipeline
```

---

## 九、常见问题

### Q1: API Key 未设置

```
ValueError: API Key 未设置，请配置环境变量 INTERNLM_API_KEY
```

**解决**：检查 `.env` 文件中的 `API_KEY` 是否正确设置，或通过 `export API_KEY=sk-xxx` 传入。

### Q2: mineru-api 连接失败

```
ConnectError: Connection refused to 127.0.0.1:8000
```

**解决**：确认 mineru-api 服务已启动。先启动 mineru-api，再启动 DrDD API。

### Q3: 请求超时

```
LLM API 调用失败（重试3次）: timeout
```

**解决**：
- 检查网络连通性
- 降低并发数（修改 `llm_client.py` 中 `_semaphore` 的值）
- 增加超时时间（`config.py` 中 `REQUEST_TIMEOUT`）

### Q4: 内存不足

```bash
# 切换到 CPU 模式的 pipeline 后端
mineru -p <pdf> -o <out> -b pipeline

# 降低 chunk 大小（修改 llm_extractor.py 中 CHUNK_MAX_CHARS）
```

### Q5: macOS GPU 加速

macOS Apple Silicon（M 系列芯片）可通过 MLX 加速：
```bash
mineru -p <pdf> -o <out> -b hybrid-auto-engine
```

mineru 会自动检测并启用 MLX 后端。

---

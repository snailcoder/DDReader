#!/usr/bin/env bash
set -euo pipefail

# DrDD 部署验证脚本
# 用法: bash scripts/verify_deployment.sh

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS() { echo -e "  ${GREEN}✓${NC} $1"; }
WARN() { echo -e "  ${YELLOW}⚠${NC} $1"; }
FAIL() { echo -e "  ${RED}✗${NC} $1"; failures=$((failures+1)); }

failures=0

echo ""
echo "════════════════════════════════════════════"
echo "  DrDD 部署验证"
echo "════════════════════════════════════════════"
echo ""

# ── Python ──
echo "【1/6】Python 环境"
if command -v python3 &>/dev/null; then
    ver=$(python3 --version 2>&1 | awk '{print $2}')
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
        PASS "Python $ver"
    else
        FAIL "Python $ver (需要 >= 3.10)"
    fi
else
    FAIL "python3 未安装"
fi
echo ""

# ── 依赖导入 ──
echo "【2/6】依赖检查"
for mod in openai fastapi uvicorn httpx jieba jsonschema; do
    if python3 -c "import $mod" 2>/dev/null; then
        PASS "模块 $mod"
    else
        FAIL "模块 $mod 未安装 (pip install -r requirements.txt)"
    fi
done
echo ""

# ── .env ──
echo "【3/6】API Key 检查"
if [ -f .env ]; then
    if grep -q "^API_KEY=" .env && ! grep -q "^API_KEY=$" .env && ! grep -q "^API_KEY=sk-your" .env; then
        PASS ".env 中 API_KEY 已配置"
    else
        WARN ".env 中 API_KEY 为空或为模板值"
    fi
else
    WARN ".env 文件不存在 (cp .env.example .env 后编辑)"
fi
echo ""

# ── mineru-api ──
echo "【4/6】mineru-api 连通性"
MINERU_URL="${MINERU_API_URL:-http://127.0.0.1:8000}"
if curl -sf "$MINERU_URL/health" >/dev/null 2>&1; then
    PASS "mineru-api 可达 ($MINERU_URL)"
else
    WARN "mineru-api 不可达 ($MINERU_URL) — 仅 PDF 上传会失败，JSON 上传不受影响"
fi
echo ""

# ── DrDD API ──
echo "【5/6】DrDD API 健康检查"
if curl -sf http://127.0.0.1:8001/health 2>/dev/null; then
    PASS "DrDD API 运行中 (http://localhost:8001)"
else
    WARN "DrDD API 未运行 (启动: uvicorn src.api:app --host 0.0.0.0 --port 8001)"
fi
echo ""

# ── 端到端验证（使用示例 JSON）──
echo "【6/6】端到端验证"
SAMPLE=$(find data/mineru-output -name "*_content_list.json" 2>/dev/null | head -1)
if [ -n "$SAMPLE" ] && curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "  提交示例 JSON 进行字段抽取..."
    TASK_ID=$(curl -sf -X POST http://127.0.0.1:8001/extract \
        -F "file=@$SAMPLE" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))" 2>/dev/null || echo "")
    if [ -n "$TASK_ID" ]; then
        PASS "任务提交成功 (task_id: $TASK_ID)"
        echo "  等待处理..."
        for i in $(seq 1 30); do
            RESP=$(curl -sf "http://127.0.0.1:8001/status/$TASK_ID" 2>/dev/null || echo '{"status":"unknown"}')
            STATUS=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "unknown")
            if [ "$STATUS" = "done" ]; then
                PASS "端到端抽取完成"
                break
            elif [ "$STATUS" = "failed" ]; then
                WARN "端到端失败: $(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))")"
                break
            fi
            sleep 2
        done
    else
        WARN "任务提交失败 — 跳过端到端验证"
    fi
else
    WARN "缺少示例数据或 DrDD API 未运行 — 跳过端到端验证"
fi
echo ""

# ── 汇总 ──
echo "════════════════════════════════════════════"
if [ "$failures" -gt 0 ]; then
    echo -e "  结果: ${RED}$failures 项失败${NC}，请根据提示修复"
    exit 1
else
    echo -e "  结果: ${GREEN}全部通过${NC}"
    echo "  部署就绪"
fi
echo "════════════════════════════════════════════"

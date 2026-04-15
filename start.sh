#!/bin/bash
# ============================================================
# Hyper-Network Analyzer — 一键启动脚本
# 用法：bash start.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_DIR="$SCRIPT_DIR/qky项目文件"
VUE_DIR="$SCRIPT_DIR/hyper-viz"

echo "============================================"
echo "  Hyper-Network Analyzer"
echo "============================================"
echo ""

# ── 检查 Python ──────────────────────────────────────────────
PYTHON_BIN=$(which python3 2>/dev/null || which python 2>/dev/null || echo "")
if [ -z "$PYTHON_BIN" ]; then
  echo "❌ 未找到 Python，请先安装 Python 3.8+"
  exit 1
fi
echo "✓ Python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

# ── 检查 Node.js ─────────────────────────────────────────────
NODE_BIN=$(which node 2>/dev/null || echo "")
if [ -z "$NODE_BIN" ]; then
  echo "❌ 未找到 Node.js，请先安装 Node.js 18+"
  exit 1
fi
echo "✓ Node.js: $NODE_BIN ($(node --version))"

# ── 安装前端依赖（如果需要）──────────────────────────────────
if [ ! -d "$VUE_DIR/node_modules" ]; then
  echo ""
  echo "📦 安装前端依赖..."
  cd "$VUE_DIR" && npm install
fi

# ── 检查 Python 依赖 ─────────────────────────────────────────
echo ""
echo "🔍 检查 Python 依赖..."
MISSING_DEPS=""
for pkg in networkx pandas numpy matplotlib Pillow; do
  case $pkg in
    Pillow) import_name="PIL" ;;
    *) import_name=$(echo "$pkg" | tr '[:upper:]' '[:lower:]') ;;
  esac
  if ! $PYTHON_BIN -c "import $import_name" 2>/dev/null; then
    MISSING_DEPS="$MISSING_DEPS $pkg"
  fi
done

if [ -n "$MISSING_DEPS" ]; then
  echo "⚠️  缺少 Python 依赖：$MISSING_DEPS"
  echo "   正在安装..."
  $PYTHON_BIN -m pip install $MISSING_DEPS -q
fi
echo "✓ Python 依赖已就绪"

# ── 启动后端服务 ─────────────────────────────────────────────
echo ""
echo "🚀 启动 Python 分析后端 (端口 5001)..."
cd "$PYTHON_DIR"
$PYTHON_BIN server.py --port 5001 --host 0.0.0.0 &
BACKEND_PID=$!
echo "   后端 PID: $BACKEND_PID"

# 等待后端就绪
sleep 2
if ! kill -0 $BACKEND_PID 2>/dev/null; then
  echo "❌ 后端启动失败，请检查 server.py"
  exit 1
fi
echo "✓ 后端服务已启动: http://127.0.0.1:5001"

# ── 启动前端开发服务器 ────────────────────────────────────────
echo ""
echo "🌐 启动前端开发服务器..."
cd "$VUE_DIR"
npm run dev &
FRONTEND_PID=$!
echo "   前端 PID: $FRONTEND_PID"

echo ""
echo "============================================"
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "未知")
echo "  ✅ 服务已启动！"
echo ""
echo "  本机访问:   http://localhost:5173"
echo "  局域网访问: http://${LOCAL_IP}:5173  ← 手机/平板用这个"
echo "  后端接口:   http://${LOCAL_IP}:5001"
echo ""
echo "  使用方法："
echo "  1. 手机连接同一 WiFi，浏览器打开 http://${LOCAL_IP}:5173"
echo "  2. 点击顶部 [Import CSV] 按钮上传 CSV 文件"
echo "  3. 等待分析完成（进度条显示），约 2~5 分钟"
echo "  4. 分析完成后各 Tab 自动刷新展示结果"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "============================================"

# ── 等待并清理 ────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "⏹ 正在停止服务..."
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  echo "✓ 已停止"
  exit 0
}
trap cleanup INT TERM

wait

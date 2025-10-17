#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[bootstrap] 检查 pnpm..."
if ! command -v pnpm >/dev/null 2>&1; then
  echo "[bootstrap] 请先安装 pnpm (https://pnpm.io/installation)" >&2
  exit 1
fi

echo "[bootstrap] 安装前端依赖 (web)..."
pnpm --filter web install

echo "[bootstrap] 准备 Python 虚拟环境 (python/.venv)..."
cd "$ROOT/python"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
echo "[bootstrap] 安装后端依赖 (含开发依赖)..."
python -m pip install -e .[dev]
deactivate

cd "$ROOT"

if [[ ! -f .env ]] && [[ -f .env.example ]]; then
  echo "[bootstrap] 生成本地 .env（来自 .env.example）"
  cp .env.example .env
fi

if [[ ! -f web/.env ]] && [[ -f web/.env.example ]]; then
  echo "[bootstrap] 生成本地 web/.env（来自 web/.env.example）"
  cp web/.env.example web/.env
fi

echo "[bootstrap] ✅ 初始化完成，建议运行：\n  ./start.sh"

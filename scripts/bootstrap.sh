#!/usr/bin/env bash
set -euo pipefail

if ! command -v pnpm >/dev/null 2>&1; then
  echo "[bootstrap] 请先安装 pnpm (https://pnpm.io/installation)" >&2
  exit 1
fi

echo "[bootstrap] 安装依赖..."
pnpm install

echo "[bootstrap] 检查 mpv 可用性..."
if ! command -v mpv >/dev/null 2>&1; then
  echo "[bootstrap] 未检测到 mpv，请使用 'brew install mpv' 安装" >&2
else
  echo "[bootstrap] mpv 已安装"
fi

echo "[bootstrap] 检查 yt-dlp 可用性..."
if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "[bootstrap] 未检测到 yt-dlp，可使用 'brew install yt-dlp' 安装" >&2
else
  echo "[bootstrap] yt-dlp 已安装"
fi

echo "[bootstrap] ✅ 初始化完成"

#!/usr/bin/env bash
# 祥旺库存工具 —— macOS / Linux 启动脚本
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

VPY=".venv/bin/python3"
[ -x "$VPY" ] || VPY=".venv/bin/python"

if [ ! -x "$VPY" ]; then
  echo
  echo "  还没装好运行环境，正在自动安装（第一次需要联网）……"
  echo
  PY=""
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "  [x] 没找到 Python。"
    echo "      • 用 WorkBuddy 的话，先打开一次 WorkBuddy 再回来重试；"
    echo "      • 否则去 https://www.python.org/downloads/ 安装，"
    echo "        Mac 也可以先在终端执行： xcode-select --install"
    exit 1
  fi
  "$PY" tools/bootstrap.py || exit 1
fi

"$VPY" tools/banner.py step3
"$VPY" -m wangxiang sync --ask "$@"
[ -d "output/sync" ] && open "output/sync" 2>/dev/null || true


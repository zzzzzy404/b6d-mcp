#!/bin/sh
# 启动 b6d MCP 服务（stdio）。Codex 从图形界面启动时 PATH 可能不含 uv，按常见安装位置找一遍。
# 首次启动 uv 会在插件目录下建 .venv 并安装依赖，之后秒开。
set -e

PLUGIN_DIR=$(cd "$(dirname "$0")/.." && pwd)

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! UV=$(find_uv); then
  echo "b6d 插件需要 uv：请先运行 curl -LsSf https://astral.sh/uv/install.sh | sh ，然后重启 Codex" >&2
  exit 1
fi

exec "$UV" run --project "$PLUGIN_DIR" --frozen --quiet --no-dev b6d-mcp

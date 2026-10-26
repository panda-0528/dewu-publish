#!/usr/bin/env sh
# 一键流水线：env-check -> scan -> import -> gen-copy(GLM) -> validate -> publish
# 用法: GLM_API_KEY=xxx sh run.sh <素材目录> [额外参数，如 --skip-import --resume --reuse-config]
# stdout 仅一个 JSON；退出码 0 全部成功 / 1 工具错误 / 2 部分失败
set -u
SRC="${1:?用法: sh run.sh <素材目录> [额外参数]}"
shift
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python}"
exec "$PY" "$HERE/scripts/dewu_tool.py" run --src "$SRC" --config "$HERE/work/posts.json" "$@"

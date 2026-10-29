#!/usr/bin/env sh
# 一键流水线：env-check -> scan -> import -> validate -> publish
# 用法: sh run.sh [素材目录] [额外参数，如 --skip-import --resume]
# stdout 仅一个 JSON；退出码 0 全部成功 / 1 工具错误 / 2 部分失败
set -u
SRC="${1:-}"
if [ -z "$SRC" ]; then
    if [ -d "/d/IMAGE/10.28" ] || [ -d "D:/IMAGE/10.28" ]; then
        SRC="D:/IMAGE/10.28"
    elif [ -d "/e/测试" ] || [ -d "E:/测试" ]; then
        SRC="E:/测试"
    else
        echo "用法: sh run.sh <素材目录> [额外参数]" >&2
        exit 1
    fi
else
    shift
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python}"
exec "$PY" "$HERE/scripts/dewu_tool.py" run --src "$SRC" --config "$HERE/work/posts.json" --reuse-config "$@"

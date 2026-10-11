#!/usr/bin/env bash
# 打运行包（zip）。
#
# **只装运行必需**：src/ config/ prompts/ skills/ + 入口脚本 + requirements。
# 刻意排除：
#   tests/           —— 需要 pytest，且含大量评测用例（约 1.1MB）
#   docs/            —— 运行时代码从不读它（已核实：无任何引用），
#                      且其中 eval-*.json 依赖 tests/ 才能读
#   web_3d_client/   —— 前端源码，构建产物已内置在 src/web_3d/static/
#   .git/ __pycache__/ .pytest_cache/ .coverage
#
# 用法：.github/scripts/package.sh <输出目录> <版本号>
# 产物：<输出目录>/llm-xiangqi-<版本号>.zip
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "用法: $0 <输出目录> <版本号>" >&2
    exit 2
fi

OUT_DIR="$1"
VERSION="$2"
STAGE_NAME="llm-xiangqi-${VERSION}"
ARCHIVE="${OUT_DIR}/${STAGE_NAME}.zip"

# 仓库根 = 脚本所在目录（.github/scripts/）的上两级
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [ ! -d "src" ] || [ ! -f "game.py" ]; then
    echo "错误：未在仓库根执行（找不到 src/ 或 game.py）" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PKG="${STAGE}/${STAGE_NAME}"
mkdir -p "$PKG"

# --- 运行必需内容（逐项而非通配，避免误纳入新加的缓存目录） ---
copy_dir() {
    if [ -d "$1" ]; then
        cp -r "$1" "$PKG/"
    else
        echo "警告：跳过不存在的目录 $1" >&2
    fi
}
copy_file() {
    if [ -f "$1" ]; then
        cp "$1" "$PKG/"
    else
        echo "警告：跳过不存在的文件 $1" >&2
    fi
}

copy_dir src
copy_dir config
copy_dir prompts
copy_dir skills
copy_file requirements.txt
copy_file game.py
copy_file main.py
copy_file run_web.py
copy_file README.md
copy_file LICENSE

# --- 清理不该进包的残留 ---
find "$PKG" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -delete 2>/dev/null || true

# --- 密钥绝不入包（.gitignore 之外的第二道保险） ---
# 即便有人在 config/ 下放了 api.txt，也要在这里拦下。
find "$PKG" -type f \( \
    -iname 'api.txt' -o -iname 'test_api.txt' -o -iname '*_api.txt' \
    -o -iname '*.pem' -o -iname '*.key' -o -iname '*.secret' \
    -o -iname '.env' -o -iname '.env.*' \
\) -print -delete 2>/dev/null || true

# 包内自检：确认没有密钥文件残留
if grep -rIlE 'sk-[A-Za-z0-9]{16,}' "$PKG" >/dev/null 2>&1; then
    echo "错误：打包内容中检测到疑似密钥字面量，已中止" >&2
    grep -rIlE 'sk-[A-Za-z0-9]{16,}' "$PKG" >&2 || true
    exit 1
fi

# --- 打 zip：顶层目录是 llm-xiangqi-<版本>，解压即用 ---
( cd "$STAGE" && zip -qr "$ARCHIVE" "$STAGE_NAME" )

SIZE_KB="$(du -k "$ARCHIVE" | cut -f1)"
echo "已打包: $ARCHIVE (${SIZE_KB} KB)"
echo "包含内容:"
( cd "$PKG" && find . -maxdepth 1 -mindepth 1 | sort | sed 's/^/  /' )
#!/bin/bash
# scripts/build-python.sh
# 打包 Python 后端为可执行文件
# 输出到 electron/resources/python-backend/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/backend"
OUTPUT_DIR="$ROOT_DIR/electron/resources/python-backend"

echo "📦 开始打包 Python 后端..."
echo "   后端目录：$BACKEND_DIR"
echo "   输出目录：$OUTPUT_DIR"

# 确保输出目录存在
mkdir -p "$OUTPUT_DIR"

# 进入后端目录
cd "$BACKEND_DIR"

# 安装依赖（如果没有）
if ! command -v pyinstaller &> /dev/null; then
  echo "⚙️  安装 PyInstaller..."
  pip install pyinstaller
fi

# 执行打包
echo "⚙️  执行 PyInstaller..."
pyinstaller backend.spec --clean --distpath "$OUTPUT_DIR"

echo "✅ Python 后端打包完成"
echo "   产物：$OUTPUT_DIR/backend"
ls -lh "$OUTPUT_DIR/"
#!/bin/bash
# scripts/build-python-mac.sh
# 在 macOS 上将 Flask 后端打包为单目录可执行文件
set -e

echo "🐍 Building Python backend for macOS..."

# 取脚本所在目录的上级（项目根目录），再进入 backend
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

cd "$BACKEND_DIR"
echo "📂 Working in: $BACKEND_DIR"

# .env 可能不在仓库里（被 .gitignore 排除），条件性添加
# 使用绝对路径避免 PyInstaller 解析错误
if [ -f "$BACKEND_DIR/.env" ]; then
  echo "📄 Found .env, will bundle it"
  ENV_ARG="--add-data $BACKEND_DIR/.env:."
else
  echo "⚠️  No .env found, skipping"
  ENV_ARG=""
fi

pyinstaller \
  --onedir \
  --name backend \
  $ENV_ARG \
  --hidden-import=pymysql \
  --hidden-import=bcrypt \
  --hidden-import=openpyxl \
  --hidden-import=openpyxl.cell._writer \
  --hidden-import=sqlalchemy.dialects.mysql \
  --hidden-import=sqlalchemy.dialects.mysql.pymysql \
  --noconfirm \
  --distpath "$PROJECT_DIR/electron/resources/python-backend" \
  --workpath /tmp/pyinstaller-build \
  --specpath "$BACKEND_DIR" \
  app.py

echo "✅ Python backend built → electron/resources/python-backend/backend/"
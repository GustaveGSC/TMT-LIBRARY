#!/bin/bash
# scripts/build-python-mac.sh
# 在 macOS 上将 Flask 后端打包为单目录可执行文件
set -e

echo "🐍 Building Python backend for macOS..."

cd backend

# .env 可能不在仓库里（被 .gitignore 排除），条件性添加
ENV_ARG=""
if [ -f ".env" ]; then
  ENV_ARG="--add-data .env:."
  echo "📄 Found .env, will bundle it"
else
  echo "⚠️  No .env found, skipping (will use environment variables at runtime)"
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
  --distpath ../electron/resources/python-backend \
  --workpath /tmp/pyinstaller-build \
  --specpath /tmp \
  app.py

echo "✅ Python backend built → electron/resources/python-backend/backend/"
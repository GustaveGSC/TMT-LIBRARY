#!/bin/bash
# scripts/build-python-mac.sh
# 在 macOS 上将 Flask 后端打包为单目录可执行文件
set -e

echo "🐍 Building Python backend for macOS..."

cd backend

pyinstaller \
  --onedir \
  --name backend \
  --add-data ".env:." \
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
@echo off
REM scripts/build-python.bat
REM 打包 Python 后端为 backend.exe
REM 输出到 electron/resources/python-backend/

setlocal

set ROOT_DIR=%~dp0..
set BACKEND_DIR=%ROOT_DIR%\backend
set OUTPUT_DIR=%ROOT_DIR%\electron\resources\python-backend

echo 📦 开始打包 Python 后端...
echo    后端目录：%BACKEND_DIR%
echo    输出目录：%OUTPUT_DIR%

REM 确保输出目录存在
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM 进入后端目录
cd /d "%BACKEND_DIR%"

REM 执行打包
echo ⚙️  执行 PyInstaller...
pyinstaller backend.spec --clean --distpath "%OUTPUT_DIR%"

if %errorlevel% neq 0 (
  echo ❌ 打包失败
  exit /b 1
)

echo ✅ Python 后端打包完成
echo    产物：%OUTPUT_DIR%\backend.exe
dir "%OUTPUT_DIR%"

copy "%BACKEND_DIR%\.env" "%OUTPUT_DIR%\.env"
echo ✅ .env 已复制
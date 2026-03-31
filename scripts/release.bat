@echo off
REM scripts/release.bat
REM 用法：release.bat <版本号> [发布说明]
REM 示例：release.bat 1.0.2 "修复主题切换重启丢失问题"

setlocal enabledelayedexpansion

REM ── 参数检查 ─────────────────────────────────────────
if "%~1"=="" (
  echo.
  echo 用法：release.bat ^<版本号^> [发布说明]
  echo 示例：release.bat 1.0.2 "修复主题切换重启丢失问题"
  echo.
  exit /b 1
)

set VERSION=%~1
set MESSAGE=%~2
if "!MESSAGE!"=="" set MESSAGE=发布 v!VERSION!

set ROOT_DIR=%~dp0..
cd /d "%ROOT_DIR%"

REM ── 检查是否有未提交的改动 ──────────────────────────
echo.
echo 🔍 检查 git 状态...
git diff --quiet && git diff --cached --quiet
if %errorlevel% neq 0 (
  echo.
  echo ⚠️  存在未提交的改动，请先 commit 或 stash 后再发布。
  echo.
  git status --short
  echo.
  exit /b 1
)

REM ── 检查 tag 是否已存在 ─────────────────────────────
git tag | findstr /x "v!VERSION!" >nul 2>&1
if %errorlevel% equ 0 (
  echo.
  echo ❌ Tag v!VERSION! 已存在，请确认版本号。
  echo.
  exit /b 1
)

REM ── 读取旧版本号 ────────────────────────────────────
for /f "delims=" %%i in ('node -e "const p=JSON.parse(require('fs').readFileSync('package.json','utf8'));process.stdout.write(p.version)"') do set OLD_VERSION=%%i
echo    当前版本：!OLD_VERSION! → !VERSION!

REM ── 更新 package.json 版本号 ────────────────────────
echo 📝 更新 package.json...
node -e "const fs=require('fs');const p=JSON.parse(fs.readFileSync('package.json','utf8'));p.version='!VERSION!';fs.writeFileSync('package.json',JSON.stringify(p,null,2)+'\n')"
if %errorlevel% neq 0 (
  echo ❌ 更新 package.json 失败
  exit /b 1
)

REM ── 更新下载页版本号 ────────────────────────────────
echo 📝 更新 docs/index.html...
node -e "const fs=require('fs');const f='docs/index.html';let s=fs.readFileSync(f,'utf8');s=s.replaceAll('!OLD_VERSION!','!VERSION!');fs.writeFileSync(f,s)"
if %errorlevel% neq 0 (
  echo ❌ 更新 docs/index.html 失败
  exit /b 1
)

REM ── Git commit ──────────────────────────────────────
echo 📦 提交版本号变更...
git add package.json docs/index.html
git commit -m "chore: release v!VERSION!"
if %errorlevel% neq 0 (
  echo ❌ git commit 失败
  exit /b 1
)

REM ── 打 Tag ──────────────────────────────────────────
echo 🏷️  打 tag v!VERSION!...
git tag -a "v!VERSION!" -m "!MESSAGE!"
if %errorlevel% neq 0 (
  echo ❌ git tag 失败
  exit /b 1
)

REM ── 推送 Git ─────────────────────────────────────────
echo 🚀 推送 commit 和 tag 到远程...
git push
if %errorlevel% neq 0 (
  echo ❌ git push 失败
  exit /b 1
)
git push origin "v!VERSION!"
if %errorlevel% neq 0 (
  echo ❌ git push tag 失败
  exit /b 1
)

REM ── 上传下载页到 OSS ─────────────────────────────────
where ossutil >nul 2>&1
if %errorlevel% equ 0 (
  echo ☁️  上传下载页到 OSS...
  ossutil cp docs/index.html oss://tmt-oss/index.html --acl public-read --meta "Content-Type:text/html; charset=utf-8" -f
  if %errorlevel% neq 0 (
    echo ⚠️  OSS 上传失败，请手动上传 docs/index.html 到 oss://tmt-oss/index.html
  ) else (
    echo    下载页已更新
  )
) else (
  echo ⚠️  未检测到 ossutil，请手动上传 docs/index.html 到 oss://tmt-oss/index.html
)

REM ── 完成 ────────────────────────────────────────────
echo.
echo ✅ 发布完成！
echo    版本：v!VERSION!
echo    说明：!MESSAGE!
echo.
echo 📌 查看所有版本 tag：git tag
echo 📌 切回该版本代码：git checkout v!VERSION!
echo 📌 返回最新代码：  git checkout master
echo.

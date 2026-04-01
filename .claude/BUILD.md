# 打包流程说明

## 前置条件

1. **Python 后端已编译**：`electron/resources/python-backend/backend.exe` 必须存在（PyInstaller `--onefile` 单文件产物）
2. **图标文件**：`resources/icon.png`（1024×1024 RGBA PNG）

---

## 步骤一：生成 Windows 图标

```bash
npm run make-ico
```

- 脚本：`scripts/make-ico.js`
- 依赖：`png-to-ico`（已在 devDependencies）
- 产出：`resources/icon.ico`（electron-builder.yml 中 win.icon 指向此文件）

> **注意**：若 `png-to-ico` 未安装，先执行 `npm install png-to-ico --save-dev`

---

## 步骤二：构建前端 + 主进程

```bash
npm run build
```

产出目录：`out/`

---

## 步骤三：打包安装包

### 正常情况

```bash
npx electron-builder --win
```

产出：`release/TMT Software Setup x.x.x.exe`

### Windows Defender 文件锁冲突（常见问题）

**现象**：`remove ... backend.exe: Access is denied`

**原因**：Defender 实时扫描锁定 `win-unpacked/` 里的 `backend.exe`，导致下次打包无法清理旧目录。

**解决办法**：指定一个新的输出目录绕过旧目录：

```bash
npx electron-builder --win --config.directories.output=release2
```

打包完成后手动将 `release2/` 中的文件整理到 `release/`。

---

## 步骤四：上传 OSS

上传以下三个文件到 `tmt-oss/tmt-library/releases/`：

| 文件 | 说明 |
|------|------|
| `TMT Software Setup x.x.x.exe` | 安装包 |
| `TMT Software Setup x.x.x.exe.blockmap` | 增量更新块图 |
| `latest.yml` | 版本元数据（下载页 + 应用内更新均依赖此文件） |

---

## 路径对应关系

| 来源 | 打包后位置 | 代码引用 |
|------|-----------|---------|
| `electron/resources/python-backend/backend.exe` | `resources/python-backend/backend.exe` | `electron/main/python.ts` → `getPythonExecutable()` |
| `resources/icon.png` | 嵌入 `TMT Software.exe` | `electron-builder.yml` → `win.icon` |

---

## 下载页 CORS 配置

下载页（GitHub Pages）通过 fetch 读取 OSS 上的 `latest.yml`，需要在 OSS 控制台配置跨域规则：

- Bucket：`tmt-oss`
- 入口：**数据安全 → 跨域设置（CORS）**
- 规则：
  - Origin：`https://gustavegsc.github.io`
  - Methods：`GET, HEAD`
  - Headers：`*`

---

## 一键完整流程（无 Defender 冲突时）

```bash
npm run make-ico && npm run build && npx electron-builder --win
```

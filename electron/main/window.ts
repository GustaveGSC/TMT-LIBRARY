import { BrowserWindow, shell } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'

let mainWindow: BrowserWindow | null = null

const WEB_BASE = 'http://47.99.100.138'

// 离线降级页（网络不通时显示，替代 Chromium 白屏）
const offlineHTML = `<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#ede8dc;display:flex;justify-content:center;align-items:center;
  height:100vh;font-family:'Microsoft YaHei UI','Microsoft YaHei','PingFang SC',sans-serif}
.card{background:#fff;border:1px solid #e0d4c0;border-radius:12px;padding:48px 56px;text-align:center}
h2{color:#3a3028;font-size:18px;margin-bottom:8px}
p{color:#6b5e4e;font-size:14px;margin-bottom:24px}
button{background:#c4883a;color:#fff;border:none;border-radius:10px;
  padding:8px 28px;cursor:pointer;font-size:14px}
button:hover{background:#e09050}
</style></head>
<body><div class="card">
<h2>网络连接失败</h2>
<p>请检查网络连接后重试</p>
<button onclick="location.reload()">重 试</button>
</div></body></html>`

function attachOfflineFallback(win: BrowserWindow): void {
  // errorCode -3 = ABORTED（用户主动导航取消，跳过）
  win.webContents.on('did-fail-load', (_e, code) => {
    if (code === -3) return
    win.webContents.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(offlineHTML))
  })
}

// ── 登录窗口（小窗口，无边框，只显示卡片）──
export function createLoginWindow(): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 860,
    height: 640,
    frame: false,           // 去掉标题栏和边框
    transparent: false,      // 背景透明
    backgroundColor: '#ede8dc',
    hasShadow: false,
    resizable: false,
    center: true,
    show: false,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow!.show())
  attachOfflineFallback(mainWindow)

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'] + '#/login')
  } else {
    mainWindow.loadURL(WEB_BASE + '/#/login')
  }

  return mainWindow
}

// ── 主窗口（登录成功后切换）──
export function createMainWindow(): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    backgroundColor: '#ede8dc',
    resizable: true,
    center: true,
    show: false,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => mainWindow!.show())
  attachOfflineFallback(mainWindow)

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'] + '#/index')
  } else {
    mainWindow.loadURL(WEB_BASE + '/#/index')
  }

  return mainWindow
}
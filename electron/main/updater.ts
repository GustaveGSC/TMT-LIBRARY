import { autoUpdater } from 'electron-updater'
import { ipcMain, BrowserWindow, app } from 'electron'
import log from 'electron-log'
import { stopPython } from './python'

// 日志输出到文件
autoUpdater.logger = log
log.transports.file.level = 'info'

// 只让 autoUpdater 在开发模式下也能工作，不影响 app.isPackaged
autoUpdater.forceDevUpdateConfig = true

// 不自动下载，由用户触发
autoUpdater.autoDownload    = false
autoUpdater.autoInstallOnAppQuit = false

let mainWinRef: BrowserWindow | null = null

let initialized = false

function sendToRenderer(event: string, data?: unknown) {
  mainWinRef?.webContents.send(event, data)
}

export function initUpdater(win: BrowserWindow) {
  mainWinRef = win

  if (initialized) return  // IPC handler 只注册一次
  initialized = true

  // ── autoUpdater 事件 ────────────────────────────
  autoUpdater.on('checking-for-update', () => {
    sendToRenderer('updater:checking')
  })

  autoUpdater.on('update-available', (info) => {
    sendToRenderer('updater:available', {
      version:     info.version,
      releaseDate: info.releaseDate,
      // releaseNotes 从数据库取，这里只传版本号
    })
  })

  autoUpdater.on('update-not-available', () => {
    sendToRenderer('updater:not-available')
  })

  autoUpdater.on('download-progress', (progress) => {
    sendToRenderer('updater:progress', {
      percent:       Math.floor(progress.percent),
      transferred:   progress.transferred,
      total:         progress.total,
      bytesPerSecond: progress.bytesPerSecond,
    })
  })

  autoUpdater.on('update-downloaded', () => {
    sendToRenderer('updater:downloaded')
  })

  autoUpdater.on('error', (err) => {
    sendToRenderer('updater:error', err.message)
  })

  // ── IPC handlers ───────────────────────────────

  // 检查更新
  ipcMain.handle('updater:check', async () => {
    try {
      await autoUpdater.checkForUpdates()
    } catch (e: any) {
      sendToRenderer('updater:error', e.message)
    }
  })

  // 开始下载（更新 manifest 已在 updater:check 时缓存，直接下载即可）
  ipcMain.handle('updater:download', async () => {
    try {
      await autoUpdater.downloadUpdate()
    } catch (e: any) {
      sendToRenderer('updater:error', e.message)
    }
  })

  // 安装并重启：先同步停掉 backend，再启动安装程序
  ipcMain.handle('updater:install', () => {
    stopPython()
    autoUpdater.quitAndInstall(false, true)
  })
}

export function destroyUpdater() {
  mainWinRef = null
}
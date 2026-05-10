import { BrowserWindow, shell } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'

let mainWindow: BrowserWindow | null = null

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

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'] + '#/login')
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'), {
      hash: '/login'
    })
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

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'] + '#/index')
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'), {
      hash: '/index'
    })
  }

  return mainWindow
}
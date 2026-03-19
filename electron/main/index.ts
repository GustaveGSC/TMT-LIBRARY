import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import { createLoginWindow, createMainWindow } from './window'
import { startPython, stopPython } from './python'
import { destroyUpdater, initUpdater } from './updater'

let loginWin: BrowserWindow | null = null
let mainWin: BrowserWindow | null = null

ipcMain.handle('get-api-base', () => 'http://127.0.0.1:8765')

// 监听登录成功事件，关闭登录窗口，打开主窗口
ipcMain.on('login-success', () => {
  loginWin?.close()
  mainWin = createMainWindow()
  initUpdater(mainWin)
})

ipcMain.on('logout', () => {
  destroyUpdater()
  mainWin?.close()
  loginWin = createLoginWindow()
})

ipcMain.handle('get-version', () => app.getVersion())

ipcMain.handle('show-open-dialog', (_event, options) =>
  dialog.showOpenDialog(options)
)

ipcMain.handle('read-file-as-data-url', (_event, filePath: string) => {
  const data = fs.readFileSync(filePath)
  const ext  = path.extname(filePath).slice(1).toLowerCase()
  const mime = ext === 'png' ? 'image/png' : 'image/jpeg'
  return `data:${mime};base64,${data.toString('base64')}`
})

// 监听窗口最小化事件
ipcMain.on('minimize-app', () => {
  BrowserWindow.getFocusedWindow()?.minimize()
})

// 监听窗口最大化事件
ipcMain.on('maximize-app', () => {
  BrowserWindow.getFocusedWindow()?.maximize()
})

// 监听窗口还原事件
ipcMain.on('unmaximize-app', () => {
  BrowserWindow.getFocusedWindow()?.unmaximize()
})

ipcMain.on('quit-app', () => {
  stopPython()   // 关闭 Python 后台
  app.quit()
})

app.whenReady().then(async () => {
  if (app.isPackaged) await startPython()
  loginWin = createLoginWindow()
})

app.on('window-all-closed', () => {
  stopPython()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopPython()
})
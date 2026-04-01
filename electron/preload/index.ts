import { contextBridge, ipcRenderer } from 'electron'

// 只暴露白名单方法给渲染进程，不暴露任何 Node.js 原生模块
contextBridge.exposeInMainWorld('electronAPI', {
  // 获取 Python 后端地址（开发/生产不同）
  getApiBase: (): Promise<string> =>
    ipcRenderer.invoke('get-api-base'),

  // 应用版本
  getVersion: () => ipcRenderer.invoke('get-version'),

  // 更新
  updater: {
    check:    ()  => ipcRenderer.invoke('updater:check'),
    download: ()  => ipcRenderer.invoke('updater:download'),
    install:  ()  => ipcRenderer.invoke('updater:install'),
    on: (event: string, cb: (...args: any[]) => void) => {
      ipcRenderer.on(event, (_, ...args) => cb(...args))
    },
    off: (event: string, cb: (...args: any[]) => void) => {
      ipcRenderer.removeListener(event, cb)
    },
  },

  // 原生对话框
  showOpenDialog: (options: Electron.OpenDialogOptions) =>
    ipcRenderer.invoke('show-open-dialog', options),

  // 读取本地文件为 base64 data URL（绕过 file:// 安全限制）
  readFileAsDataURL: (filePath: string) =>
    ipcRenderer.invoke('read-file-as-data-url', filePath),

  // 最小化应用
  minimizeApp: () => ipcRenderer.send('minimize-app'),

  // 最大化应用
  maximizeApp: () => ipcRenderer.send('maximize-app'),

  // 还原应用
  unmaximizeApp: () => ipcRenderer.send('unmaximize-app'),

  // 监听窗口最大化/还原状态变更（主进程转发）
  onMaximize:   (cb: () => void) => ipcRenderer.on('window-maximized',   () => cb()),
  onUnmaximize: (cb: () => void) => ipcRenderer.on('window-unmaximized', () => cb()),

  // 登录成功后通知主进程切换窗口
  loginSuccess: () => ipcRenderer.send('login-success'),

  // 登出
  logout: () => ipcRenderer.send('logout'),

  // 退出应用
  quitApp: () => ipcRenderer.send('quit-app'),
})

// 类型声明（在 src/env.d.ts 中引用）
export type ElectronAPI = typeof window.electronAPI
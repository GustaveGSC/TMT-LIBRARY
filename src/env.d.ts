/// <reference types="vite/client" />

interface Window {
  electronAPI: {
    getApiBase:    () => Promise<string>
    minimizeApp:   () => void
    getVersion:    () => Promise<string>
    loginSuccess:  () => void
    logout:        () => void
    quitApp:       () => void
    openExternal:   (url: string) => void
    showOpenDialog: (options: Electron.OpenDialogOptions) => Promise<Electron.OpenDialogReturnValue>
    updater: {
      check:    () => Promise<void>
      download: () => Promise<void>
      install:  () => Promise<void>
      on:  (event: string, cb: (...args: any[]) => void) => void
      off: (event: string, cb: (...args: any[]) => void) => void
    }
  }
}
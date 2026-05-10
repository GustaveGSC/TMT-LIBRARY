// 平台检测：是否运行在 Electron 环境
export const isElectron = typeof window !== 'undefined' && !!window.electronAPI

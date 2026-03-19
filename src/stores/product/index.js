// src/stores/product/index.js
export { useFinishedStore } from './finished'
export { usePackagedStore  } from './packaged'

import { useFinishedStore } from './finished'
import { usePackagedStore  } from './packaged'

// 进入产品库页面时调用（只初始化 store 实例，数据按需加载）
export function initProductStore() {
  useFinishedStore()
  usePackagedStore()
}

// 确保表格所需数据已加载（进入表格页时调用）
export async function ensureTableData() {
  const finishedStore = useFinishedStore()
  const packagedStore = usePackagedStore()
  const tasks = []
  if (!finishedStore.loaded) tasks.push(finishedStore.load())
  if (!packagedStore.loaded) tasks.push(packagedStore.loadAll())
  if (tasks.length) await Promise.all(tasks)
}

// 离开产品库时调用
export function resetProductStore() {
  useFinishedStore().reset()
}
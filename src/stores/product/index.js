// src/stores/product/index.js
export { useFinishedStore } from './finished'
export { usePackagedStore  } from './packaged'

import { useFinishedStore } from './finished'
import { usePackagedStore  } from './packaged'

// 进入产品库页面时调用
export async function initProductStore() {
  const finishedStore = useFinishedStore()
  const packagedStore = usePackagedStore()
  await Promise.all([finishedStore.load(), packagedStore.loadAll()])
}

// 离开产品库时调用
export function resetProductStore() {
  useFinishedStore().reset()
}
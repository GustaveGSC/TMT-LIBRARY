import { ref } from 'vue'
// 模块级单例：跨产品行实例共享的参数剪贴板
export const copiedParams = ref(null)
// 模块级单例：跨产品行实例共享的标签剪贴板（tag_names 数组）
export const copiedTagNames = ref(null)

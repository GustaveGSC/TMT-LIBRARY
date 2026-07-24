/**
 * useCategoryTree — 产品分类树共享加载 composable
 *
 * `/api/category/tree` 内容与日期筛选等页面局部状态无关，之前被多个页面各自在
 * date watcher / mount 里重复请求。这里做成模块级单例：
 *   - loadCategoryTreeOnce()：只在首次调用时真正发请求，之后返回同一个 Promise/缓存结果，
 *     并发调用会共享同一次网络请求（不会打出多条 /api/category/tree）。
 *   - invalidateCategoryTree()：分类维护（新增/编辑/删除分类/系列/型号）成功后调用，
 *     清空缓存，下次 loadCategoryTreeOnce() 会重新发请求，避免永久缓存旧树。
 */
import { ref } from 'vue'
import http from '@/api/http'

const categoryTree = ref([])
let inflightPromise = null
let loaded = false

export function useCategoryTree() {
  async function loadCategoryTreeOnce() {
    if (loaded) return categoryTree.value
    if (inflightPromise) return inflightPromise

    inflightPromise = (async () => {
      try {
        const res = await http.get('/api/category/tree')
        if (res.success) {
          categoryTree.value = res.data
          loaded = true
        }
        return categoryTree.value
      } finally {
        inflightPromise = null
      }
    })()

    return inflightPromise
  }

  function invalidateCategoryTree() {
    loaded = false
    inflightPromise = null
  }

  return {
    categoryTree,
    loadCategoryTreeOnce,
    invalidateCategoryTree,
  }
}

// src/stores/product/packaged.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/api/http'

export const usePackagedStore = defineStore('product/packaged', () => {

  // ── 状态 ──────────────────────────────────────────
  // 全量产成品，key 为 code
  const map     = ref({})
  const loading = ref(false)
  const loaded  = ref(false)

  // ── 全量加载（进入产品库时调用，只加载一次）──────
  async function loadAll() {
    if (loaded.value) return
    loading.value = true
    try {
      const res = await http.get('/api/product/packaged/all')
      if (res.success) {
        const m = {}
        res.data.forEach(p => { m[p.code] = p })
        map.value    = m
        loaded.value = true
      }
    } catch (e) {
      console.error('产成品预加载失败', e)
    } finally {
      loading.value = false
    }
  }

  // ── 根据 code 列表取详情 ──────────────────────────
  function getByCodeList(codes = []) {
    return codes.map(code => map.value[code]).filter(Boolean)
  }

  return { map, loading, loaded, loadAll, getByCodeList }
})
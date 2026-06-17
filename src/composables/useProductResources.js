// ── 产品资料库 composable ─────────────────────────────────────────────────
// 用法一（资料库页面）：useProductResources()  — 无参，管理全局资料列表和类型
// 用法二（产品详情）：useProductResources(() => code) — 管理该产品的关联资料
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'

export function useProductResources(codeGetter = null) {
  // ── 类型 ──────────────────────────────────────────
  const types        = ref([])
  const typesLoading = ref(false)

  async function loadTypes() {
    typesLoading.value = true
    try {
      const res = await http.get('/api/resources/types')
      if (res.success) types.value = res.data
    } finally {
      typesLoading.value = false
    }
  }

  async function createType(name, sort_order = 0) {
    const res = await http.post('/api/resources/types', { name, sort_order })
    if (res.success) { ElMessage.success('类型已新增'); await loadTypes() }
    else ElMessage.error(res.message || '新增失败')
    return res.success
  }

  async function updateType(id, payload) {
    const res = await http.put(`/api/resources/types/${id}`, payload)
    if (res.success) { ElMessage.success('已保存'); await loadTypes() }
    else ElMessage.error(res.message || '保存失败')
    return res.success
  }

  async function deleteType(id) {
    try {
      await ElMessageBox.confirm('确认删除该类型？删除后无法恢复。', '删除确认', {
        confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
      })
    } catch { return false }
    const res = await http.delete(`/api/resources/types/${id}`)
    if (res.success) { ElMessage.success('已删除'); await loadTypes() }
    else ElMessage.error(res.message || '删除失败')
    return res.success
  }

  // ── 资料库列表（资料库页面用）────────────────────
  const resources        = ref([])
  const resourcesTotal   = ref(0)
  const resourcesLoading = ref(false)
  const resourcesFilter  = ref({ type_id: null, search: '', page: 1, size: 50 })

  async function loadResources(filter = {}) {
    Object.assign(resourcesFilter.value, filter)
    resourcesLoading.value = true
    try {
      const params = {}
      if (resourcesFilter.value.type_id) params.type_id = resourcesFilter.value.type_id
      if (resourcesFilter.value.search)  params.search  = resourcesFilter.value.search
      params.page = resourcesFilter.value.page
      params.size = resourcesFilter.value.size
      const res = await http.get('/api/resources', { params })
      if (res.success) {
        resources.value      = res.data.items
        resourcesTotal.value = res.data.total
      }
    } finally {
      resourcesLoading.value = false
    }
  }

  async function createResource(payload) {
    const res = await http.post('/api/resources', payload)
    if (res.success) { ElMessage.success('资料已创建') }
    else ElMessage.error(res.message || '创建失败')
    return res.success ? res.data : null
  }

  async function updateResource(id, payload) {
    const res = await http.put(`/api/resources/${id}`, payload)
    if (res.success) { ElMessage.success('已保存') }
    else ElMessage.error(res.message || '保存失败')
    return res.success
  }

  async function setResourceModels(id, modelIds) {
    const res = await http.put(`/api/resources/${id}/models`, { model_ids: modelIds })
    if (!res.success) ElMessage.error(res.message || '型号设置失败')
    return res.success
  }

  async function setResourceTags(id, tagIds) {
    const res = await http.put(`/api/resources/${id}/tags`, { tag_ids: tagIds })
    if (!res.success) ElMessage.error(res.message || '标签设置失败')
    return res.success
  }

  async function deleteResource(id) {
    try {
      await ElMessageBox.confirm('确认删除该资料？将同时解除所有产品的关联。', '删除确认', {
        confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
      })
    } catch { return false }
    const res = await http.delete(`/api/resources/${id}`)
    if (res.success) ElMessage.success('已删除')
    else ElMessage.error(res.message || '删除失败')
    return res.success
  }

  // ── 文件直传 OSS ──────────────────────────────────
  const uploading = ref(false)

  async function uploadFile(file) {
    const ext = file.name.split('.').pop().toLowerCase()
    uploading.value = true
    try {
      // 1. 获取预签名 URL
      const presignRes = await http.post('/api/resources/presign', { ext })
      if (!presignRes.success) {
        ElMessage.error(presignRes.message || '获取上传凭证失败')
        return null
      }
      const { presign_url, oss_url, storage_key, file_type } = presignRes.data

      // 2. 直传 OSS
      const contentTypeMap = {
        pdf: 'application/pdf',
        png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp',
      }
      const uploadRes = await fetch(presign_url, {
        method: 'PUT',
        headers: { 'Content-Type': contentTypeMap[ext] || 'application/octet-stream' },
        body: file,
      })
      if (!uploadRes.ok) throw new Error(`OSS 上传失败：${uploadRes.status}`)

      return { url: oss_url, storage_key, file_type, original_filename: file.name }
    } catch (e) {
      ElMessage.error('上传失败：' + e.message)
      return null
    } finally {
      uploading.value = false
    }
  }

  // ── 产品关联资料（产品详情用，需传 codeGetter）──
  const linkedResources = ref([])
  const linkedLoading   = ref(false)
  const linkedLoaded    = ref(false)   // 懒加载标记

  async function loadLinkedResources() {
    if (!codeGetter) return
    const code = codeGetter()
    if (!code) return
    linkedLoading.value = true
    try {
      const res = await http.get(`/api/resources/finished/${code}`)
      if (res.success) { linkedResources.value = res.data; linkedLoaded.value = true }
    } finally {
      linkedLoading.value = false
    }
  }

  async function linkResource(resourceId, sort_order = 0) {
    if (!codeGetter) return false
    const code = codeGetter()
    const res = await http.post(`/api/resources/finished/${code}`, { resource_id: resourceId, sort_order })
    if (res.success) await loadLinkedResources()
    else ElMessage.error(res.message || '关联失败')
    return res.success
  }

  async function unlinkResource(resourceId) {
    if (!codeGetter) return false
    const code = codeGetter()
    const res = await http.delete(`/api/resources/finished/${code}/${resourceId}`)
    if (res.success) await loadLinkedResources()
    else ElMessage.error(res.message || '解除关联失败')
    return res.success
  }

  async function updateLinkedOrder(orderedIds) {
    if (!codeGetter) return false
    const code = codeGetter()
    const res = await http.put(`/api/resources/finished/${code}/order`, { ordered_ids: orderedIds })
    if (!res.success) ElMessage.error(res.message || '排序更新失败')
    return res.success
  }

  // 按类型分组展示
  const linkedByType = computed(() => {
    const groups = {}
    for (const r of linkedResources.value) {
      const key  = r.type_id ?? 0
      const name = r.type_name ?? '未分类'
      if (!groups[key]) groups[key] = { type_id: key, type_name: name, items: [] }
      groups[key].items.push(r)
    }
    return Object.values(groups)
  })

  return {
    // 类型
    types, typesLoading, loadTypes, createType, updateType, deleteType,
    // 资料库列表
    resources, resourcesTotal, resourcesLoading, resourcesFilter,
    loadResources, createResource, updateResource, deleteResource, setResourceTags, setResourceModels,
    // 上传
    uploading, uploadFile,
    // 产品关联资料
    linkedResources, linkedLoading, linkedLoaded, linkedByType,
    loadLinkedResources, linkResource, unlinkResource, updateLinkedOrder,
  }
}

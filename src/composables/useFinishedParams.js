// ── 成品展开行「参数」区逻辑 ─────────────────────────────────────────
import { ref, reactive, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { initSortable } from '@/composables/useSortable'

// 四个固定分组定义（也供模板和其他模块使用）
export const GROUP_DEFS = [
  { key: 'dimension', label: '尺寸', color: '#c4883a', bg: '#fff7ed' },
  { key: 'config',    label: '配置', color: '#3a7bc8', bg: '#edf4ff' },
  { key: 'brand',     label: '品牌', color: '#9c6fba', bg: '#f5eeff' },
  { key: 'other',     label: '其他', color: '#4a9a5a', bg: '#edf8ef' },
]

const EMPTY_GROUPS = () => ({ dimension: [], config: [], brand: [], other: [] })

export function useFinishedParams(props) {
  // ── 状态 ──────────────────────────────────────────

  // 查看模式数据（服务端确认态）
  const paramsData   = ref(EMPTY_GROUPS())
  const paramsLoaded = ref(false)

  // 编辑模式数据（可变），item: { key_id, key_name, value, state }
  // state: 'original' | 'added' | 'deleted'
  const editParams = reactive(EMPTY_GROUPS())

  // 编辑开始时的快照（用于 cancel 回退）
  const originalParamsSnapshot = ref(null)

  // 参数独立编辑模式（不依赖主行 editing）
  const paramsEditing = ref(false)
  const paramsSaving  = ref(false)

  // 可用键名（懒加载）
  const paramKeys       = ref(EMPTY_GROUPS())
  const paramKeysLoaded = ref(false)

  // 新增参数 dialog（四个分组共用）
  const paramAddDialog = reactive({ visible: false, groupKey: '', name: '', value: '' })

  // 拖拽实例
  const sortableRefs      = reactive(EMPTY_GROUPS())
  const sortableInstances = {}

  // ── 键名管理 ──────────────────────────────────────

  function openParamAdd(groupKey) {
    paramAddDialog.groupKey = groupKey
    paramAddDialog.name     = ''
    paramAddDialog.value    = ''
    paramAddDialog.visible  = true
  }

  async function ensureParamKeysLoaded() {
    if (paramKeysLoaded.value) return
    try {
      const res = await http.get('/api/product/params/keys')
      if (res.success) { paramKeys.value = res.data; paramKeysLoaded.value = true }
    } catch {}
  }

  // el-select 候选键名（已有库中的名称，排除已添加）
  function availableKeyOptions(groupKey) {
    const usedNames = new Set(editParams[groupKey].map(i => i.key_name))
    return (paramKeys.value[groupKey] || []).filter(k => !usedNames.has(k.name))
  }

  function addParamItem() {
    const groupKey = paramAddDialog.groupKey
    const name = (paramAddDialog.name || '').trim()
    if (!name) return
    if (editParams[groupKey].some(i => i.key_name === name)) {
      ElMessage.warning('该分组下已添加同名参数')
      return
    }
    const existingKey = (paramKeys.value[groupKey] || []).find(k => k.name === name)
    editParams[groupKey].push({
      key_id:   existingKey?.id ?? null,
      key_name: name,
      value:    paramAddDialog.value || '',
      state:    'added',
    })
    paramAddDialog.visible = false
  }

  // added → 直接移除；original → 标记为 deleted（变红+撤回键）
  function removeParamItem(groupKey, idx) {
    const item = editParams[groupKey][idx]
    if (item.state === 'added') {
      editParams[groupKey].splice(idx, 1)
    } else {
      item.state = 'deleted'
    }
  }

  function restoreParamItem(groupKey, idx) {
    editParams[groupKey][idx].state = 'original'
  }

  // ── 数据加载 & 同步 ───────────────────────────────

  async function loadParams(finishedId) {
    if (!finishedId) return
    try {
      const res = await http.get(`/api/product/params/finished/${finishedId}`)
      if (res.success) { paramsData.value = res.data; paramsLoaded.value = true }
    } catch {}
  }

  // 将 paramsData 深拷贝到 editParams，所有项 state 置为 'original'
  function syncEditParamsFromData() {
    GROUP_DEFS.forEach(g => {
      editParams[g.key] = (paramsData.value[g.key] || []).map(p => ({
        key_id:   p.key_id,
        key_name: p.key_name,
        value:    p.value,
        state:    'original',
      }))
    })
  }

  // ── 拖拽 ──────────────────────────────────────────

  function initSortables() {
    GROUP_DEFS.forEach(g => {
      const el = sortableRefs[g.key]
      if (el && !sortableInstances[g.key]) {
        sortableInstances[g.key] = initSortable(el, ({ oldIndex, newIndex }) => {
          const arr = editParams[g.key]
          const [moved] = arr.splice(oldIndex, 1)
          arr.splice(newIndex, 0, moved)
        })
      }
    })
  }

  function destroySortables() {
    GROUP_DEFS.forEach(g => {
      sortableInstances[g.key]?.destroy()
      sortableInstances[g.key] = null
    })
  }

  // ── 独立编辑模式（不依赖主行 editing）────────────

  async function startParamsEdit() {
    if (!props.row.id) return
    await Promise.all([ensureParamKeysLoaded(), loadParams(props.row.id)])
    syncEditParamsFromData()
    originalParamsSnapshot.value = JSON.stringify(paramsData.value)
    paramsEditing.value = true
    await nextTick()
    initSortables()
  }

  function cancelParamsEdit() {
    if (originalParamsSnapshot.value) {
      paramsData.value = JSON.parse(originalParamsSnapshot.value)
      syncEditParamsFromData()
    }
    destroySortables()
    paramsEditing.value = false
  }

  // 构建保存 payload（过滤 deleted 项）
  function buildParamsPayload() {
    const payload = {}
    GROUP_DEFS.forEach(g => {
      payload[g.key] = editParams[g.key]
        .filter(item => item.state !== 'deleted')
        .map((item, idx) => ({
          key_id:     item.key_id,
          key_name:   item.key_name,
          value:      item.value,
          sort_order: idx,
        }))
    })
    return payload
  }

  // 保存参数到服务端，返回是否成功
  async function saveParamsFor(finishedId) {
    if (!finishedId) return false
    try {
      const res = await http.post(`/api/product/params/finished/${finishedId}`, buildParamsPayload())
      if (res.success) {
        paramsData.value   = res.data
        paramsLoaded.value = true
        return true
      } else {
        ElMessage.error(res.message || '参数保存失败')
        return false
      }
    } catch {
      ElMessage.error('参数保存失败，请重试')
      return false
    }
  }

  // 独立模式的保存按钮入口
  async function saveParamsOnly() {
    paramsSaving.value = true
    try {
      const ok = await saveParamsFor(props.row.id)
      if (ok) { destroySortables(); paramsEditing.value = false; ElMessage.success('参数已保存') }
    } finally {
      paramsSaving.value = false
    }
  }

  return {
    // 状态
    paramsData, paramsLoaded, editParams, originalParamsSnapshot,
    paramsEditing, paramsSaving, paramKeys, paramKeysLoaded,
    paramAddDialog, sortableRefs,
    // 方法
    openParamAdd, ensureParamKeysLoaded, availableKeyOptions,
    addParamItem, removeParamItem, restoreParamItem,
    loadParams, syncEditParamsFromData,
    initSortables, destroySortables,
    startParamsEdit, cancelParamsEdit,
    buildParamsPayload, saveParamsFor, saveParamsOnly,
  }
}

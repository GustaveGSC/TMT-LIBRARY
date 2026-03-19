<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted, computed } from 'vue'
import { Plus, Delete, Edit, ArrowRight } from '@element-plus/icons-vue'
import http from '@/api/http'

// ── 树形数据 ──────────────────────────────────────
const tree      = ref([])   // [ { id, name, series: [ { id, name, models: [...] } ] } ]
const loading   = ref(false)
const treeError = ref('')

// ── 当前选中节点 ──────────────────────────────────
// type: 'category' | 'series' | 'model'
const selected = ref(null)  // { type, data, parent? }

// ── 右侧表单 ──────────────────────────────────────
const formMode   = ref('')   // 'create' | 'edit' | ''
const formData   = ref({ code: '', name: '', model_code: '', name_en: '' })
const formError  = ref('')
const submitting = ref(false)

// ── 新增时的父节点上下文 ──────────────────────────
// createContext: { type: 'category'|'series'|'model', parentId? }
const createContext = ref(null)

// ── 计算右侧面板标题 ──────────────────────────────
const panelTitle = computed(() => {
  if (!formMode.value) return ''
  const typeLabel = createContext.value
    ? { category: '分类', series: '系列', model: '型号' }[createContext.value.type]
    : { category: '分类', series: '系列', model: '型号' }[selected.value?.type]
  return formMode.value === 'create' ? `新增${typeLabel}` : `编辑${typeLabel}`
})

// ── 展开/折叠状态 ─────────────────────────────────
// 用普通对象 { id: true } 代替 Set，Vue 能追踪属性变化
const expandedCategories = ref({})
const expandedSeries     = ref({})

function toggleCategory(id) {
  expandedCategories.value[id] = !expandedCategories.value[id]
}
function toggleSeries(id) {
  expandedSeries.value[id] = !expandedSeries.value[id]
}

// 加载树后默认展开所有
async function loadTree() {
  loading.value   = true
  treeError.value = ''
  try {
    const res = await http.get('/api/category/tree')
    if (res.success) {
      tree.value = res.data
      // 默认全部展开
      const catExp = {}
      const serExp = {}
      res.data.forEach(c => {
        catExp[c.id] = true
        ;(c.series || []).forEach(s => { serExp[s.id] = true })
      })
      expandedCategories.value = catExp
      expandedSeries.value     = serExp
    } else {
      treeError.value = res.message || '加载失败'
    }
  } catch (e) {
    treeError.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ── 选中节点 ──────────────────────────────────────
function selectNode(type, data, parent = null) {
  selected.value    = { type, data, parent }
  formMode.value    = ''
  createContext.value = null
  formError.value   = ''
}

// ── 打开新增表单 ──────────────────────────────────
function openCreate(type, parentId = null) {
  createContext.value = { type, parentId }
  selected.value      = null
  formData.value      = { code: '', name: '', model_code: '', name_en: '' }
  formError.value     = ''
  formMode.value      = 'create'
}

// ── 打开编辑表单 ──────────────────────────────────
function openEdit(type, data, parent = null) {
  selected.value      = { type, data, parent }
  createContext.value = null
  formData.value      = {
    code:       data.code       || '',
    name:       data.name       || '',
    model_code: data.model_code || '',
    name_en:    data.name_en    || '',
  }
  formError.value = ''
  formMode.value  = 'edit'
}

// ── 提交表单 ──────────────────────────────────────
async function handleSubmit() {
  formError.value = ''
  const name = (formData.value.name || '').trim()
  if (!name) { formError.value = '名称不能为空'; return }

  submitting.value = true
  try {
    let res
    if (formMode.value === 'create') {
      const { type, parentId } = createContext.value
      if (type === 'category') {
        res = await http.post('/api/category/categories', { name })
      } else if (type === 'series') {
        const code = (formData.value.code || '').trim()
        if (!code) { formError.value = '编码不能为空'; submitting.value = false; return }
        res = await http.post('/api/category/series', { category_id: parentId, code, name })
      } else {
        const code       = (formData.value.code       || '').trim()
        const model_code = (formData.value.model_code || '').trim()
        const name_en    = (formData.value.name_en    || '').trim()
        if (!code)       { formError.value = 'ERP编码不能为空';  submitting.value = false; return }
        if (!model_code) { formError.value = '型号简码不能为空'; submitting.value = false; return }
        res = await http.post('/api/category/models', {
          series_id: parentId, code, name, model_code, name_en
        })
      }
    } else {
      const { type, data } = selected.value
      if (type === 'category') {
        res = await http.put(`/api/category/categories/${data.id}`, { name })
      } else if (type === 'series') {
        const code = (formData.value.code || '').trim()
        if (!code) { formError.value = '编码不能为空'; submitting.value = false; return }
        res = await http.put(`/api/category/series/${data.id}`, { code, name })
      } else {
        const code       = (formData.value.code       || '').trim()
        const model_code = (formData.value.model_code || '').trim()
        const name_en    = (formData.value.name_en    || '').trim()
        if (!code)       { formError.value = 'ERP编码不能为空';  submitting.value = false; return }
        if (!model_code) { formError.value = '型号简码不能为空'; submitting.value = false; return }
        res = await http.put(`/api/category/models/${data.id}`, { code, name, model_code, name_en })
      }
    }

    if (res.success) {
      formMode.value = ''
      createContext.value = null
      await loadTree()
    } else {
      formError.value = res.message || '操作失败'
    }
  } catch (e) {
    formError.value = e.message || '网络错误'
  } finally {
    submitting.value = false
  }
}

// ── 删除节点 ──────────────────────────────────────
const deletingId = ref(null)

async function handleDelete(type, data) {
  deletingId.value = `${type}-${data.id}`
  try {
    let res
    if (type === 'category') res = await http.delete(`/api/category/categories/${data.id}`)
    else if (type === 'series') res = await http.delete(`/api/category/series/${data.id}`)
    else res = await http.delete(`/api/category/models/${data.id}`)

    if (res.success) {
      // 如果删除的是当前选中节点，清空右侧
      if (selected.value?.data?.id === data.id && selected.value?.type === type) {
        selected.value = null
        formMode.value = ''
      }
      await loadTree()
    } else {
      treeError.value = res.message || '删除失败'
    }
  } catch (e) {
    treeError.value = e.message || '网络错误'
  } finally {
    deletingId.value = null
  }
}

// ── 取消编辑 ──────────────────────────────────────
function handleCancel() {
  formMode.value      = ''
  createContext.value = null
  formError.value     = ''
}

// ── 生命周期 ──────────────────────────────────────
onMounted(loadTree)
</script>

<template>
  <div class="product-category">

    <!-- 错误提示 -->
    <div v-if="treeError" class="error-bar">{{ treeError }}</div>

    <div class="layout">

      <!-- ── 左侧树 ──────────────────────────────── -->
      <div class="tree-panel">
        <div class="tree-header">
          <span class="tree-title">分类结构</span>
          <button class="btn-tree-add" title="新增分类" @click="openCreate('category')">
            <el-icon><Plus /></el-icon>
          </button>
        </div>

        <div v-if="loading" class="tree-state">加载中...</div>
        <div v-else-if="!tree.length" class="tree-state">暂无分类，点击 + 新增</div>

        <div v-else class="tree-body">
          <!-- Category 层 -->
          <div v-for="cat in tree" :key="cat.id" class="tree-category">
            <div
              class="tree-node node-category"
              :class="{ active: selected?.type === 'category' && selected?.data?.id === cat.id }"
              @click="selectNode('category', cat)"
            >
              <!-- 展开/折叠箭头，阻止冒泡避免同时触发 selectNode -->
              <el-icon
                class="node-arrow"
                :class="{ expanded: expandedCategories[cat.id] }"
                @click.stop="toggleCategory(cat.id)"
              ><ArrowRight /></el-icon>
              <span class="node-name">{{ cat.name }}</span>
              <div class="node-actions">
                <button class="btn-node" title="新增系列" @click.stop="openCreate('series', cat.id)">
                  <el-icon><Plus /></el-icon>
                </button>
                <button class="btn-node" title="编辑" @click.stop="openEdit('category', cat)">
                  <el-icon><Edit /></el-icon>
                </button>
                <button
                  class="btn-node danger"
                  title="删除"
                  :disabled="deletingId === `category-${cat.id}`"
                  @click.stop="handleDelete('category', cat)"
                >
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>

            <!-- Series 层 -->
            <template v-if="expandedCategories[cat.id]">
              <div v-for="ser in cat.series" :key="ser.id" class="tree-series">
                <div
                  class="tree-node node-series"
                  :class="{ active: selected?.type === 'series' && selected?.data?.id === ser.id }"
                  @click="selectNode('series', ser, cat)"
                >
                  <el-icon
                    class="node-arrow"
                    :class="{ expanded: expandedSeries[ser.id] }"
                    @click.stop="toggleSeries(ser.id)"
                  ><ArrowRight /></el-icon>
                  <span class="node-code">{{ ser.code }}</span>
                  <span class="node-sep">·</span>
                  <span class="node-name">{{ ser.name }}</span>
                  <div class="node-actions">
                    <button class="btn-node" title="新增型号" @click.stop="openCreate('model', ser.id)">
                      <el-icon><Plus /></el-icon>
                    </button>
                    <button class="btn-node" title="编辑" @click.stop="openEdit('series', ser, cat)">
                      <el-icon><Edit /></el-icon>
                    </button>
                    <button
                      class="btn-node danger"
                      title="删除"
                      :disabled="deletingId === `series-${ser.id}`"
                      @click.stop="handleDelete('series', ser)"
                    >
                      <el-icon><Delete /></el-icon>
                    </button>
                  </div>
                </div>

                <!-- Model 层 -->
                <template v-if="expandedSeries[ser.id]">
                  <div
                    v-for="mod in ser.models"
                    :key="mod.id"
                    class="tree-node node-model"
                    :class="{ active: selected?.type === 'model' && selected?.data?.id === mod.id }"
                    @click="selectNode('model', mod, ser)"
                  >
                    <span class="node-dot"></span>
                    <span class="node-code">{{ mod.code }}</span>
                    <div class="node-actions">
                      <button class="btn-node" title="编辑" @click.stop="openEdit('model', mod, ser)">
                        <el-icon><Edit /></el-icon>
                      </button>
                      <button
                        class="btn-node danger"
                        title="删除"
                        :disabled="deletingId === `model-${mod.id}`"
                        @click.stop="handleDelete('model', mod)"
                      >
                        <el-icon><Delete /></el-icon>
                      </button>
                    </div>
                  </div>
                </template>

              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- ── 右侧编辑区 ────────────────────────────── -->
      <div class="edit-panel">

        <!-- 无选中状态 -->
        <div v-if="!formMode && !selected" class="edit-empty">
          <div class="empty-hint">点击左侧节点查看详情，或点击 + 新增</div>
        </div>

        <!-- 查看详情 -->
        <div v-else-if="!formMode && selected" class="edit-detail">

          <!-- 顶部标题区 -->
          <div class="detail-header">
            <span class="detail-type-badge" :class="selected.type">
              {{ { category: '分类', series: '系列', model: '型号' }[selected.type] }}
            </span>
            <span class="detail-name" :class="{ 'is-code': selected.type !== 'category' }">
              {{ selected.type === 'category' ? selected.data.name : selected.data.code }}
            </span>
          </div>

          <!-- 信息卡片（series/model 用卡片，category 不加卡片）-->
          <div :class="selected.type !== 'category' ? 'detail-card' : 'detail-meta'">

            <!-- series/model 专有字段 -->
            <template v-if="selected.type !== 'category'">
              <div class="meta-row">
                <span class="meta-label">名称</span>
                <span class="meta-value">{{ selected.data.name }}</span>
              </div>
              <div v-if="selected.type === 'model'" class="meta-row">
                <span class="meta-label">英文名称</span>
                <span class="meta-value">{{ selected.data.name_en || '—' }}</span>
              </div>
              <div v-if="selected.type === 'model'" class="meta-row">
                <span class="meta-label">型号简码</span>
                <span class="meta-value code-val">{{ selected.data.model_code }}</span>
              </div>
            </template>

            <div v-if="selected.parent" class="meta-row">
              <span class="meta-label">上级</span>
              <span class="meta-value">{{ selected.parent.name }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">创建时间</span>
              <span class="meta-value">{{ selected.data.created_at }}</span>
            </div>
            <div v-if="selected.type === 'category'" class="meta-row">
              <span class="meta-label">包含系列</span>
              <span class="meta-value">{{ selected.data.series?.length ?? 0 }} 个</span>
            </div>
            <div v-if="selected.type === 'series'" class="meta-row">
              <span class="meta-label">包含型号</span>
              <span class="meta-value">{{ selected.data.models?.length ?? 0 }} 个</span>
            </div>
          </div>

          <!-- 底部按钮 -->
          <button class="btn btn-primary" @click="openEdit(selected.type, selected.data, selected.parent)">
            <el-icon><Edit /></el-icon> 编辑
          </button>
        </div>

        <!-- 新增/编辑表单 -->
        <div v-else class="edit-form">
          <div class="form-title">{{ panelTitle }}</div>

          <!-- 编码：仅 series 和 model 显示 -->
          <div
            v-if="(createContext?.type || selected?.type) !== 'category'"
            class="form-row"
          >
            <label class="form-label">ERP编码 <span class="required">*</span></label>
            <input
              v-model="formData.code"
              class="form-input"
              placeholder="输入ERP编码"
              @keyup.enter="handleSubmit"
            />
          </div>

          <div class="form-row">
            <label class="form-label">名称 <span class="required">*</span></label>
            <input
              v-model="formData.name"
              class="form-input"
              placeholder="输入名称"
              @keyup.enter="handleSubmit"
            />
          </div>

          <!-- 型号简码：仅 model 显示，必填 -->
          <div
            v-if="(createContext?.type || selected?.type) === 'model'"
            class="form-row"
          >
            <label class="form-label">型号简码 <span class="required">*</span></label>
            <input
              v-model="formData.model_code"
              class="form-input"
              placeholder="输入型号简码（简码）"
              @keyup.enter="handleSubmit"
            />
          </div>

          <!-- 英文名称：仅 model 显示，选填 -->
          <div
            v-if="(createContext?.type || selected?.type) === 'model'"
            class="form-row"
          >
            <label class="form-label">英文名称</label>
            <input
              v-model="formData.name_en"
              class="form-input"
              placeholder="输入英文名称（选填）"
              @keyup.enter="handleSubmit"
            />
          </div>

          <div v-if="formError" class="form-error">{{ formError }}</div>

          <div class="form-actions">
            <button class="btn btn-secondary" @click="handleCancel">取消</button>
            <button class="btn btn-primary" :disabled="submitting" @click="handleSubmit">
              {{ submitting ? '提交中...' : (formMode === 'create' ? '新增' : '保存') }}
            </button>
          </div>
        </div>

      </div>
    </div>

  </div>
</template>

<style scoped>
.product-category {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  height: 100%;
}

/* ── 错误栏 ───────────────────────────────────── */
.error-bar {
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}

/* ── 整体布局 ─────────────────────────────────── */
.layout {
  display: flex; gap: 12px;
  height: 420px;
}

/* ── 左侧树 ───────────────────────────────────── */
.tree-panel {
  width: 240px; flex-shrink: 0;
  border: 1px solid var(--border); border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
}
.tree-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.8); flex-shrink: 0;
}
.tree-title { font-size: 12px; font-weight: 600; color: #5a4e42; letter-spacing: 0.05em; }
.btn-tree-add {
  width: 22px; height: 22px; border-radius: 5px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 12px; transition: all 0.15s;
}
.btn-tree-add:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }

.tree-state {
  padding: 24px; text-align: center;
  font-size: 12px; color: var(--text-muted);
}
.tree-body {
  flex: 1; overflow-y: auto; padding: 6px 0;
}
.tree-body::-webkit-scrollbar { width: 4px; }
.tree-body::-webkit-scrollbar-track { background: transparent; }
.tree-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── 树节点 ───────────────────────────────────── */
.tree-node {
  display: flex; align-items: center; gap: 6px;
  padding: 0 10px; min-height: 32px;
  cursor: pointer; transition: background 0.15s;
  position: relative;
}
.tree-node:hover { background: rgba(196,136,58,0.05); }
.tree-node.active { background: var(--accent-bg); }

.node-category { padding-left: 10px; }
.node-series   { padding-left: 22px; }
.node-model    { padding-left: 34px; }

.node-arrow {
  font-size: 11px; color: #8a7a6a; flex-shrink: 0;
  transition: transform 0.2s;
  width: 18px; height: 18px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 4px; cursor: pointer;
}
.node-arrow:hover { background: var(--border); color: #3a3028; }
.node-arrow.expanded { transform: rotate(90deg); }
.node-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--border); flex-shrink: 0; margin-right: 2px;
}
.node-name {
  flex: 1; font-size: 12px; color: #6b5e4e;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  min-width: 0;
}
.node-code {
  font-size: 12px; font-weight: 600;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
  color: #3a3028; flex-shrink: 0;
}
.node-sep {
  font-size: 11px; color: #c0b09a; flex-shrink: 0; margin: 0 2px;
}
.tree-node.active .node-code { color: var(--accent); }
.tree-node.active .node-name { color: var(--accent); }

.node-actions {
  display: none; gap: 2px; flex-shrink: 0;
}
.tree-node:hover .node-actions { display: flex; }

.btn-node {
  width: 20px; height: 20px; border-radius: 4px;
  border: none; background: transparent; color: var(--text-muted);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 11px; transition: all 0.15s;
}
.btn-node:hover { background: var(--accent-bg); color: var(--accent); }
.btn-node.danger:hover { background: rgba(208,90,60,0.08); color: #d05a3c; }
.btn-node:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 右侧编辑区 ───────────────────────────────── */
.edit-panel {
  flex: 1; border: 1px solid var(--border); border-radius: 10px;
  background: var(--bg-card); display: flex; flex-direction: column;
  overflow: hidden;
}

.edit-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
}
.empty-hint { font-size: 12px; color: #8a7a6a; }

/* 详情 */
.edit-detail { padding: 24px; }
.detail-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 20px;
}
.detail-type-badge {
  font-size: 11px; font-weight: 500; padding: 3px 10px;
  border-radius: 5px; border: 1px solid;
}
.detail-type-badge.category { color: #c4883a; background: #c4883a18; border-color: #c4883a40; }
.detail-type-badge.series   { color: #4a8fc0; background: #4a8fc018; border-color: #4a8fc040; }
.detail-type-badge.model    { color: #9c6fba; background: #9c6fba18; border-color: #9c6fba40; }
.detail-name { font-size: 18px; font-weight: 700; color: #2c2420; }
.detail-name.is-code { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace; }

.detail-meta { margin-bottom: 24px; display: flex; flex-direction: column; gap: 10px; }
.detail-card {
  margin: 20px 0 24px;
  padding: 16px 18px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex; flex-direction: column; gap: 12px;
}
.meta-row { display: flex; gap: 12px; align-items: center; }
.meta-label { font-size: 12px; color: #8a7a6a; width: 64px; flex-shrink: 0; }
.meta-value { font-size: 13px; color: #3a3028; }
.code-val { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace; color: var(--accent); font-weight: 600; }

/* 表单 */
.edit-form { padding: 24px; }
.form-title { font-size: 15px; font-weight: 600; color: #2c2420; margin-bottom: 20px; }
.form-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.form-label {
  width: 60px; flex-shrink: 0; font-size: 12px; color: #6b5e4e;
  text-align: right; display: flex; align-items: center; justify-content: flex-end; gap: 2px;
}
.required { color: #d05a3c; font-size: 14px; line-height: 1; margin-left: 1px; }
.form-input {
  flex: 1; height: 34px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 13px; font-family: inherit;
  outline: none; transition: border-color 0.2s;
}
.form-input:focus { border-color: var(--accent); }
.form-error { font-size: 12px; color: #d05a3c; margin-bottom: 12px; padding-left: 72px; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; }

/* 通用按钮 */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 18px; border-radius: 7px;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s; border: none;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg); border: 1px solid var(--border); color: var(--text-muted); }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
</style>
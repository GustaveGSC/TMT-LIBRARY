<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { Plus, Delete, FolderAdd, Refresh } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import http from '@/api/http'
import { useFinishedStore } from '@/stores/product'

const finishedStore = useFinishedStore()

// ── 数据 ──────────────────────────────────────────
const categories = ref([])   // [{id, name, color, sort_order, tags:[...]}]
const loading    = ref(false)
const error      = ref('')

// 预设颜色
const PRESET_COLORS = [
  '#c4883a', '#4a8fc0', '#9c6fba', '#6ab47a',
  '#d05a3c', '#3a7bc8', '#e6a817', '#5c7a5c',
]

// ── 展开状态 ──────────────────────────────────────
const expandedCats = ref(new Set())   // 展开的分类 id（-1 = 未分类）

function toggleCat(id) {
  if (expandedCats.value.has(id)) expandedCats.value.delete(id)
  else expandedCats.value.add(id)
}

// ── 未分类标签 ────────────────────────────────────
const _allTags = ref([])  // 所有标签（来自 GET /api/product/tags/）
const uncategorizedTags = computed(() =>
  _allTags.value.filter(t => !t.category_id)
)

// ── 拖拽排序 ──────────────────────────────────────
const listBodyRef = ref(null)
let sortableInstance = null

function initSortable() {
  if (sortableInstance) { sortableInstance.destroy(); sortableInstance = null }
  if (!listBodyRef.value) return
  sortableInstance = Sortable.create(listBodyRef.value, {
    animation: 150,
    handle: '.drag-handle',
    draggable: '.cat-group-sortable',
    ghostClass: 'drag-ghost',
    onEnd({ oldIndex, newIndex }) {
      if (oldIndex === newIndex) return
      const moved = categories.value.splice(oldIndex, 1)[0]
      categories.value.splice(newIndex, 0, moved)
      saveCategoryOrder()
    },
  })
}

async function saveCategoryOrder() {
  await Promise.all(
    categories.value.map((cat, idx) =>
      http.put(`/api/product/tags/categories/${cat.id}`, {
        name: cat.name,
        color: cat.color,
        sort_order: idx * 10,
      })
    )
  )
}

onBeforeUnmount(() => {
  if (sortableInstance) sortableInstance.destroy()
})

// ── 生命周期 ──────────────────────────────────────
onMounted(loadAll)

async function loadAll() {
  loading.value = true
  error.value   = ''
  try {
    const [catRes, tagRes] = await Promise.all([
      http.get('/api/product/tags/categories/'),
      http.get('/api/product/tags/'),
    ])
    if (catRes.success)  categories.value = catRes.data || []
    else error.value = catRes.message || '加载分类失败'
    if (tagRes.success)  _allTags.value = tagRes.data || []
    // 默认展开所有分类
    expandedCats.value = new Set([
      ...categories.value.map(c => c.id),
      -1,   // 未分类
    ])
    // 同步刷新产品库的标签缓存，使编辑框候选项实时更新
    finishedStore.reloadTagOptions()
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    loading.value = false
    await nextTick()
    initSortable()
  }
}

// ── 表单状态 ──────────────────────────────────────
// formType: '' | 'newCategory' | 'editCategory' | 'newTag' | 'editTag'
const formType      = ref('')
const editingId     = ref(null)    // 正在编辑的 id
const formName      = ref('')
const formColor     = ref('#c4883a')
const formCatId     = ref(null)    // 新增/编辑 tag 时所属分类 id（null = 未分类）
const formSortOrder = ref(0)
const formError     = ref('')
const submitting    = ref(false)

const formTitle = computed(() => {
  if (formType.value === 'newCategory')  return '新增分类'
  if (formType.value === 'editCategory') return '编辑分类'
  if (formType.value === 'newTag')       return '新增标签'
  if (formType.value === 'editTag')      return '编辑标签'
  return ''
})
const isCategory = computed(() => formType.value === 'newCategory' || formType.value === 'editCategory')
const isTag      = computed(() => formType.value === 'newTag'      || formType.value === 'editTag')

// ── 打开表单 ──────────────────────────────────────
function openNewCategory() {
  formType.value      = 'newCategory'
  editingId.value     = null
  formName.value      = ''
  formColor.value     = '#c4883a'
  formSortOrder.value = categories.value.length * 10
  formError.value     = ''
}

function openEditCategory(cat) {
  formType.value      = 'editCategory'
  editingId.value     = cat.id
  formName.value      = cat.name
  formColor.value     = cat.color
  formSortOrder.value = cat.sort_order ?? 0
  formError.value     = ''
}

function openNewTag(catId = null) {
  formType.value  = 'newTag'
  editingId.value = null
  formName.value  = ''
  formCatId.value = catId
  formError.value = ''
}

function openEditTag(tag) {
  formType.value  = 'editTag'
  editingId.value = tag.id
  formName.value  = tag.name
  formCatId.value = tag.category_id ?? null
  formError.value = ''
}

function handleCancel() {
  formType.value  = ''
  editingId.value = null
  formError.value = ''
}

// ── 提交 ──────────────────────────────────────────
async function handleSubmit() {
  const name = formName.value.trim()
  if (!name) { formError.value = '名称不能为空'; return }
  submitting.value = true
  formError.value  = ''
  try {
    let res
    if (formType.value === 'newCategory') {
      res = await http.post('/api/product/tags/categories/', {
        name, color: formColor.value, sort_order: formSortOrder.value,
      })
    } else if (formType.value === 'editCategory') {
      res = await http.put(`/api/product/tags/categories/${editingId.value}`, {
        name, color: formColor.value, sort_order: formSortOrder.value,
      })
    } else if (formType.value === 'newTag') {
      res = await http.post('/api/product/tags/', {
        name, category_id: formCatId.value || null,
      })
    } else if (formType.value === 'editTag') {
      res = await http.put(`/api/product/tags/${editingId.value}`, {
        name, category_id: formCatId.value || null,
      })
    }
    if (res.success) {
      formType.value = ''
      await loadAll()
    } else {
      formError.value = res.message || '操作失败'
    }
  } catch (e) {
    formError.value = e.message || '网络错误'
  } finally {
    submitting.value = false
  }
}

// ── 删除 ──────────────────────────────────────────
const deletingKey = ref(null)  // 'cat-{id}' | 'tag-{id}'

async function deleteCategory(cat) {
  deletingKey.value = `cat-${cat.id}`
  try {
    const res = await http.delete(`/api/product/tags/categories/${cat.id}`)
    if (res.success) await loadAll()
    else error.value = res.message || '删除失败'
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    deletingKey.value = null
  }
}

async function deleteTag(tag) {
  deletingKey.value = `tag-${tag.id}`
  try {
    const res = await http.delete(`/api/product/tags/${tag.id}`)
    if (res.success) await loadAll()
    else error.value = res.message || '删除失败'
  } catch (e) {
    error.value = e.message || '网络错误'
  } finally {
    deletingKey.value = null
  }
}

// ── 当前选中（高亮用）────────────────────────────
const selectedKey = computed(() => {
  if (!formType.value || editingId.value == null) return null
  if (isCategory.value) return `cat-${editingId.value}`
  if (isTag.value)      return `tag-${editingId.value}`
  return null
})
</script>

<template>
  <div class="product-label">

    <div v-if="error" class="error-bar">{{ error }}</div>

    <div class="layout">

      <!-- ── 左侧层级列表 ──────────────────────────── -->
      <div class="list-panel">
        <div class="panel-header">
          <span class="panel-title">标签管理</span>
          <div style="display:flex;gap:4px">
            <button class="btn-add" title="刷新" :disabled="loading" @click="loadAll">
              <el-icon :class="{ 'icon-spin': loading }"><Refresh /></el-icon>
            </button>
            <button class="btn-add" title="新增分类" @click="openNewCategory">
              <el-icon><FolderAdd /></el-icon>
            </button>
          </div>
        </div>

        <div v-if="loading" class="panel-state">加载中...</div>
        <div v-else-if="!categories.length && !uncategorizedTags.length" class="panel-state">
          暂无数据，点击右上角新增分类
        </div>

        <div v-else ref="listBodyRef" class="list-body">

          <!-- 有分类的 categories -->
          <!-- 未分类标签组（固定在最顶部） -->
          <div v-if="uncategorizedTags.length" class="cat-group">
            <div class="cat-row uncat" @click="toggleCat(-1)">
              <span class="expand-arrow">{{ expandedCats.has(-1) ? '▾' : '›' }}</span>
              <span class="cat-dot" style="background:#aaa"></span>
              <span class="cat-name">未分类</span>
              <span class="cat-count">{{ uncategorizedTags.length }}</span>
              <div class="row-actions">
                <button class="btn-node" title="新增未分类标签" @click.stop="openNewTag(null)">
                  <el-icon><Plus /></el-icon>
                </button>
              </div>
            </div>
            <template v-if="expandedCats.has(-1)">
              <div
                v-for="tag in uncategorizedTags" :key="tag.id"
                class="tag-row"
                :class="{ active: selectedKey === `tag-${tag.id}` }"
                @click="openEditTag(tag)"
              >
                <span class="tag-dot" style="background:#aaa"></span>
                <span class="tag-name">{{ tag.name }}</span>
                <div class="row-actions">
                  <button
                    class="btn-node danger"
                    :disabled="deletingKey === `tag-${tag.id}`"
                    @click.stop="deleteTag(tag)"
                  >
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
              </div>
            </template>
          </div>

          <div v-for="cat in categories" :key="cat.id" class="cat-group cat-group-sortable">
            <!-- 分类行 -->
            <div
              class="cat-row"
              :class="{ active: selectedKey === `cat-${cat.id}` }"
              @click="openEditCategory(cat)"
            >
              <span class="drag-handle" title="拖动排序" @click.stop>⠿</span>
              <span class="expand-arrow" @click.stop="toggleCat(cat.id)">
                {{ expandedCats.has(cat.id) ? '▾' : '›' }}
              </span>
              <span class="cat-dot" :style="{ background: cat.color }"></span>
              <span class="cat-name">{{ cat.name }}</span>
              <span class="cat-count">{{ (cat.tags || []).length }}</span>
              <div class="row-actions">
                <button class="btn-node" title="新增标签" @click.stop="openNewTag(cat.id)">
                  <el-icon><Plus /></el-icon>
                </button>
                <button
                  class="btn-node danger"
                  title="删除分类"
                  :disabled="deletingKey === `cat-${cat.id}`"
                  @click.stop="deleteCategory(cat)"
                >
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
            </div>

            <!-- 分类下的标签 -->
            <template v-if="expandedCats.has(cat.id)">
              <div
                v-for="tag in (cat.tags || [])" :key="tag.id"
                class="tag-row"
                :class="{ active: selectedKey === `tag-${tag.id}` }"
                @click="openEditTag(tag)"
              >
                <span class="tag-dot" :style="{ background: cat.color }"></span>
                <span class="tag-name">{{ tag.name }}</span>
                <div class="row-actions">
                  <button
                    class="btn-node danger"
                    :disabled="deletingKey === `tag-${tag.id}`"
                    @click.stop="deleteTag(tag)"
                  >
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
              </div>
              <div v-if="!(cat.tags || []).length" class="tag-empty">暂无标签</div>
            </template>
          </div>

        </div>
      </div>

      <!-- ── 右侧表单 ───────────────────────────── -->
      <div class="edit-panel">
        <div v-if="!formType" class="edit-empty">
          <span class="empty-hint">点击分类或标签编辑，或点击 + 新增</span>
        </div>

        <div v-else class="edit-form">
          <div class="form-title">{{ formTitle }}</div>

          <!-- 名称 -->
          <div class="form-row">
            <label class="form-label">名称 <span class="required">*</span></label>
            <input
              v-model="formName"
              class="form-input"
              placeholder="输入名称"
              @keyup.enter="handleSubmit"
            />
          </div>

          <!-- 分类的颜色 -->
          <template v-if="isCategory">
            <div class="form-row">
              <label class="form-label">颜色</label>
              <div class="color-picker">
                <span
                  v-for="c in PRESET_COLORS" :key="c"
                  class="color-dot"
                  :class="{ selected: formColor === c }"
                  :style="{ background: c }"
                  @click="formColor = c"
                ></span>
                <input type="color" v-model="formColor" class="color-custom" title="自定义颜色" />
              </div>
            </div>
            <!-- 预览 -->
            <div class="form-row">
              <label class="form-label">预览</label>
              <span class="label-preview" :style="{ background: formColor + '20', color: formColor, borderColor: formColor + '60' }">
                {{ formName || '标签示例' }}
              </span>
            </div>
          </template>

          <!-- 标签的所属分类 -->
          <template v-if="isTag">
            <div class="form-row">
              <label class="form-label">分类</label>
              <select v-model="formCatId" class="form-select">
                <option :value="null">— 未分类 —</option>
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
              </select>
            </div>
            <!-- 预览（颜色取自选中分类） -->
            <div class="form-row">
              <label class="form-label">预览</label>
              <span
                class="label-preview"
                :style="{
                  background: (categories.find(c => c.id === formCatId)?.color ?? '#aaa') + '20',
                  color:       categories.find(c => c.id === formCatId)?.color ?? '#aaa',
                  borderColor:(categories.find(c => c.id === formCatId)?.color ?? '#aaa') + '60',
                }"
              >{{ formName || '标签示例' }}</span>
            </div>
          </template>

          <div v-if="formError" class="form-error">{{ formError }}</div>

          <div class="form-actions">
            <button class="btn btn-secondary" @click="handleCancel">取消</button>
            <button class="btn btn-primary" :disabled="submitting" @click="handleSubmit">
              {{ submitting ? '提交中...' : (formType.startsWith('new') ? '新增' : '保存') }}
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.product-label { height: 100%; }

.error-bar {
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}

/* ── 布局 ─────────────────────────────────────── */
.layout { display: flex; gap: 12px; height: 400px; }

/* ── 左侧列表 ─────────────────────────────────── */
.list-panel {
  width: 240px; flex-shrink: 0;
  border: 1px solid var(--border); border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.8); flex-shrink: 0;
}
.panel-title { font-size: 12px; font-weight: 600; color: #5a4e42; }
.btn-add {
  width: 22px; height: 22px; border-radius: 5px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 12px; transition: all 0.15s;
}
.btn-add:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }
.btn-add:disabled { opacity: 0.5; cursor: not-allowed; }
.icon-spin { animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.panel-state {
  padding: 24px; text-align: center; font-size: 12px; color: var(--text-muted);
}
.list-body { flex: 1; overflow-y: auto; padding: 4px 0; }
.list-body::-webkit-scrollbar { width: 4px; }
.list-body::-webkit-scrollbar-track { background: transparent; }
.list-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* 分类行 */
.cat-row {
  display: flex; align-items: center; gap: 6px;
  padding: 0 10px 0 8px; height: 34px;
  cursor: pointer; transition: background 0.15s;
  font-size: 12px; font-weight: 600; color: #3a3028;
}
.cat-row:hover  { background: rgba(196,136,58,0.06); }
.cat-row.active { background: var(--accent-bg); }
.cat-row.uncat  { color: #6b5e4e; }

.drag-handle {
  width: 14px; flex-shrink: 0; text-align: center;
  color: #ccc; font-size: 12px; cursor: grab; user-select: none;
  display: none;
}
.cat-row:hover .drag-handle { display: block; color: #aaa; }
.drag-handle:active { cursor: grabbing; }

.drag-ghost { opacity: 0.4; background: var(--accent-bg) !important; }

.expand-arrow {
  width: 14px; flex-shrink: 0; text-align: center;
  color: #8a7a6a; font-size: 11px; cursor: pointer;
  user-select: none;
}
.cat-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.cat-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cat-count {
  font-size: 10px; font-weight: 400; color: #8a7a6a;
  background: #f0e8d8; border-radius: 8px; padding: 1px 5px;
  flex-shrink: 0;
}

/* 标签行 */
.tag-row {
  display: flex; align-items: center; gap: 6px;
  padding: 0 10px 0 28px; height: 30px;
  cursor: pointer; transition: background 0.15s;
  font-size: 12px; color: #3a3028;
}
.tag-row:hover  { background: rgba(196,136,58,0.04); }
.tag-row.active { background: var(--accent-bg); }

.tag-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; opacity: 0.8;
}
.tag-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.tag-empty {
  padding: 6px 28px; font-size: 11px; color: #aaa; font-style: italic;
}

/* 操作按钮 */
.row-actions { display: none; gap: 2px; margin-left: auto; }
.cat-row:hover .row-actions,
.tag-row:hover .row-actions { display: flex; }

.btn-node {
  width: 20px; height: 20px; border-radius: 4px;
  border: none; background: transparent; color: var(--text-muted);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 11px; transition: all 0.15s;
}
.btn-node:hover { background: var(--accent-bg); color: var(--accent); }
.btn-node.danger:hover { background: rgba(208,90,60,0.08); color: #d05a3c; }
.btn-node:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 右侧表单 ─────────────────────────────────── */
.edit-panel {
  flex: 1; border: 1px solid var(--border); border-radius: 10px;
  background: var(--bg-card); display: flex; flex-direction: column; overflow: hidden;
}
.edit-empty { flex: 1; display: flex; align-items: center; justify-content: center; }
.empty-hint { font-size: 12px; color: #8a7a6a; }

.edit-form { padding: 24px; }
.form-title { font-size: 15px; font-weight: 600; color: #2c2420; margin-bottom: 20px; }
.form-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.form-label {
  width: 48px; flex-shrink: 0; font-size: 12px; color: #6b5e4e;
  text-align: right; display: flex; align-items: center; justify-content: flex-end; gap: 2px;
}
.required { color: #d05a3c; font-size: 14px; line-height: 1; }
.form-input {
  flex: 1; height: 34px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 13px; font-family: inherit;
  outline: none; transition: border-color 0.2s;
}
.form-input:focus { border-color: var(--accent); }

.form-select {
  flex: 1; height: 34px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 13px; font-family: inherit;
  outline: none; cursor: pointer;
}
.form-select:focus { border-color: var(--accent); }

/* 颜色选择器 */
.color-picker { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.color-dot {
  width: 22px; height: 22px; border-radius: 50%;
  cursor: pointer; transition: transform 0.15s; border: 2px solid transparent;
}
.color-dot:hover { transform: scale(1.15); }
.color-dot.selected { border-color: #3a3028; transform: scale(1.15); }
.color-custom {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--border); cursor: pointer; padding: 0; background: none; outline: none;
}

/* 预览 */
.label-preview {
  display: inline-block; font-size: 12px; font-weight: 500;
  padding: 3px 10px; border-radius: 4px; border: 1px solid;
}

.form-error { font-size: 12px; color: #d05a3c; margin-bottom: 12px; padding-left: 60px; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }

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

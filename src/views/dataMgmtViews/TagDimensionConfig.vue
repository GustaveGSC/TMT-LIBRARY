<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

// ── 响应式状态 ────────────────────────────────────
const { canEditShipping } = usePermission()
const categories = ref([])   // [{ id, name, color, is_shipping_dim, tags: [{id, name, shipping_dim_enabled}] }]
const loading     = ref(false)
const saving      = ref(false)
let initialSnapshot = '[]'   // 保存前的初始状态快照，用于 diff

// ── 生命周期 ──────────────────────────────────────
onMounted(loadCategories)

// ── 方法 ──────────────────────────────────────────

async function loadCategories() {
  loading.value = true
  try {
    const res = await http.get('/api/product/tags/categories/')
    if (res.success) {
      categories.value = res.data.map(cat => ({
        id: cat.id, name: cat.name, color: cat.color, is_shipping_dim: !!cat.is_shipping_dim,
        tags: (cat.tags || []).map(t => ({ id: t.id, name: t.name, shipping_dim_enabled: !!t.shipping_dim_enabled })),
      }))
      initialSnapshot = JSON.stringify(categories.value)
    } else {
      ElMessage.error(res.message)
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  const initial = JSON.parse(initialSnapshot)
  const initCatMap = new Map(initial.map(c => [c.id, c]))
  const requests = []

  for (const cat of categories.value) {
    const before = initCatMap.get(cat.id)
    if (before && before.is_shipping_dim !== cat.is_shipping_dim) {
      requests.push(http.put(`/api/product/tags/categories/${cat.id}`, {
        name: cat.name, color: cat.color, is_shipping_dim: cat.is_shipping_dim,
      }))
    }
    const beforeTagMap = new Map((before?.tags || []).map(t => [t.id, t]))
    for (const tag of cat.tags) {
      const tagBefore = beforeTagMap.get(tag.id)
      if (tagBefore && tagBefore.shipping_dim_enabled !== tag.shipping_dim_enabled) {
        requests.push(http.put(`/api/product/tags/${tag.id}`, {
          name: tag.name, category_id: cat.id, shipping_dim_enabled: tag.shipping_dim_enabled,
        }))
      }
    }
  }

  if (requests.length === 0) {
    ElMessage.info('没有变更')
    return
  }

  saving.value = true
  try {
    const results = await Promise.all(requests)
    const failed = results.find(r => !r.success)
    if (failed) {
      ElMessage.error(failed.message)
    } else {
      ElMessage.success('保存成功')
      initialSnapshot = JSON.stringify(categories.value)
    }
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="tag-dim-config">

    <div class="config-header">
      <div class="header-left">
        <div class="config-title">标签分析维度</div>
        <div class="config-sub">配置哪些标签分类可用于发货图表按标签聚合分析，及分类下具体参与统计的标签</div>
      </div>
      <div v-if="canEditShipping" class="header-right">
        <button class="btn-save" :disabled="saving" @click="saveConfig">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && categories.length === 0" class="empty-state">
      <div class="empty-icon">🏷️</div>
      <div>暂无标签分类，请先在产品库「标签管理」中创建</div>
    </div>

    <!-- 加载 -->
    <div v-else-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>加载中…</span>
    </div>

    <!-- 分类列表 -->
    <div v-else class="cat-list">
      <div v-for="cat in categories" :key="cat.id" class="cat-card">
        <div class="cat-row">
          <span class="cat-dot" :style="{ background: cat.color }"></span>
          <span class="cat-name">{{ cat.name }}</span>
          <el-switch
            v-model="cat.is_shipping_dim"
            size="small"
            active-color="#c4883a"
            :disabled="!canEditShipping"
          />
          <span class="cat-switch-label">作为发货分析维度</span>
        </div>
        <div v-if="cat.tags.length" class="tag-list" :class="{ disabled: !cat.is_shipping_dim }">
          <label v-for="tag in cat.tags" :key="tag.id" class="tag-item">
            <el-checkbox
              v-model="tag.shipping_dim_enabled"
              :disabled="!cat.is_shipping_dim || !canEditShipping"
            />
            <span>{{ tag.name }}</span>
          </label>
        </div>
        <div v-else class="tag-empty">该分类下暂无标签</div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.tag-dim-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 680px;
}

.config-header {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
}
.config-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.config-sub   { font-size: 12px; color: var(--text-muted); }

.header-right { display: flex; gap: 8px; flex-shrink: 0; align-items: center; }

.btn-save {
  padding: 7px 16px;
  border-radius: 8px; border: none;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.18s;
  background: var(--accent); color: #fff;
}
.btn-save:hover:not(:disabled) { background: var(--accent-hover); }
.btn-save:disabled { opacity: 0.45; cursor: not-allowed; }

/* 空状态 / 加载 */
.empty-state, .loading-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; padding: 48px 0; color: var(--text-muted); font-size: 13px;
}
.empty-icon { font-size: 30px; }
.spinner {
  width: 24px; height: 24px;
  border: 2px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 分类列表 */
.cat-list {
  display: flex; flex-direction: column; gap: 10px;
}
.cat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  transition: box-shadow 0.15s;
}
.cat-card:hover { box-shadow: 0 2px 8px var(--shadow); }

.cat-row {
  display: flex; align-items: center; gap: 8px;
}
.cat-dot {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.cat-name {
  flex: 1; font-size: 13px; font-weight: 500; color: var(--text-primary);
}
.cat-switch-label {
  font-size: 12px; color: var(--text-muted);
}

.tag-list {
  display: flex; flex-wrap: wrap; gap: 10px 16px;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px dashed var(--border);
  transition: opacity 0.15s;
}
.tag-list.disabled { opacity: 0.45; }
.tag-item {
  display: flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--text-primary);
  cursor: pointer;
}
.tag-empty {
  margin-top: 10px; padding-top: 10px;
  border-top: 1px dashed var(--border);
  font-size: 12px; color: var(--text-muted);
}
</style>

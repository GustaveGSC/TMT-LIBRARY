<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

// ── 权限 ──────────────────────────────────────────
const { canEditShipping } = usePermission()

// ── 常量 ──────────────────────────────────────────
const STATUS_OPTIONS = [
  { label: '未审核',    value: 'pending'   },
  { label: '外贸客户',  value: 'export'    },
  { label: '内销客户',  value: 'domestic'  },
  { label: '非销售客户', value: 'non_sales' },
]
const STATUS_LABEL = Object.fromEntries(STATUS_OPTIONS.map(o => [o.value, o.label]))

// ── 响应式状态 ────────────────────────────────────
const items         = ref([])   // [{ customer_alias, occurrences, mapping }]
const loading       = ref(false)
const savingKey     = ref('')   // 正在保存的 customer_alias，用于单行 loading
const keyword       = ref('')
const onlyPending    = ref(false) // 仅看未审核（含尚未创建映射的简称）
const page          = ref(1)
const perPage       = 50
const total         = ref(0)

// 每行的可编辑草稿，key 为 customer_alias
const drafts = reactive({})

// ── 生命周期 ──────────────────────────────────────
onMounted(loadAliases)

let debounceTimer = null
watch(keyword, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    loadAliases()
  }, 400)
})

watch(onlyPending, () => {
  page.value = 1
  loadAliases()
})

// ── 方法 ──────────────────────────────────────────
function makeDraft(item) {
  const m = item.mapping
  return {
    status: m?.status ?? 'pending',
    country: m?.country ?? '',
    brand:   m?.brand ?? '',
    note:    m?.note ?? '',
    dirty:   false,
  }
}

async function loadAliases() {
  loading.value = true
  try {
    const res = await http.get('/api/shipping/finance-customer-aliases', {
      params: {
        keyword: keyword.value || undefined,
        status:  onlyPending.value ? 'pending' : undefined,
        page: page.value,
        per_page: perPage,
      },
    })
    if (res.success) {
      items.value = res.data.items
      total.value = res.data.total
      for (const item of items.value) {
        if (!drafts[item.customer_alias]) drafts[item.customer_alias] = makeDraft(item)
      }
    } else {
      ElMessage.error(res.message || '加载失败')
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function markDirty(alias) {
  drafts[alias].dirty = true
}

async function saveRow(item) {
  const draft = drafts[item.customer_alias]
  savingKey.value = item.customer_alias
  try {
    const res = await http.post('/api/shipping/finance-customer-aliases/mapping', {
      customer_alias: item.customer_alias,
      status: draft.status,
      country: draft.country || null,
      brand: draft.brand || null,
      note: draft.note || null,
    })
    if (res.success) {
      item.mapping = res.data
      draft.dirty = false
      ElMessage.success('保存成功')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingKey.value = ''
  }
}

function handlePageChange(p) {
  page.value = p
  loadAliases()
}
</script>

<template>
  <div class="fcm-config" v-loading="loading">

    <div class="config-header">
      <div class="config-title">外贸客户匹配</div>
      <div class="config-sub">财务原始数据"客户简称"列去重列表，人工审核归类为外贸客户/内销客户/非销售客户，并按需填写国家/品牌（不做自动解析）</div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-row">
      <el-input v-model="keyword" placeholder="按客户简称筛选" clearable style="width: 220px" />
      <el-checkbox v-model="onlyPending">仅看未审核</el-checkbox>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && items.length === 0" class="empty-tip">暂无客户简称数据</div>

    <!-- 列表 -->
    <div v-else class="alias-list">
      <div
        v-for="item in items"
        :key="item.customer_alias"
        class="alias-row"
        :class="`status-${drafts[item.customer_alias]?.status ?? 'pending'}`"
      >
        <div class="alias-main">
          <span class="alias-name" :title="item.customer_alias">{{ item.customer_alias }}</span>
          <span class="alias-count">{{ item.occurrences }} 条</span>
          <span class="alias-status" :class="`badge-${drafts[item.customer_alias]?.status ?? 'pending'}`">
            {{ STATUS_LABEL[drafts[item.customer_alias]?.status ?? 'pending'] }}
          </span>
        </div>
        <div class="alias-fields">
          <el-select
            v-model="drafts[item.customer_alias].status"
            :disabled="!canEditShipping"
            style="width: 110px"
            @change="markDirty(item.customer_alias)"
          >
            <el-option v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
          <el-input
            v-model="drafts[item.customer_alias].country"
            placeholder="国家/地区"
            :disabled="!canEditShipping"
            style="width: 130px"
            @input="markDirty(item.customer_alias)"
          />
          <el-input
            v-model="drafts[item.customer_alias].brand"
            placeholder="品牌"
            :disabled="!canEditShipping"
            style="width: 130px"
            @input="markDirty(item.customer_alias)"
          />
          <el-input
            v-model="drafts[item.customer_alias].note"
            placeholder="备注（可选）"
            :disabled="!canEditShipping"
            style="min-width: 260px; flex: 1"
            @input="markDirty(item.customer_alias)"
          />
          <button
            v-if="canEditShipping"
            class="save-btn"
            :disabled="!drafts[item.customer_alias].dirty || savingKey === item.customer_alias"
            @click="saveRow(item)"
          >
            {{ savingKey === item.customer_alias ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="total > perPage" class="pager-row">
      <el-pagination
        layout="prev, pager, next"
        :current-page="page"
        :page-size="perPage"
        :total="total"
        @current-change="handlePageChange"
      />
    </div>

  </div>
</template>

<style scoped>
.fcm-config {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.config-header {}
.config-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.config-sub   { font-size: 12px; color: var(--text-muted); }

.filter-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.empty-tip {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  padding: 32px 0;
}

.alias-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.alias-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  transition: border-color 0.18s, background 0.18s;
}
.alias-row.status-export {
  border-color: rgba(74, 154, 90, 0.3);
  background: rgba(74, 154, 90, 0.03);
}
.alias-row.status-domestic {
  border-color: rgba(74, 143, 192, 0.3);
  background: rgba(74, 143, 192, 0.03);
}
.alias-row.status-non_sales {
  border-color: rgba(138, 122, 106, 0.3);
  background: rgba(138, 122, 106, 0.03);
}

.alias-main {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 260px;
  flex-shrink: 0;
}
.alias-name {
  font-size: 13px;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.alias-count {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.alias-status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
  white-space: nowrap;
}
.badge-pending    { color: #c06030; background: rgba(192, 96, 48, 0.1); }
.badge-export     { color: #4a9a5a; background: rgba(74, 154, 90, 0.1); }
.badge-domestic   { color: #4a8fc0; background: rgba(74, 143, 192, 0.1); }
.badge-non_sales  { color: #8a7a6a; background: rgba(138, 122, 106, 0.1); }

.alias-fields {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.save-btn {
  padding: 6px 18px;
  background: var(--accent); color: #fff;
  border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; font-family: inherit;
  cursor: pointer; transition: background 0.18s;
}
.save-btn:hover:not(:disabled) { background: var(--accent-hover); }
.save-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.pager-row {
  display: flex;
  justify-content: center;
}
</style>

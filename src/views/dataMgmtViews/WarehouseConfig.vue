<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

// ── 响应式状态 ────────────────────────────────────
const warehouses = ref([])   // [{ warehouse_name, is_excluded }]
const loading    = ref(false)
const saving     = ref(false)

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  await loadWarehouses()
})

// ── 方法 ──────────────────────────────────────────

async function loadWarehouses() {
  loading.value = true
  try {
    const res = await http.get('/api/shipping/warehouses')
    if (res.success) warehouses.value = res.data
    else ElMessage.error(res.message)
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function saveFilters() {
  saving.value = true
  try {
    const res = await http.post('/api/shipping/warehouses/filter', warehouses.value)
    if (res.success) ElMessage.success('保存成功')
    else ElMessage.error(res.message || '保存失败')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="warehouse-config" v-loading="loading">

    <div class="config-header">
      <div class="config-title">仓库过滤配置</div>
      <div class="config-sub">配置销退清单导入时需要忽略的仓库，已排除的仓库数据不会被导入</div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && warehouses.length === 0" class="empty-tip">
      暂无仓库数据，请先导入销退清单
    </div>

    <!-- 仓库列表 -->
    <div v-else class="warehouse-list">
      <div
        v-for="item in warehouses"
        :key="item.warehouse_name"
        class="warehouse-row"
        :class="{ excluded: item.is_excluded }"
      >
        <span class="wh-name">{{ item.warehouse_name }}</span>
        <div class="wh-toggle">
          <span class="wh-status-label" :class="item.is_excluded ? 'excluded-label' : 'included-label'">
            {{ item.is_excluded ? '已排除' : '正常导入' }}
          </span>
          <el-switch
            v-model="item.is_excluded"
            active-color="#c06030"
            inactive-color="#4a9a5a"
            :active-text="''"
            :inactive-text="''"
          />
        </div>
      </div>
    </div>

    <!-- 保存按钮 -->
    <div v-if="warehouses.length > 0" class="save-row">
      <button class="save-btn" :disabled="saving" @click="saveFilters">
        {{ saving ? '保存中…' : '保存配置' }}
      </button>
    </div>

  </div>
</template>

<style scoped>
.warehouse-config {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.config-header {}
.config-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.config-sub   { font-size: 12px; color: var(--text-muted); }

.empty-tip {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  padding: 32px 0;
}

.warehouse-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.warehouse-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  transition: border-color 0.18s, background 0.18s;
}
.warehouse-row.excluded {
  border-color: rgba(192, 96, 48, 0.3);
  background: rgba(192, 96, 48, 0.03);
}

.wh-name {
  font-size: 13px;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wh-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.wh-status-label {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
}
.included-label {
  color: #4a9a5a;
  background: rgba(74, 154, 90, 0.1);
}
.excluded-label {
  color: #c06030;
  background: rgba(192, 96, 48, 0.1);
}

.save-row {
  display: flex;
  justify-content: flex-end;
}

.save-btn {
  padding: 9px 28px;
  background: var(--accent); color: #fff;
  border: none; border-radius: 8px;
  font-size: 13px; font-weight: 500; font-family: inherit;
  cursor: pointer; transition: background 0.18s;
}
.save-btn:hover:not(:disabled) { background: var(--accent-hover); }
.save-btn:disabled { opacity: 0.45; cursor: not-allowed; }
</style>

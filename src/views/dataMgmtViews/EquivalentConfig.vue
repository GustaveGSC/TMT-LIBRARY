<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

// ── 响应式状态 ────────────────────────────────────
const { canEditShipping } = usePermission()
const pairs     = ref([])    // [{id, code_a, name_a, code_b, name_b, note, created_at}]
const loading   = ref(false)
const adding    = ref(false)
const form      = ref({ code_a: '', code_b: '', note: '' })
const formError = ref('')

// ── 生命周期 ──────────────────────────────────────
onMounted(loadPairs)

// ── 方法 ──────────────────────────────────────────
async function loadPairs() {
  loading.value = true
  try {
    const res = await http.get('/api/shipping/equivalents')
    if (res.success) pairs.value = res.data
    else ElMessage.error(res.message || '加载失败')
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function addPair() {
  formError.value = ''
  const code_a = form.value.code_a.trim()
  const code_b = form.value.code_b.trim()
  const note   = form.value.note.trim()
  if (!code_a || !code_b) {
    formError.value = '请填写两个产成品编码'
    return
  }
  if (code_a === code_b) {
    formError.value = '两个编码不能相同'
    return
  }
  adding.value = true
  try {
    const res = await http.post('/api/shipping/equivalents', { code_a, code_b, note: note || undefined })
    if (res.success) {
      pairs.value.unshift(res.data)
      form.value = { code_a: '', code_b: '', note: '' }
      ElMessage.success('已新增通用件对，配置保存后如需更新历史数据请前往"数据维护"执行"重建全部成品组合"')
    } else {
      formError.value = res.message || '新增失败'
    }
  } catch {
    formError.value = '新增失败'
  } finally {
    adding.value = false
  }
}

async function deletePair(pair) {
  try {
    await ElMessageBox.confirm(
      `确认删除通用件对 ${pair.code_a} ↔ ${pair.code_b}？`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res = await http.delete(`/api/shipping/equivalents/${pair.id}`)
    if (res.success) {
      pairs.value = pairs.value.filter(p => p.id !== pair.id)
      ElMessage.success('已删除，如需更新历史数据请前往"数据维护"执行"重建全部成品组合"')
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>

<template>
  <div class="equiv-config" v-loading="loading">

    <div class="config-header">
      <div class="config-title">产成品通用件配置</div>
      <div class="config-sub">声明两个产成品可互换（如 A01 ↔ B01），发货匹配时任意一个均可满足对方的槽位需求</div>
    </div>

    <!-- 新增表单 -->
    <div v-if="canEditShipping" class="add-form">
      <div class="add-inputs">
        <el-input
          v-model="form.code_a"
          placeholder="产成品编码 A"
          size="small"
          class="code-input"
          @keyup.enter="addPair"
        />
        <span class="swap-icon">⇌</span>
        <el-input
          v-model="form.code_b"
          placeholder="产成品编码 B"
          size="small"
          class="code-input"
          @keyup.enter="addPair"
        />
        <el-input
          v-model="form.note"
          placeholder="备注（可选）"
          size="small"
          class="note-input"
          @keyup.enter="addPair"
        />
        <button class="add-btn" :disabled="adding" @click="addPair">
          {{ adding ? '新增中…' : '新增' }}
        </button>
      </div>
      <div v-if="formError" class="form-error">{{ formError }}</div>
    </div>

    <!-- 列表 -->
    <div v-if="pairs.length === 0 && !loading" class="empty-tip">
      暂无通用件配置
    </div>

    <div v-else class="pair-list">
      <div v-for="pair in pairs" :key="pair.id" class="pair-row">
        <div class="pair-codes">
          <div class="pair-code-item">
            <span class="code-tag">{{ pair.code_a }}</span>
            <span class="code-name">{{ pair.name_a || '—' }}</span>
          </div>
          <span class="pair-arrow">⇌</span>
          <div class="pair-code-item">
            <span class="code-tag">{{ pair.code_b }}</span>
            <span class="code-name">{{ pair.name_b || '—' }}</span>
          </div>
        </div>
        <div class="pair-right">
          <span v-if="pair.note" class="pair-note">{{ pair.note }}</span>
          <button v-if="canEditShipping" class="del-btn" @click="deletePair(pair)">删除</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.equiv-config {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.config-header {}
.config-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.config-sub   { font-size: 12px; color: var(--text-muted); line-height: 1.6; }

/* 新增表单 */
.add-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.add-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.code-input { width: 160px; }
.note-input { flex: 1; min-width: 120px; }
.swap-icon {
  font-size: 16px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.add-btn {
  padding: 5px 18px;
  background: var(--accent); color: #fff;
  border: none; border-radius: 7px;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: background 0.18s;
  flex-shrink: 0; white-space: nowrap;
}
.add-btn:hover:not(:disabled) { background: var(--accent-hover); }
.add-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.form-error { font-size: 12px; color: #e06040; }

/* 列表 */
.empty-tip {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  padding: 32px 0;
}
.pair-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pair-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  gap: 12px;
}
.pair-codes {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}
.pair-code-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.code-tag {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  background: rgba(196,136,58,0.1);
  border-radius: 5px;
  padding: 2px 8px;
  display: inline-block;
  letter-spacing: 0.03em;
}
.code-name {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
}
.pair-arrow {
  font-size: 18px;
  color: var(--text-muted);
  flex-shrink: 0;
  margin-top: -4px;
}
.pair-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.pair-note {
  font-size: 12px;
  color: var(--text-muted);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.del-btn {
  padding: 4px 12px;
  border: 1px solid rgba(192,96,48,0.3);
  border-radius: 6px;
  background: transparent;
  color: #c06030;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s;
  flex-shrink: 0;
}
.del-btn:hover {
  background: rgba(192,96,48,0.08);
  border-color: rgba(192,96,48,0.6);
}
</style>

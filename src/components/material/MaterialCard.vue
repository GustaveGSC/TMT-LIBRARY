<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, watch } from 'vue'
import { WarningFilled, Picture } from '@element-plus/icons-vue'
import http from '@/api/http'

// ── Props / Emits ─────────────────────────────────
const props = defineProps({
  visible: { type: Boolean, default: false },
  code:    { type: String,  default: '' },
})
const emit = defineEmits(['update:visible', 'saved'])

// ── 响应式状态 ────────────────────────────────────
const detail   = ref(null)
const loading  = ref(false)
const saving   = ref(false)
const errorMsg = ref('')

// 人工可编辑的字段草稿。ERP 侧字段（code/name/group/大类）只读展示，
// 它们归 import_product_raw 所有，不在这里改。
const form = ref({ short_name: '', category: '', spec: '', remark: '', is_disabled: false })

// ── 加载详情 ──────────────────────────────────────
async function loadDetail() {
  if (!props.code) return
  loading.value  = true
  errorMsg.value = ''
  detail.value   = null
  try {
    const res = await http.get(`/api/material/items/${encodeURIComponent(props.code)}`)
    if (res.success) {
      detail.value = res.data
      form.value = {
        short_name:  res.data.short_name  || '',
        category:    res.data.category    || '',
        spec:        res.data.spec        || '',
        remark:      res.data.remark      || '',
        is_disabled: !!res.data.is_disabled,
      }
    } else {
      errorMsg.value = res.message || '加载失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ── 保存 ──────────────────────────────────────────
async function handleSave() {
  saving.value   = true
  errorMsg.value = ''
  try {
    const res = await http.put(
      `/api/material/items/${encodeURIComponent(props.code)}`, form.value,
    )
    if (res.success) {
      // 用服务端返回值回写，并通知列表更新对应行
      detail.value = { ...detail.value, ...(res.data || form.value) }
      emit('saved', detail.value)
      close()
    } else {
      errorMsg.value = res.message || '保存失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    saving.value = false
  }
}

function close() { emit('update:visible', false) }

// 打开时才拉详情，关闭不清理（同一条再打开可秒开）
watch(() => props.visible, v => { if (v) loadDetail() })
</script>

<template>
  <el-dialog
    :model-value="props.visible"
    title="物料卡片"
    width="560"
    align-center
    append-to-body
    @update:model-value="emit('update:visible', $event)"
  >
    <div class="material-card">

      <div v-if="loading" class="state-tip">加载中...</div>

      <div v-else-if="errorMsg" class="error-bar">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ errorMsg }}</span>
      </div>

      <template v-else-if="detail">
        <!-- 图片 -->
        <div class="mc-image">
          <img v-if="detail.cover_image" :src="detail.cover_image" alt="" />
          <div v-else class="mc-image-empty">
            <el-icon><Picture /></el-icon>
            <span>暂无图片</span>
          </div>
        </div>

        <!-- ERP 权威字段：只读 -->
        <div class="mc-section">
          <div class="mc-section-title">ERP 信息（只读）</div>
          <div class="mc-field"><label>编码</label><span class="mono">{{ detail.code }}</span></div>
          <div class="mc-field"><label>名称</label><span>{{ detail.name }}</span></div>
          <div class="mc-field">
            <label>分组</label>
            <span>{{ detail.group_code }} · {{ detail.group_name || '—' }}</span>
          </div>
          <div class="mc-field">
            <label>大类</label>
            <span v-if="(detail.categories || []).length">{{ (detail.category_labels || detail.categories).join(' / ') }}</span>
            <span v-else class="muted">未分类</span>
          </div>
        </div>

        <!-- 人工维护字段 -->
        <div class="mc-section">
          <div class="mc-section-title">人工维护</div>
          <div class="mc-field">
            <label>短名</label>
            <input v-model="form.short_name" class="mc-input" placeholder="录入/挑选时显示的短名称" />
          </div>
          <div class="mc-field">
            <label>分类</label>
            <input v-model="form.category" class="mc-input" placeholder="自由文本，用于下拉分组" />
          </div>
          <div class="mc-field">
            <label>规格</label>
            <input v-model="form.spec" class="mc-input" placeholder="规格" />
          </div>
          <div class="mc-field mc-field-top">
            <label>备注</label>
            <textarea v-model="form.remark" class="mc-textarea" rows="3"></textarea>
          </div>
          <label class="mc-check">
            <input v-model="form.is_disabled" type="checkbox" />
            <span>停用（不进入后续选择候选）</span>
          </label>
        </div>

        <div class="mc-actions">
          <button class="btn btn-secondary" @click="close">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="handleSave">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.material-card {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 13px; color: var(--text-primary);
}
.state-tip { font-size: 13px; color: #6b5e4e; padding: 32px 0; text-align: center; }
.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}

/* ── 图片 ─────────────────────────────────────── */
.mc-image {
  height: 180px; margin-bottom: 16px;
  border: 1px solid var(--border); border-radius: 12px;
  background: var(--bg); overflow: hidden;
  display: flex; align-items: center; justify-content: center;
}
.mc-image img { max-width: 100%; max-height: 100%; object-fit: contain; }
.mc-image-empty {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  color: var(--text-muted); font-size: 12px;
}
.mc-image-empty .el-icon { font-size: 28px; }

/* ── 分区 ─────────────────────────────────────── */
.mc-section {
  margin-bottom: 18px; padding: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 12px;
}
.mc-section-title {
  font-size: 11px; font-weight: 700; color: var(--accent);
  letter-spacing: 0.08em; margin-bottom: 12px;
}
.mc-field { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.mc-field:last-of-type { margin-bottom: 0; }
.mc-field-top { align-items: flex-start; }
.mc-field label {
  width: 42px; flex-shrink: 0;
  font-size: 12px; color: #6b5e4e; text-align: right;
}
.mc-field > span { flex: 1; min-width: 0; word-break: break-all; }
.mono { font-family: monospace; font-size: 12px; }
.muted { color: #6b5e4e; }

.mc-input {
  flex: 1; height: 30px; padding: 0 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none;
  transition: border-color 0.2s;
}
.mc-input:focus { border-color: var(--accent); }
.mc-textarea {
  flex: 1; padding: 7px 10px;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text-primary);
  font-size: 12px; font-family: inherit; outline: none; resize: vertical;
  transition: border-color 0.2s;
}
.mc-textarea:focus { border-color: var(--accent); }

.mc-check {
  display: flex; align-items: center; gap: 6px;
  margin-top: 12px; padding-top: 10px;
  border-top: 1px solid var(--border);
  font-size: 12px; color: #3a3028; cursor: pointer;
}

/* ── 操作 ─────────────────────────────────────── */
.mc-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn {
  padding: 6px 18px; border-radius: 7px;
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s; border: none;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg); border: 1px solid var(--border); color: #6b5e4e; }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
</style>

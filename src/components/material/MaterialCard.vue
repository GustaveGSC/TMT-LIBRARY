<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch } from 'vue'
import { WarningFilled, Picture, Upload, Delete } from '@element-plus/icons-vue'
import { pickFile } from '@/utils/download'
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
//
// ⚠️ disabledMode 是三态，对应后端 product_material.is_disabled 这一列：
//   'follow' → null  跟随 ERP 默认判定（状态失效 或 名称含停用关键词）
//   'off'    → true  人工强制停用
//   'on'     → false 人工强制启用
// 以前这里错误地用最终生效值 is_disabled 填一个普通复选框再原样回传，
// 结果只要打开卡片保存一次，就会把「跟随默认」静默写成「人工覆盖」。
const form = ref({ short_name: '', category: '', spec: '', remark: '', disabledMode: 'follow' })

// 新选的图片（base64）；空串表示未改动
const newImage = ref('')

const DISABLED_MODES = [
  { value: 'follow', label: '跟随 ERP 默认' },
  { value: 'off',    label: '人工强制停用' },
  { value: 'on',     label: '人工强制启用' },
]

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
      const ov = res.data.is_disabled_override
      form.value = {
        short_name: res.data.short_name || '',
        category:   res.data.category   || '',
        spec:       res.data.spec       || '',
        remark:     res.data.remark     || '',
        disabledMode: ov === null || ov === undefined ? 'follow' : (ov ? 'off' : 'on'),
      }
      newImage.value = ''
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
    // 有新图先上传，拿到 OSS URL 后随属性一起保存
    if (newImage.value.startsWith('data:')) {
      const up = await http.post(
        `/api/material/items/${encodeURIComponent(props.code)}/image`,
        { data_url: newImage.value },
      )
      if (!up.success) { errorMsg.value = up.message || '图片上传失败'; return }
      detail.value = { ...detail.value, ...(up.data || {}) }
      newImage.value = ''
    }
    const payload = {
      short_name: form.value.short_name,
      category:   form.value.category,
      spec:       form.value.spec,
      remark:     form.value.remark,
      // 'follow' 必须显式传 null，后端才会把该列置回「跟随默认」
      is_disabled: form.value.disabledMode === 'follow'
        ? null : form.value.disabledMode === 'off',
    }
    const res = await http.put(
      `/api/material/items/${encodeURIComponent(props.code)}`, payload,
    )
    if (res.success) {
      // 用服务端返回值回写，并通知列表更新对应行
      detail.value = { ...detail.value, ...(res.data || {}) }
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

// ── 图片 ──────────────────────────────────────────
async function chooseImage() {
  const file = await pickFile('image/*')
  if (!file) return
  if (file.size > 5 * 1024 * 1024) { errorMsg.value = '图片不能超过 5MB'; return }
  errorMsg.value = ''
  newImage.value = await new Promise((resolve) => {
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result || ''))
    fr.onerror = () => resolve('')
    fr.readAsDataURL(file)
  })
}

function clearNewImage() { newImage.value = '' }

// 优先显示新选的图，其次是已保存的 OSS 图（带时间戳破缓存）
const shownImage = computed(() => {
  if (newImage.value) return newImage.value
  const d = detail.value
  if (!d?.cover_image) return ''
  return d.img_updated_at ? `${d.cover_image}?t=${d.img_updated_at}` : d.cover_image
})

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
          <img v-if="shownImage" :src="shownImage" alt="" />
          <div v-else class="mc-image-empty">
            <el-icon><Picture /></el-icon>
            <span>暂无图片</span>
          </div>
        </div>
        <div class="mc-image-bar">
          <button class="mc-img-btn" @click="chooseImage">
            <el-icon><Upload /></el-icon><span>{{ shownImage ? '更换图片' : '选择图片' }}</span>
          </button>
          <button v-if="newImage" class="mc-img-btn danger" @click="clearNewImage">
            <el-icon><Delete /></el-icon><span>撤销选图</span>
          </button>
          <span v-if="newImage" class="mc-img-tip">保存后才会上传</span>
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
            <label>状态</label>
            <span>{{ detail.status || '—' }}</span>
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
            <label>简称</label>
            <input v-model="form.short_name" class="mc-input" placeholder="录入/挑选时显示的简称" />
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
          <div class="mc-field mc-field-top mc-disabled">
            <label>停用</label>
            <div class="dm-wrap">
              <div class="dm-opts">
                <button
                  v-for="o in DISABLED_MODES"
                  :key="o.value"
                  class="dm-opt"
                  :class="{ on: form.disabledMode === o.value }"
                  @click="form.disabledMode = o.value"
                >{{ o.label }}</button>
              </div>
              <div class="dm-hint">
                <template v-if="form.disabledMode === 'follow'">
                  跟随 ERP 判定：状态为「失效」或名称含停用关键词时即视为停用。
                  当前生效值：<b>{{ detail.is_disabled ? '停用' : '启用' }}</b>
                </template>
                <template v-else>
                  人工覆盖，<b>不再跟随 ERP</b>——即使 ERP 状态变化也保持此设置。
                </template>
              </div>
            </div>
          </div>
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

.mc-image-bar { display: flex; align-items: center; gap: 8px; margin: -8px 0 16px; }
.mc-img-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-card);
  color: var(--text-primary); font-size: 12px; font-family: inherit; cursor: pointer;
  transition: all 0.15s;
}
.mc-img-btn:hover { border-color: var(--accent); color: var(--accent); }
.mc-img-btn.danger:hover { border-color: #d05a3c; color: #d05a3c; }
.mc-img-tip { font-size: 11px; color: var(--accent); }

/* 三态停用 */
.mc-disabled { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
.dm-wrap { flex: 1; min-width: 0; }
.dm-opts { display: flex; gap: 6px; flex-wrap: wrap; }
.dm-opt {
  padding: 4px 12px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg);
  color: var(--text-primary); font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.dm-opt:hover { border-color: var(--accent); color: var(--accent); }
.dm-opt.on {
  border-color: #4a8fc0; background: rgba(74,143,192,0.12);
  color: #4a8fc0; font-weight: 600;
}
.dm-hint { margin-top: 6px; font-size: 11px; color: #6b5e4e; line-height: 1.6; }
.dm-hint b { color: var(--text-primary); }

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

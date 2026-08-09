<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

// 供应商是成本域数据。usePermission 返回普通布尔值不是 ref，不能写 .value。
const { canEditRd } = usePermission()

// ── 数据 ──────────────────────────────────────────
const items    = ref([])
const loading  = ref(false)
const errorMsg = ref('')
const keyword  = ref('')

// 展开的供应商 id → 物料明细。明细按需拉取并缓存，避免列表页一次性拖全部。
const expanded = ref(new Set())
const details  = ref({})          // { id: { loading, rows } }

// ── 新建 / 编辑表单 ────────────────────────────────
const formOpen   = ref(false)
const editingId  = ref(null)      // null = 新建
const form       = ref({ name: '', contact: '', remark: '' })
const saving     = ref(false)

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return items.value
  return items.value.filter(x =>
    (x.name || '').toLowerCase().includes(k) ||
    (x.contact || '').toLowerCase().includes(k) ||
    (x.groups || []).some(g => (g.code + g.name).toLowerCase().includes(k)))
})

// ── 加载 ──────────────────────────────────────────
async function load() {
  loading.value  = true
  errorMsg.value = ''
  try {
    const res = await http.get('/api/material/suppliers')
    if (res.success) items.value = res.data?.items || []
    else errorMsg.value = res.message || '加载失败'
  } catch (e) {
    errorMsg.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

async function toggleExpand(row) {
  const next = new Set(expanded.value)
  if (next.has(row.id)) {
    next.delete(row.id)
    expanded.value = next
    return
  }
  next.add(row.id)
  expanded.value = next
  if (details.value[row.id]) return          // 已缓存
  details.value = { ...details.value, [row.id]: { loading: true, rows: [] } }
  try {
    const res = await http.get(`/api/material/suppliers/${row.id}/materials`)
    details.value = {
      ...details.value,
      [row.id]: { loading: false, rows: res.success ? (res.data || []) : [] },
    }
  } catch {
    details.value = { ...details.value, [row.id]: { loading: false, rows: [] } }
  }
}

// ── 新建 / 编辑 ───────────────────────────────────
function openCreate() {
  editingId.value = null
  form.value = { name: '', contact: '', remark: '' }
  formOpen.value = true
}

function openEdit(row) {
  editingId.value = row.id
  form.value = { name: row.name || '', contact: row.contact || '', remark: row.remark || '' }
  formOpen.value = true
}

async function submit() {
  if (!form.value.name.trim()) { ElMessage.warning('请填写供应商名称'); return }
  saving.value = true
  try {
    const body = {
      name: form.value.name.trim(),
      contact: form.value.contact.trim(),
      remark: form.value.remark.trim(),
    }
    const res = editingId.value
      ? await http.patch(`/api/material/suppliers/${editingId.value}`, body)
      : await http.post('/api/material/suppliers', body)
    if (res.success) {
      ElMessage.success(editingId.value ? '已保存' : '已新建')
      formOpen.value = false
      // 改名会影响关联汇总的展示名，整表重拉一次
      await load()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message || '网络错误')
  } finally {
    saving.value = false
  }
}

// ── 删除（两段式：后端不带 force 会先告知影响面）────
async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除供应商「${row.name}」？`, '确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }

  let res = await http.delete(`/api/material/suppliers/${row.id}`)
  if (!res.success) {
    // 有价格记录引用时后端返回 400 + price_count，用它的原文做二次确认；
    // 价格记录不会被删除，只是不再归属任何供应商。
    const cnt = res.data?.price_count
    if (cnt == null) { ElMessage.error(res.message || '删除失败'); return }
    try {
      await ElMessageBox.confirm(res.message, '仍要删除？', {
        type: 'warning', confirmButtonText: '仍然删除', cancelButtonText: '取消',
      })
    } catch { return }
    res = await http.delete(`/api/material/suppliers/${row.id}?force=1`)
  }
  if (res.success) {
    ElMessage.success('已删除')
    const d = { ...details.value }; delete d[row.id]; details.value = d
    await load()
  } else {
    ElMessage.error(res.message || '删除失败')
  }
}

// ── 生命周期 ──────────────────────────────────────
onMounted(load)
</script>

<template>
  <div class="supplier-panel">

    <div v-if="errorMsg" class="error-bar">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ errorMsg }}</span>
    </div>

    <!-- 工具条 -->
    <div class="toolbar">
      <input v-model="keyword" class="sp-input search" placeholder="搜索供应商、联系方式、分组" />
      <span class="spacer"></span>
      <span class="count-hint">共 <b>{{ filtered.length }}</b> 家</span>
      <button v-if="canEditRd" class="btn btn-primary sm" @click="openCreate">+ 新建供应商</button>
    </div>

    <!-- 表格 -->
    <div class="table-wrap">
      <table class="sp-table">
        <thead>
          <tr>
            <th style="width:170px">供应商</th>
            <th style="width:130px">联系方式</th>
            <th style="width:110px" class="ta-c">关联物料</th>
            <th>涉及分组</th>
            <th style="width:110px">最近报价</th>
            <th v-if="canEditRd" style="width:110px" class="ta-c">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in filtered" :key="row.id">
            <tr class="sp-row">
              <td class="sp-name">{{ row.name }}</td>
              <td>{{ row.contact || '—' }}</td>
              <td class="ta-c">
                <!-- 关联物料与分组都是从价格记录反推的，不是手工维护的 -->
                <button v-if="row.material_count" class="link-btn" @click="toggleExpand(row)">
                  {{ row.material_count }} 个
                  <span class="caret">{{ expanded.has(row.id) ? '▴' : '▾' }}</span>
                </button>
                <span v-else class="cell-empty">—</span>
              </td>
              <td>
                <template v-if="(row.groups || []).length">
                  <span v-for="g in row.groups" :key="g.code" class="grp-tag">
                    {{ g.code }}<template v-if="g.name"> {{ g.name }}</template>
                  </span>
                  <!-- groups_truncated 由后端用独立的 COUNT(DISTINCT) 与展示条数比对得出，
                       即使 GROUP_CONCAT 被静默截断也能提示 -->
                  <span v-if="row.groups_truncated" class="grp-more">
                    等 {{ row.group_count }} 个分组
                  </span>
                </template>
                <span v-else class="cell-empty">—</span>
              </td>
              <td>{{ row.last_quote_date || '—' }}</td>
              <td v-if="canEditRd" class="ta-c">
                <button class="link-btn" @click="openEdit(row)">编辑</button>
                <button class="link-btn danger" @click="remove(row)">删除</button>
              </td>
            </tr>

            <!-- 物料明细 -->
            <tr v-if="expanded.has(row.id)" class="sp-detail-row">
              <td :colspan="canEditRd ? 6 : 5">
                <div v-if="details[row.id]?.loading" class="detail-tip">加载中...</div>
                <table v-else-if="details[row.id]?.rows?.length" class="sp-subtable">
                  <thead>
                    <tr>
                      <th style="width:180px">物料编码</th>
                      <th>名称</th>
                      <th style="width:170px">分组</th>
                      <th style="width:110px" class="ta-r">单价</th>
                      <th style="width:100px">报价日期</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="m in details[row.id].rows" :key="m.code">
                      <td class="mono">{{ m.code }}</td>
                      <td class="ellip">{{ m.name || '—' }}</td>
                      <td>{{ m.group_code }}<template v-if="m.group_name"> · {{ m.group_name }}</template></td>
                      <td class="ta-r price-val">¥{{ Number(m.unit_price).toFixed(4) }}</td>
                      <td>{{ m.price_date || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
                <div v-else class="detail-tip">暂无物料明细</div>
              </td>
            </tr>
          </template>

          <tr v-if="!loading && !filtered.length">
            <td :colspan="canEditRd ? 6 : 5" class="sp-empty">
              {{ keyword ? '没有匹配的供应商' : '还没有供应商，点右上角新建' }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="loading" class="detail-tip">加载中...</div>
    </div>

    <!-- 新建 / 编辑 -->
    <el-dialog
      v-model="formOpen"
      :title="editingId ? '编辑供应商' : '新建供应商'"
      width="440"
      align-center
      append-to-body
    >
      <div class="sp-form">
        <div class="sp-field">
          <label>名称 <b>*</b></label>
          <input v-model="form.name" class="sp-input" placeholder="供应商名称" maxlength="64" />
        </div>
        <div class="sp-field">
          <label>联系方式</label>
          <input v-model="form.contact" class="sp-input" placeholder="联系人 / 电话，可留空" maxlength="64" />
        </div>
        <div class="sp-field top">
          <label>备注</label>
          <textarea v-model="form.remark" class="sp-textarea" rows="3"></textarea>
        </div>
        <p v-if="editingId" class="sp-hint">
          改名后，已归属该供应商的价格记录会同步显示新名称。
        </p>
      </div>
      <template #footer>
        <button class="btn btn-secondary sm" @click="formOpen = false">取消</button>
        <button class="btn btn-primary sm" :disabled="saving" @click="submit">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.supplier-panel {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 13px; color: var(--text-primary);
}

.error-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 10px; padding: 8px 12px;
  background: rgba(208,90,60,0.06); border: 1px solid rgba(208,90,60,0.2);
  border-radius: 7px; color: #d05a3c; font-size: 12px;
}

/* ── 工具条 ───────────────────────────────────── */
.toolbar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px; flex-shrink: 0;
}
.spacer { margin-left: auto; }
.count-hint { font-size: 12px; color: var(--text-secondary); }
.count-hint b { color: var(--text-primary); }

.sp-input, .sp-textarea {
  padding: 5px 10px; font-size: 13px; font-family: inherit;
  color: var(--text-primary); background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 8px;
  outline: none; transition: border-color 0.15s;
}
.sp-input:focus, .sp-textarea:focus { border-color: var(--accent); }
.sp-input.search { width: 260px; }
.sp-textarea { width: 100%; resize: vertical; }

.btn {
  padding: 6px 16px; border-radius: 8px; border: none;
  font-size: 13px; font-family: inherit; cursor: pointer; transition: all 0.2s;
}
.btn.sm { padding: 5px 14px; font-size: 12px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.btn-secondary {
  background: var(--bg-card); border: 1px solid var(--border); color: var(--text-primary);
}
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); }

/* ── 表格 ─────────────────────────────────────── */
.table-wrap {
  flex: 1; min-height: 0; overflow: auto;
  border: 1px solid var(--border); border-radius: 10px;
  background: var(--bg-card);
}
.table-wrap::-webkit-scrollbar { width: 4px; height: 4px; }
.table-wrap::-webkit-scrollbar-track { background: transparent; }
.table-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.sp-table { width: 100%; border-collapse: collapse; }
.sp-table th {
  position: sticky; top: 0; z-index: 1;
  text-align: left; font-size: 12px; font-weight: 600;
  color: var(--text-secondary); background: #f5f0e8;
  padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
.sp-table td {
  padding: 7px 10px; border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.sp-row:hover td { background: #faf7f2; }
.sp-name { font-weight: 600; }
.ta-c { text-align: center; }
.ta-r { text-align: right; }
.cell-empty { color: var(--text-secondary); }
.mono { font-family: 'SF Mono', Consolas, monospace; font-size: 12px; }
.ellip { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.price-val { font-family: 'SF Mono', Consolas, monospace; font-weight: 600; }

.link-btn {
  border: none; background: transparent; color: var(--accent);
  font-size: 12px; font-family: inherit; cursor: pointer; padding: 0 4px;
}
.link-btn:hover { text-decoration: underline; }
.link-btn.danger { color: #d05a3c; }
.caret { font-size: 10px; }

.grp-tag {
  display: inline-block; margin: 1px 4px 1px 0; padding: 1px 7px;
  border-radius: 4px; font-size: 11px; white-space: nowrap;
  color: #4a8fc0; background: rgba(74,143,192,0.1);
  border: 1px solid rgba(74,143,192,0.3);
}
.grp-more { font-size: 11px; color: var(--text-secondary); }

/* ── 明细 ─────────────────────────────────────── */
.sp-detail-row > td { background: var(--bg); padding: 0 10px 8px; }
.sp-subtable { width: 100%; border-collapse: collapse; }
.sp-subtable th {
  position: static; background: transparent; font-size: 11px;
  padding: 6px 8px; color: var(--text-secondary);
}
.sp-subtable td {
  padding: 4px 8px; font-size: 12px;
  border-bottom: 1px dashed var(--border);
}
.sp-subtable tr:last-child td { border-bottom: none; }

.detail-tip, .sp-empty {
  padding: 14px; text-align: center;
  font-size: 12px; color: var(--text-secondary);
}

/* ── 表单 ─────────────────────────────────────── */
.sp-form { font-size: 13px; }
.sp-field { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.sp-field.top { align-items: flex-start; }
.sp-field label { width: 68px; flex-shrink: 0; color: var(--text-secondary); }
.sp-field label b { color: #d05a3c; }
.sp-field .sp-input { flex: 1; min-width: 0; }
.sp-hint { margin: 0; font-size: 11px; color: var(--text-secondary); }
</style>

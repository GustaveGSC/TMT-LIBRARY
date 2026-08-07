<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, watch } from 'vue'
import { WarningFilled, Picture, Upload, Delete } from '@element-plus/icons-vue'
import { pickFile } from '@/utils/download'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'

// 价格属于研发成本数据。usePermission 返回普通布尔值不是 ref，不能写 .value。
const { canViewRd, canEditRd } = usePermission()

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
// 停用状态**不可人工设置**（用户 2026-08-07 决定：只来源于导入数据），
// 所以表单里没有它，卡片只在 ERP 信息区做只读展示。
const form = ref({ short_name: '', category: '', spec: '', remark: '' })

// 新选的图片（base64）；空串表示未改动
const newImage = ref('')

// ── 价格（研发 BOM 成本数据）────────────────────────
// 价格与研发部 BOM 共用同一份 cost_material_price，不是物料库独有的副本。
// 物料若还没有成本节点（8091 个物料里只有 130 个有），首次加价时后端惰性创建。
const prices        = ref([])
const usages        = ref([])
const costLoading   = ref(false)
const costTab       = ref('prices')     // prices | usages
const priceFormOpen = ref(false)
const priceSaving   = ref(false)
const priceForm     = ref({ unit_price: '', price_date: '', supplier_name: '', notes: '' })
const priceErr      = ref('')

// 无用物料不允许维护价格（用户 2026-08-07 决定：金蝶旧编码那两组已不再使用）。
// 后端同样有门禁，这里只是不给入口。后端若返回 can_add_price 则优先用它。
const canAddPrice = computed(() => {
  const d = detail.value
  if (!d || !canEditRd) return false
  if (typeof d.can_add_price === 'boolean') return d.can_add_price
  return !(d.categories || []).includes('useless')
})
const isUseless = computed(() => (detail.value?.categories || []).includes('useless'))

async function loadCost() {
  if (!canViewRd || !props.code) return
  costLoading.value = true
  const c = encodeURIComponent(props.code)
  try {
    const [pRes, uRes] = await Promise.all([
      http.get(`/api/material/items/${c}/prices`),
      http.get(`/api/material/items/${c}/usages`),
    ])
    prices.value = (pRes.success ? (pRes.data || []) : [])
      .map(x => ({ ...x, _supplierDraft: x.supplier_name || '' }))
    usages.value = uRes.success ? (uRes.data || []) : []
  } catch { /* 价格拿不到不该阻塞整张卡片 */ }
  finally { costLoading.value = false }
}

async function submitPrice() {
  priceErr.value = ''
  if (!String(priceForm.value.unit_price).trim()) { priceErr.value = '请填写单价'; return }
  priceSaving.value = true
  try {
    const res = await http.post(
      `/api/material/items/${encodeURIComponent(props.code)}/prices`, {
        unit_price:    priceForm.value.unit_price,
        price_date:    priceForm.value.price_date || '',
        supplier_name: priceForm.value.supplier_name || '',
        notes:         priceForm.value.notes || '',
      })
    if (res.success) {
      // 重新拉取而不是本地 unshift：最新价由 price_date 排序决定，
      // 新加的一条不一定就是最新（可能补录的是更早日期）。
      await loadCost()
      priceFormOpen.value = false
      priceForm.value = { unit_price: '', price_date: '', supplier_name: '', notes: '' }
      // 通知列表刷新该行的价格列
      emit('saved', { ...detail.value, _priceChanged: true })
    } else {
      priceErr.value = res.message || '添加失败'
    }
  } catch (e) { priceErr.value = e.message || '网络错误' }
  finally { priceSaving.value = false }
}

async function saveSupplier(row) {
  const next = row._supplierDraft || ''
  const res = await http.patch(`/api/material/prices/${row.id}`, { supplier_name: next })
  if (res.success) row.supplier_name = next
  else priceErr.value = res.message || '供应商更新失败'
}

async function removePrice(row) {
  const { ElMessageBox } = await import('element-plus')
  try {
    await ElMessageBox.confirm('确认删除该价格记录？', '确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  const res = await http.delete(`/api/material/prices/${row.id}`)
  if (res.success) { await loadCost(); emit('saved', { ...detail.value, _priceChanged: true }) }
  else priceErr.value = res.message || '删除失败'
}

const SOURCE_LABELS = { bom_import: 'BOM 导入', manual: '手动', bom_calc: 'BOM 推算' }

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
        short_name: res.data.short_name || '',
        category:   res.data.category   || '',
        spec:       res.data.spec       || '',
        remark:     res.data.remark     || '',
      }
      newImage.value = ''
      loadCost()
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
    // 刻意不传 is_disabled：该列是「人工覆盖」，一旦传值就会覆盖导入数据的判定。
    // 停用状态只来源于导入，卡片无权修改。
    const payload = {
      short_name: form.value.short_name,
      category:   form.value.category,
      spec:       form.value.spec,
      remark:     form.value.remark,
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
watch(() => props.visible, v => {
  if (!v) return
  prices.value = []; usages.value = []
  priceFormOpen.value = false; priceErr.value = ''; costTab.value = 'prices'
  loadDetail()
})
</script>

<template>
  <el-dialog
    :model-value="props.visible"
    title="物料卡片"
    :width="canViewRd ? 720 : 560"
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
            <span v-if="detail.is_disabled" class="ro-badge off">已停用</span>
            <span v-else class="ro-badge on">启用</span>
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

        </div>

        <!-- ── 价格（研发 BOM 成本数据，仅 rd:view 可见）──────
             与研发部 BOM 共用同一份 cost_material_price，不是副本。
             后端在无 rd:view 时根本不返回价格字段，此处隐藏只是体验层。 -->
        <div v-if="canViewRd" class="mc-section">
          <div class="mc-section-title">
            <span>价格（研发 BOM）</span>
            <span v-if="detail.latest_price != null" class="mc-latest">
              最新　<b>¥{{ Number(detail.latest_price).toFixed(4) }}</b>
              <span class="mc-src">{{ SOURCE_LABELS[detail.latest_price_source] || '' }}</span>
            </span>
          </div>

          <div class="cost-tabs">
            <button class="cost-tab" :class="{ active: costTab === 'prices' }"
                    @click="costTab = 'prices'">价格记录（{{ prices.length }}）</button>
            <button class="cost-tab" :class="{ active: costTab === 'usages' }"
                    @click="costTab = 'usages'">使用记录（{{ usages.length }}）</button>
            <button v-if="canAddPrice" class="cost-add" @click="priceFormOpen = !priceFormOpen">
              {{ priceFormOpen ? '取消添加' : '+ 添加价格' }}
            </button>
            <span v-else-if="isUseless" class="cost-locked" title="金蝶旧编码物料已不再使用">
              无用物料不维护价格
            </span>
          </div>

          <div v-if="priceErr" class="error-bar mini">
            <el-icon><WarningFilled /></el-icon><span>{{ priceErr }}</span>
          </div>

          <!-- 添加价格 -->
          <div v-if="priceFormOpen && canAddPrice" class="price-form">
            <div class="pf-row">
              <label>单价 <b>*</b></label>
              <input v-model="priceForm.unit_price" class="mc-input" placeholder="如 12.3456" />
              <label>日期</label>
              <input v-model="priceForm.price_date" class="mc-input" type="date" />
            </div>
            <div class="pf-row">
              <label>供应商</label>
              <input v-model="priceForm.supplier_name" class="mc-input" placeholder="可留空" />
              <label>备注</label>
              <input v-model="priceForm.notes" class="mc-input" placeholder="可留空" />
            </div>
            <div class="pf-actions">
              <button class="btn btn-primary sm" :disabled="priceSaving" @click="submitPrice">
                {{ priceSaving ? '提交中...' : '确认添加' }}
              </button>
              <span v-if="!detail.has_cost_node" class="pf-hint">
                该物料尚无成本节点，首次加价会自动创建
              </span>
            </div>
          </div>

          <div v-if="costLoading" class="state-tip mini">加载中...</div>

          <!-- 价格记录 -->
          <table v-else-if="costTab === 'prices' && prices.length" class="cost-table">
            <thead>
              <tr>
                <th style="width:96px">日期</th>
                <th style="width:96px" class="ta-r">单价</th>
                <th>供应商</th>
                <th style="width:78px">来源</th>
                <th v-if="canEditRd" style="width:44px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in prices" :key="row.id">
                <td>{{ row.price_date || '—' }}</td>
                <td class="ta-r price-val">¥{{ Number(row.unit_price).toFixed(4) }}</td>
                <td>
                  <template v-if="canEditRd">
                    <div class="sup-cell">
                      <input v-model="row._supplierDraft" class="mc-input tiny"
                             placeholder="点击填写" @keyup.enter="saveSupplier(row)" />
                      <button v-if="row._supplierDraft !== (row.supplier_name || '')"
                              class="sup-ok" title="确认" @click="saveSupplier(row)">✓</button>
                    </div>
                  </template>
                  <span v-else>{{ row.supplier_name || '—' }}</span>
                </td>
                <td>
                  <span class="src-tag" :class="'src-' + row.source">
                    {{ SOURCE_LABELS[row.source] || row.source }}
                  </span>
                </td>
                <td v-if="canEditRd">
                  <button class="del-btn" title="删除" @click="removePrice(row)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 使用记录 -->
          <table v-else-if="costTab === 'usages' && usages.length" class="cost-table">
            <thead>
              <tr>
                <th style="width:96px">快照日期</th>
                <th>订单号</th>
                <th>成品品号</th>
                <th style="width:60px" class="ta-r">数量</th>
                <th style="width:96px" class="ta-r">单价</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in usages" :key="i">
                <td>{{ row.snapshot_date || '—' }}</td>
                <td class="ellip">{{ row.order_no || '—' }}</td>
                <td class="mono ellip">{{ row.finished_code }}</td>
                <td class="ta-r">{{ row.quantity ?? '—' }}</td>
                <td class="ta-r price-val">
                  {{ row.unit_price != null ? '¥' + Number(row.unit_price).toFixed(4) : '—' }}
                </td>
              </tr>
            </tbody>
          </table>

          <div v-else class="cost-empty">
            {{ costTab === 'prices' ? '暂无价格记录' : '暂无使用记录' }}
          </div>

          <!-- 成本备注：属于 cost_bom_node.notes，与上面「人工维护」的备注是
               两个不同字段，刻意分开显示避免互相覆盖 -->
          <div v-if="detail.has_cost_node && detail.cost_notes" class="cost-notes">
            <label>成本备注</label><span>{{ detail.cost_notes }}</span>
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

/* 只读的停用角标——停用状态来源于导入数据，卡片不提供修改入口 */
.ro-badge {
  font-size: 10px; font-weight: 600;
  border: 1px solid; border-radius: 4px; padding: 1px 7px; flex-shrink: 0;
}
.ro-badge.on  { color: #4a8f6a; background: rgba(74,143,106,0.12); border-color: rgba(74,143,106,0.4); }
.ro-badge.off { color: #d05a3c; background: rgba(208,90,60,0.1);  border-color: rgba(208,90,60,0.35); }


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

/* ── 价格区（研发 BOM）───────────────────────────── */
.mc-section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.mc-latest { font-size: 12px; color: var(--text-secondary); font-weight: 400; }
.mc-latest b { font-family: 'SF Mono', Consolas, monospace; color: #3d2b1a; font-size: 13px; }
.mc-src { margin-left: 6px; color: var(--text-secondary); }

.cost-tabs { display: flex; align-items: center; gap: 6px; margin: 10px 0 8px; }
.cost-tab {
  padding: 4px 12px; border-radius: 7px;
  border: 1px solid var(--border); background: var(--bg);
  color: var(--text-secondary); font-size: 12px; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.cost-tab:hover  { border-color: var(--accent); color: var(--accent); }
.cost-tab.active { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); font-weight: 600; }
.cost-add {
  margin-left: auto; padding: 4px 12px; border-radius: 7px;
  border: 1px solid var(--accent); background: var(--accent-bg);
  color: var(--accent); font-size: 12px; font-family: inherit; cursor: pointer;
}
.cost-add:hover { background: var(--accent); color: #fff; }
.cost-locked { margin-left: auto; font-size: 12px; color: var(--text-secondary); }

/* 添加价格表单 */
.price-form {
  padding: 10px 12px; margin-bottom: 8px;
  background: var(--bg); border: 1px solid var(--border); border-radius: 9px;
}
.pf-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.pf-row label { font-size: 12px; color: var(--text-secondary); flex-shrink: 0; width: 46px; }
.pf-row label b { color: #d05a3c; }
.pf-row .mc-input { flex: 1; min-width: 0; }
.pf-actions { display: flex; align-items: center; gap: 10px; }
.pf-hint { font-size: 11px; color: var(--text-secondary); }
.btn.sm { padding: 5px 14px; font-size: 12px; }

/* 价格 / 使用记录表 */
.cost-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cost-table th {
  text-align: left; font-weight: 600; color: var(--text-secondary);
  padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
.cost-table td {
  padding: 5px 8px; border-bottom: 1px solid var(--border);
  color: var(--text-primary); vertical-align: middle;
}
.cost-table tr:last-child td { border-bottom: none; }
.ta-r { text-align: right; }
.ellip { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.price-val { font-family: 'SF Mono', Consolas, monospace; font-weight: 600; }

.src-tag {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  font-size: 11px; border: 1px solid;
}
.src-bom_import { color: #4a8fc0; background: rgba(74,143,192,0.1);  border-color: rgba(74,143,192,0.35); }
.src-manual     { color: #6ab47a; background: rgba(106,180,122,0.1); border-color: rgba(106,180,122,0.35); }
.src-bom_calc   { color: #9c6fba; background: rgba(156,111,186,0.1); border-color: rgba(156,111,186,0.35); }

.sup-cell { display: flex; align-items: center; gap: 4px; }
.mc-input.tiny { padding: 3px 7px; font-size: 12px; }
.sup-ok {
  border: none; background: transparent; color: #6ab47a;
  font-size: 15px; cursor: pointer; padding: 0 2px; line-height: 1;
}
.del-btn {
  border: none; background: transparent; color: #d05a3c;
  font-size: 12px; font-family: inherit; cursor: pointer; padding: 0;
}
.del-btn:hover { text-decoration: underline; }

.cost-empty { padding: 16px 0; text-align: center; font-size: 12px; color: var(--text-secondary); }
.state-tip.mini { padding: 16px 0; font-size: 12px; }
.error-bar.mini { margin: 0 0 8px; padding: 6px 10px; font-size: 12px; }

.cost-notes {
  margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border);
  display: flex; gap: 10px; font-size: 12px;
}
.cost-notes label { color: var(--text-secondary); flex-shrink: 0; }
</style>

<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import http from '@/api/http.js'
import { usePermission } from '@/composables/usePermission.js'

// ── 权限 ──────────────────────────────────────────
const { canEditAftersale } = usePermission()

// ── 响应式状态 ────────────────────────────────────
const items      = ref([])
const total      = ref(0)
const page       = ref(1)
const pageSize   = ref(50)
const loading    = ref(false)

// 筛选
const searchText = ref('')
const statusFilter = ref('')        // '' | 'confirmed' | 'ignored'
const dateRange  = ref([])

// 展开行
const expandedRows = ref([])

// 编辑弹窗
const editDialog   = ref(false)
const editCase     = ref(null)
const editReasons  = ref([])
const reasonOpts   = ref([])
const saving       = ref(false)

// 状态显示
const STATUS_MAP = {
  confirmed: { label: '已确认', type: 'success' },
  ignored:   { label: '已忽略', type: 'info' },
  pending:   { label: '待处理', type: 'warning' },
}

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  loadData()
})

// ── 方法 ──────────────────────────────────────────

async function loadData() {
  loading.value = true
  try {
    const res = await http.get('/api/aftersale/cases', {
      params: {
        page:       page.value,
        page_size:  pageSize.value,
        status:     statusFilter.value || undefined,
        date_start: dateRange.value?.[0] || undefined,
        date_end:   dateRange.value?.[1] || undefined,
        search:     searchText.value || undefined,
      },
    })
    if (res.success) {
      items.value = res.data.items
      total.value = res.data.total
    }
  } finally {
    loading.value = false
  }
}

function onPageChange(p) {
  page.value = p
  loadData()
}

function onSizeChange(s) {
  pageSize.value = s
  page.value = 1
  loadData()
}

let searchTimer = null
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadData()
  }, 300)
}

function onFilterChange() {
  page.value = 1
  loadData()
}

// 展开行：切换
function toggleExpand(row) {
  const id = row.id
  const idx = expandedRows.value.indexOf(id)
  if (idx === -1) expandedRows.value.push(id)
  else expandedRows.value.splice(idx, 1)
}

// 打开编辑弹窗
async function openEdit(row) {
  editCase.value    = { ...row }
  editReasons.value = (row.reasons || []).map(r => ({
    reason_id:         r.reason_id,
    custom_reason:     r.custom_reason || '',
    involved_products: r.involved_products || [],
    notes:             r.notes || '',
  }))
  // 加载原因选项
  if (reasonOpts.value.length === 0) {
    const res = await http.get('/api/aftersale/reasons')
    if (res.success) reasonOpts.value = res.data.flatMap(g => g.reasons)
  }
  editDialog.value = true
}

function addEditReason() {
  editReasons.value.push({ reason_id: null, custom_reason: '', involved_products: [], notes: '' })
}
function removeEditReason(idx) {
  editReasons.value.splice(idx, 1)
}

async function saveEdit() {
  saving.value = true
  try {
    const res = await http.put(`/api/aftersale/cases/${editCase.value.id}`, {
      reasons: editReasons.value,
    })
    if (res.success) {
      ElMessage.success('已保存')
      editDialog.value = false
      loadData()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

// 将原因列表格式化为 tag 字符串（用于展示）
function formatReasons(reasons) {
  return (reasons || []).map(r => r.reason_name || r.custom_reason || '未知').join('、')
}
</script>

<template>
  <div class="table-wrap">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-input
        v-model="searchText"
        placeholder="搜索订单号"
        :prefix-icon="Search"
        size="small"
        clearable
        style="width:200px"
        @input="onSearch"
        @clear="onSearch"
      />

      <el-select
        v-model="statusFilter"
        size="small"
        placeholder="全部状态"
        clearable
        style="width:120px"
        @change="onFilterChange"
      >
        <el-option label="已确认" value="confirmed" />
        <el-option label="已忽略" value="ignored" />
      </el-select>

      <el-date-picker
        v-model="dateRange"
        type="daterange"
        size="small"
        range-separator="~"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        style="width:220px"
        @change="onFilterChange"
      />

      <span class="total-hint">共 {{ total }} 条</span>
    </div>

    <!-- 表格 -->
    <div class="table-container">
      <el-table
        v-loading="loading"
        :data="items"
        row-key="id"
        border
        size="small"
        style="width:100%"
        :expand-row-keys="expandedRows.map(String)"
        @row-click="toggleExpand"
      >
        <!-- 展开列 -->
        <el-table-column type="expand" width="30">
          <template #default="{ row }">
            <div class="expand-content">
              <!-- 备注 -->
              <div class="expand-row">
                <span class="expand-label">商家备注</span>
                <span class="expand-val">{{ row.seller_remark || '—' }}</span>
              </div>
              <div class="expand-row">
                <span class="expand-label">买家留言</span>
                <span class="expand-val">{{ row.buyer_remark || '—' }}</span>
              </div>
              <!-- 原因详情 -->
              <div class="expand-row expand-reasons">
                <span class="expand-label">原因详情</span>
                <div class="reason-detail-list">
                  <div
                    v-for="(r, i) in row.reasons"
                    :key="i"
                    class="reason-detail-item"
                  >
                    <el-tag size="small" type="warning">
                      {{ r.reason_name || r.custom_reason || '未知' }}
                    </el-tag>
                    <span v-if="r.involved_products?.length" class="inv-products">
                      涉及：{{ r.involved_products.join('、') }}
                    </span>
                    <span v-if="r.notes" class="inv-notes">备注：{{ r.notes }}</span>
                  </div>
                </div>
              </div>
              <!-- 物料 -->
              <div class="expand-row">
                <span class="expand-label">发货物料</span>
                <div class="products-inline">
                  <span v-for="p in row.products" :key="p.code" class="prod-tag">
                    {{ p.code }} {{ p.name }} ×{{ p.quantity }}
                  </span>
                </div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="ecommerce_order_no" label="订单号" min-width="160" show-overflow-tooltip />
        <el-table-column prop="shipped_date" label="日期" width="100" />
        <el-table-column prop="channel_name" label="渠道" width="120" show-overflow-tooltip />
        <el-table-column prop="province" label="省份" width="80" />
        <el-table-column label="产品数" width="70" align="center">
          <template #default="{ row }">{{ row.products?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="售后原因" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="reason-tags">
              <el-tag
                v-for="r in (row.reasons || [])"
                :key="r.id"
                size="small"
                type="warning"
                style="margin:1px 3px 1px 0"
              >
                {{ r.reason_name || r.custom_reason || '未知' }}
              </el-tag>
              <span v-if="!row.reasons?.length" style="color:var(--text-muted);font-size:12px">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" width="100" show-overflow-tooltip />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag
              :type="STATUS_MAP[row.status]?.type || 'info'"
              size="small"
            >{{ STATUS_MAP[row.status]?.label || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canEditAftersale" label="操作" width="70" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              @click.stop="openEdit(row)"
            >编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        small
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog
      v-model="editDialog"
      title="编辑售后原因"
      width="600px"
      :close-on-click-modal="false"
    >
      <div v-if="editCase">
        <div class="edit-order-no">{{ editCase.ecommerce_order_no }}</div>

        <div
          v-for="(row, idx) in editReasons"
          :key="idx"
          class="edit-reason-row"
        >
          <el-select
            v-model="row.reason_id"
            placeholder="选择原因"
            clearable filterable
            style="width:160px"
          >
            <el-option
              v-for="opt in reasonOpts"
              :key="opt.id"
              :value="opt.id"
              :label="opt.name"
            />
          </el-select>
          <el-input
            v-model="row.custom_reason"
            placeholder="自定义原因"
            style="flex:1"
          />
          <el-button
            type="danger"
            link
            size="small"
            @click="removeEditReason(idx)"
          >删</el-button>
        </div>

        <el-button size="small" @click="addEditReason" style="margin-top:8px">
          + 添加原因
        </el-button>
      </div>

      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.table-wrap {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; padding: 12px 16px;
}

.toolbar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px; flex-wrap: wrap;
}
.total-hint {
  font-size: 12px; color: var(--text-muted); margin-left: auto;
}

.table-container {
  flex: 1; overflow: auto;
}
.table-container::-webkit-scrollbar { width: 4px; height: 4px; }
.table-container::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.pagination {
  padding-top: 10px; display: flex; justify-content: flex-end;
}

/* 展开行 */
.expand-content {
  padding: 10px 20px 10px 40px;
  background: #faf7f2;
  border-top: 1px solid var(--border);
}
.expand-row {
  display: flex; gap: 12px; margin-bottom: 8px;
  font-size: 12px; line-height: 1.6;
}
.expand-label {
  width: 70px; flex-shrink: 0;
  font-weight: 600; color: var(--text-muted);
}
.expand-val { color: var(--text-primary); }

.expand-reasons .reason-detail-list {
  display: flex; flex-direction: column; gap: 4px;
}
.reason-detail-item {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.inv-products, .inv-notes {
  font-size: 11px; color: var(--text-muted);
}

.products-inline {
  display: flex; flex-wrap: wrap; gap: 4px;
}
.prod-tag {
  padding: 2px 8px; background: #f5f0e8;
  border: 1px solid var(--border); border-radius: 4px;
  font-size: 11px; color: var(--text-primary);
}

.reason-tags { display: flex; flex-wrap: wrap; }

/* 编辑弹窗 */
.edit-order-no {
  font-size: 13px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 14px;
}
.edit-reason-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px;
}
</style>

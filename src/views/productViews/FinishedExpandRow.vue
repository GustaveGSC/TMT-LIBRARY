<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, reactive, computed, watch } from 'vue'
import http from '@/api/http'
import { usePermission } from '@/composables/usePermission'
import { ZoomIn, EditPen, Plus, Delete } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useFinishedStore } from '@/stores/product/finished'
import { usePackagedStore } from '@/stores/product/packaged'
import GEditTagList from '@/components/common/GEditTagList.vue'

// ── Props ─────────────────────────────────────────
const props = defineProps({
  row: { type: Object, required: true },
})

// ── Emits ─────────────────────────────────────────
const emit = defineEmits(['saved'])

// ── 权限 ──────────────────────────────────────────
const { canEditProduct } = usePermission()

// ── 响应式状态 ────────────────────────────────────
const editing = ref(false)
const saving  = ref(false)

// ── 图片相关状态 ──────────────────────────────────
const imgHover    = ref(false)       // 编辑状态下鼠标悬停
const imgPreview  = ref(false)       // 预览弹窗开关
const addMenuVisible = ref(false)    // 新增子菜单

// 图片操作
function previewImage() {
  if (!props.row.cover_image) return
  imgPreview.value = true
}
function editImage() {
  // 裁切图片（后续接入裁切库）
}
async function addImageFromUpload() {
  addMenuVisible.value = false
  const result = await window.electronAPI.showOpenDialog({
    filters: [{ name: '图片', extensions: ['jpg', 'jpeg', 'png', 'webp'] }],
    properties: ['openFile'],
  })
  if (result.canceled || !result.filePaths.length) return
  // TODO: 上传到 OSS 并保存
}
function addImageFromExisting() {
  addMenuVisible.value = false
  // TODO: 从已有图片库选择
}
async function deleteImage() {
  try {
    await ElMessageBox.confirm('确认删除当前封面图片？', '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    // TODO: 删除 OSS 图片并清空 cover_image
  } catch {}
}
const editForm = reactive({
  name: '', name_en: '', status: '',
  listed_yymm: '', delisted_yymm: '',
  market: '',
  market_domestic: false,
  market_foreign:  false,
  category_name:  '',
  series_code:    '',
  series_name:    '',
  model_code:     '',
  packaged_tags: [],    // 产成品清单（{value: code, state: 'new'|'raw'|'delete'} 数组）
  // state 语义：new=编码不在产成品库里，raw=在库里，delete=标记删除
  tag_names:      [],   // 标签名称数组
})

// 编辑开始时的原始产成品 codes（用于 saveEdit 做对比，不依赖 state）
const originalPackagedCodes = ref(new Set())

// ── 折叠分组 ──────────────────────────────────────
const openSec = reactive({})
function toggleSec(key) { openSec[key] = !openSec[key] }
function isSec(key)     { return !!openSec[key] }

// ── 生命周期 badge（始终显示）────────────────────
function lc(row) {
  if (row.listed_yymm && row.delisted_yymm) return { label: '已退市', cls: 'lc-out' }
  if (row.listed_yymm)                       return { label: '上市中',  cls: 'lc-on'  }
  return { label: '未知状态', cls: 'lc-unknown' }
}

// ── 编辑 ──────────────────────────────────────────

// 判断编码是否存在于产成品库
function isInPackagedLibrary(code) {
  return packagedOptions.value.some(o => o.code === code)
}

async function startEdit() {
  const d = props.row
  const domestic = d.market === 'domestic' || d.market === 'both'
  const foreign  = d.market === 'foreign'  || d.market === 'both'
  // 先加载候选库，再判断每个 code 的初始状态
  await Promise.all([ensurePackagedOptionsLoaded(), ensureTagOptionsLoaded()])
  const initialCodes = (d.packaged_list || []).map(p => p?.code ?? p)
  originalPackagedCodes.value = new Set(initialCodes)
  Object.assign(editForm, {
    name:            d.name          || '',
    name_en:         d.name_en       || '',
    status:          d.status        || 'unrecorded',
    listed_yymm:     d.listed_yymm   || '',
    delisted_yymm:   d.delisted_yymm || '',
    market:          d.market        || '',
    market_domestic: domestic,
    market_foreign:  foreign,
    category_name:   d.category_name || '',
    series_code:     d.series_code   || '',
    series_name:     d.series_name   || '',
    model_code:      d.model_code    || '',
    packaged_tags: initialCodes.map(code => ({
      value: code,
      state: isInPackagedLibrary(code) ? 'raw' : 'new',
    })),
    tag_names: (d.tags || []).map(t => t.name),
  })
  editing.value = true
}
function cancelEdit() { editing.value = false }

// market checkbox → market 字段
function resolveMarket() {
  const d = editForm.market_domestic
  const f = editForm.market_foreign
  if (d && f)  return 'both'
  if (d)       return 'domestic'
  if (f)       return 'foreign'
  return ''
}

async function saveEdit() {
  saving.value = true
  try {
    const res = await http.post('/api/product/finished', {
      code:          props.row.code,
      name:          editForm.name,
      name_en:       editForm.name_en,
      status:        editForm.status,
      listed_yymm:   editForm.listed_yymm  || null,
      delisted_yymm: editForm.delisted_yymm || null,
      market:        resolveMarket(),
      category_name: editForm.category_name || null,
      series_code:   editForm.series_code   || null,
      series_name:   editForm.series_name   || null,
      model_code:    editForm.model_code    || null,
    })
    if (res.success) {
      // 通过与原始 codes 对比决定增删，不依赖 state（state 仅用于 UI）
      const finishedId  = props.row.id
      const activeCodes = new Set(editForm.packaged_tags.filter(t => t.state !== 'delete').map(t => t.value))
      const toRemove = [...originalPackagedCodes.value].filter(c => !activeCodes.has(c))
      const toAdd    = [...activeCodes].filter(c => !originalPackagedCodes.value.has(c))
      for (const code of toRemove) {
        const pid = packagedStore.map[code]?.id
        if (pid) await http.delete(`/api/product/finished/${finishedId}/packaged/${pid}`)
      }
      for (const code of toAdd) {
        const pid = packagedStore.map[code]?.id
        if (pid) await http.post(`/api/product/finished/${finishedId}/packaged/${pid}`)
      }
      editing.value = false
      emit('saved')
    }
  } finally {
    saving.value = false
  }
}

// ── Autocomplete 候选 ─────────────────────────────
const finishedStore  = useFinishedStore()
const packagedStore  = usePackagedStore()

// 中文名称 / 英文名称：从 rawItems 本地匹配
function suggestName(query, cb) {
  const list = query
    ? finishedStore.getSuggestions('name', query)
    : finishedStore.getTopSuggestions('name')
  cb(list.map(v => ({ value: v })))
}
function suggestNameEn(query, cb) {
  const list = query
    ? finishedStore.getSuggestions('name_en', query)
    : finishedStore.getTopSuggestions('name_en')
  cb(list.map(v => ({ value: v })))
}

// ── 产成品候选选项（懒加载）──────────────────────
const packagedOptions = ref([])   // [{code, name}]
const packagedLoaded  = ref(false)
async function ensurePackagedOptionsLoaded() {
  if (packagedLoaded.value) return
  try {
    const res = await http.get('/api/product/packaged/candidates/all')
    if (res.success) { packagedOptions.value = res.data || []; packagedLoaded.value = true }
  } catch {}
}

// ── 标签选项（懒加载）────────────────────────────
const tagOptions = ref([])   // [{id, name, color}]
const tagsLoaded = ref(false)
async function ensureTagOptionsLoaded() {
  if (tagsLoaded.value) return
  try {
    const res = await http.get('/api/product/tags/')
    if (res.success) { tagOptions.value = res.data || []; tagsLoaded.value = true }
  } catch {}
}

// ── 分类树（编辑时懒加载）────────────────────────
const categoryTree = ref([])
const treeLoaded   = ref(false)
async function ensureTreeLoaded() {
  if (treeLoaded.value) return
  try {
    const res = await http.get('/api/category/tree')
    if (res.success) { categoryTree.value = res.data || []; treeLoaded.value = true }
  } catch {}
}

// 当前选中的品类/系列对象（用于过滤下级候选）
const selectedCategoryObj = computed(() =>
  categoryTree.value.find(c => c.name === editForm.category_name) ?? null
)
const selectedSeriesObj = computed(() =>
  (selectedCategoryObj.value?.series || []).find(s => s.code === editForm.series_code) ?? null
)

// 字段是否禁用
const seriesDisabled     = computed(() => !editForm.category_name)
const seriesNameReadonly = computed(() => !!selectedSeriesObj.value)
const modelDisabled      = computed(() => !editForm.series_code)

// 品类变化 → 清空下级
watch(() => editForm.category_name, () => {
  editForm.series_code = ''
  editForm.series_name = ''
  editForm.model_code  = ''
})

// 系列编码变化 → 自动填充系列名称 / 清空型号
watch(() => editForm.series_code, (code) => {
  editForm.model_code = ''
  if (!code) {
    editForm.series_name = ''
  } else {
    const match = (selectedCategoryObj.value?.series || []).find(s => s.code === code)
    if (match) editForm.series_name = match.name
  }
})

// 品类候选
async function suggestCategory(query, cb) {
  await ensureTreeLoaded()
  const list = categoryTree.value.filter(c => !query || c.name.includes(query))
  cb(list.map(c => ({ value: c.name })))
}

// 系列编码候选（限当前品类下，若品类不在树中则显示全部）
async function suggestSeriesCode(query, cb) {
  await ensureTreeLoaded()
  const series = selectedCategoryObj.value
    ? (selectedCategoryObj.value.series || [])
    : categoryTree.value.flatMap(c => c.series || [])
  cb(series.filter(s => !query || s.code.includes(query)).map(s => ({ value: s.code })))
}

// 系列名称候选（同上）
async function suggestSeriesName(query, cb) {
  await ensureTreeLoaded()
  const series = selectedCategoryObj.value
    ? (selectedCategoryObj.value.series || [])
    : categoryTree.value.flatMap(c => c.series || [])
  cb(series.filter(s => !query || s.name.includes(query)).map(s => ({ value: s.name })))
}

// 型号编码候选（限当前系列下，若系列不在树中则显示全部）
async function suggestModelCode(query, cb) {
  await ensureTreeLoaded()
  const models = selectedSeriesObj.value
    ? (selectedSeriesObj.value.models || [])
    : categoryTree.value.flatMap(c => (c.series || []).flatMap(s => s.models || []))
  cb(models.filter(m => !query || m.code.includes(query)).map(m => ({ value: m.code })))
}
</script>

<template>
  <div class="ec">

    <!-- ── 大卡片：顶栏 + 图片信息 + 折叠分组 ── -->
    <div class="ec-main">

      <!-- 顶栏：编码 + 生命周期badge + 操作按钮 -->
      <div class="ec-top">
        <span class="ec-code">{{ row.code }}</span>
        <span class="lc-badge" :class="lc(row).cls">{{ lc(row).label }}</span>
        <div class="ec-acts">
          <template v-if="canEditProduct && !editing">
            <button class="eb eb-edit" @click.stop="startEdit">✎ 编辑</button>
          </template>
          <template v-else-if="canEditProduct && editing">
            <button class="eb eb-save" :disabled="saving" @click.stop="saveEdit">
              {{ saving ? '保存中…' : '✓ 提交' }}
            </button>
            <button class="eb eb-cancel" @click.stop="cancelEdit">× 取消</button>
          </template>
          <button class="eb eb-more">···</button>
        </div>
      </div>

      <!-- 图片 + 信息并排 -->
      <div class="ec-row">

        <!-- 图片区 -->
        <div class="ec-img"
          @mouseenter="imgHover = true"
          @mouseleave="imgHover = false; addMenuVisible = false"
        >
          <!-- 有图片 -->
          <template v-if="row.cover_image">
            <img :src="row.cover_image" class="ec-img-photo" alt="封面图" />
          </template>
          <!-- 无图片 -->
          <template v-else>
            <span class="ec-img-ico">🖼</span>
            <span class="ec-img-hint">暂无图片</span>
          </template>

          <!-- 非编辑：点击预览 -->
          <div v-if="!editing && row.cover_image && imgHover"
            class="ec-img-overlay"
            @click="previewImage"
          >
            <el-icon class="ov-icon"><ZoomIn /></el-icon>
          </div>

          <!-- 编辑状态遮罩：4个按钮 -->
          <div v-if="editing && imgHover" class="ec-img-overlay ec-img-overlay-edit">
            <!-- 查看 -->
            <button class="ov-btn" :disabled="!row.cover_image" @click.stop="previewImage">
              <el-icon><ZoomIn /></el-icon>
            </button>
            <!-- 编辑（裁切） -->
            <button class="ov-btn" :disabled="!row.cover_image" @click.stop="editImage">
              <el-icon><EditPen /></el-icon>
            </button>
            <!-- 新增（有子菜单） -->
            <div class="ov-btn-wrap">
              <button class="ov-btn" @click.stop="addMenuVisible = !addMenuVisible">
                <el-icon><Plus /></el-icon>
              </button>
              <div v-if="addMenuVisible" class="ov-submenu">
                <div class="ov-submenu-item" @click.stop="addImageFromUpload">使用新图片</div>
                <div class="ov-submenu-item" @click.stop="addImageFromExisting">使用已有图片</div>
              </div>
            </div>
            <!-- 删除 -->
            <button class="ov-btn ov-btn-danger" :disabled="!row.cover_image" @click.stop="deleteImage">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
        </div>

        <!-- 图片预览弹窗（el-image-viewer） -->
        <el-image-viewer
          v-if="imgPreview && row.cover_image"
          :url-list="[row.cover_image]"
          @close="imgPreview = false"
        />

        <!-- 信息区：flex列，gap=5px，每行36px -->
        <div class="ec-card">

        <!-- ── 查看模式 ── -->
        <template v-if="!editing">

          <!-- 行1：中文名称 + 内销tag -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">中文名称</span>
              <span class="eg-val">
                <span class="eg-txt">{{ row.name || '—' }}</span>
                <span v-if="row.market === 'domestic' || row.market === 'both'" class="eg-inner-tag eg-tag-domestic">内销</span>
              </span>
            </div>
          </div>

          <!-- 行2：英文名称 + 外贸tag -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">英文名称</span>
              <span class="eg-val">
                <span class="eg-txt">{{ row.name_en || '—' }}</span>
                <span v-if="row.market === 'foreign' || row.market === 'both'" class="eg-inner-tag eg-tag-foreign">外贸</span>
              </span>
            </div>
          </div>

          <!-- 行3：品类 / 系列编码 / 上市年月 -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">品类编码</span><span class="eg-val">{{ row.category_name || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">系列编码</span><span class="eg-val eg-mono">{{ row.series_code || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl eg-lbl-em">上市日期</span><span class="eg-val">{{ row.listed_yymm || '—' }}</span></div>
          </div>

          <!-- 行4：型号编码 / 系列名称 / 退市年月 -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">型号编码</span><span class="eg-val eg-mono">{{ row.model_code || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">系列名称</span><span class="eg-val">{{ row.series_name || '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl eg-lbl-em">退市日期</span><span class="eg-val">{{ row.delisted_yymm || '—' }}</span></div>
          </div>

          <!-- 行5：体积 / 毛重 / 净重 -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">体积 (m³)</span><span class="eg-val">{{ row.total_volume ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">毛重 (kg)</span><span class="eg-val">{{ row.total_gross_weight ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">净重 (kg)</span><span class="eg-val">{{ row.total_net_weight ?? '—' }}</span></div>
          </div>

          <!-- 行6：产成品清单 -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">产成品清单</span>
              <span class="eg-val">
                <span v-for="c in (row.packaged_list || [])" :key="c" class="pk-tag">{{ c }}</span>
                <span v-if="!row.packaged_list?.length" class="eg-dim">—</span>
              </span>
            </div>
          </div>

          <!-- 行7：标签 -->
          <div class="eg-row">
            <div class="eg-cell eg-full">
              <span class="eg-lbl">标签</span>
              <span class="eg-val eg-dim">暂未定义</span>
            </div>
          </div>

        </template>

        <!-- ── 编辑模式 ── -->
        <template v-else-if="canEditProduct">

          <!-- 行1：中文名称 + 内销checkbox -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-full">
              <span class="eg-lbl eg-lbl-edit">中文名称</span>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.name" :fetch-suggestions="suggestName"
                  placeholder="中文名称" class="ei-auto" clearable />
                <el-checkbox v-model="editForm.market_domestic" class="ei-check">内销</el-checkbox>
              </span>
            </div>
          </div>

          <!-- 行2：英文名称 + 外贸checkbox -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-full">
              <span class="eg-lbl eg-lbl-edit">英文名称</span>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.name_en" :fetch-suggestions="suggestNameEn"
                  placeholder="英文名称（选填）" class="ei-auto" clearable />
                <el-checkbox v-model="editForm.market_foreign" class="ei-check">外贸</el-checkbox>
              </span>
            </div>
          </div>

          <!-- 行3：品类 / 系列编码 / 上市年月 -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">品类编码</span>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.category_name" :fetch-suggestions="suggestCategory"
                  placeholder="品类" class="ei-auto" clearable />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">系列编码</span>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.series_code" :fetch-suggestions="suggestSeriesCode"
                  placeholder="系列编码" class="ei-auto" clearable :disabled="seriesDisabled" />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">上市日期</span>
              <span class="eg-val eg-val-inp">
                <el-date-picker v-model="editForm.listed_yymm" type="month"
                  format="YYYY-MM" value-format="YYYY-MM" placeholder="上市年月" class="ei-date" />
              </span>
            </div>
          </div>

          <!-- 行4：型号编码 / 系列名称 / 退市年月 -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">型号编码</span>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.model_code" :fetch-suggestions="suggestModelCode"
                  placeholder="型号编码" class="ei-auto" clearable :disabled="modelDisabled" />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">系列名称</span>
              <span class="eg-val eg-val-inp">
                <el-autocomplete v-model="editForm.series_name" :fetch-suggestions="suggestSeriesName"
                  placeholder="系列名称" class="ei-auto" clearable
                  :disabled="seriesDisabled || seriesNameReadonly" />
              </span>
            </div>
            <div class="eg-cell eg-cell-edit">
              <span class="eg-lbl eg-lbl-edit">退市日期</span>
              <span class="eg-val eg-val-inp">
                <el-date-picker v-model="editForm.delisted_yymm" type="month"
                  format="YYYY-MM" value-format="YYYY-MM" placeholder="退市年月" class="ei-date" />
              </span>
            </div>
          </div>

          <!-- 行5：体积 / 毛重 / 净重（只读，不加 eg-row-edit） -->
          <div class="eg-row">
            <div class="eg-cell"><span class="eg-lbl">体积 (m³)</span><span class="eg-val">{{ row.total_volume ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">毛重 (kg)</span><span class="eg-val">{{ row.total_gross_weight ?? '—' }}</span></div>
            <div class="eg-cell"><span class="eg-lbl">净重 (kg)</span><span class="eg-val">{{ row.total_net_weight ?? '—' }}</span></div>
          </div>

          <!-- 行6：产成品清单 → GEditTagList -->
          <div class="eg-row eg-row-edit eg-row-grow">
            <div class="eg-cell eg-full" style="align-items: flex-start;">
              <span class="eg-lbl eg-lbl-edit" style="align-self: stretch;">产成品清单</span>
              <span class="eg-val eg-val-inp" style="align-items: flex-start; padding: 4px 6px;">
                <GEditTagList v-model="editForm.packaged_tags" :options="packagedOptions" />
              </span>
            </div>
          </div>

          <!-- 行7：标签 → el-select -->
          <div class="eg-row eg-row-edit">
            <div class="eg-cell eg-full">
              <span class="eg-lbl eg-lbl-edit">标签</span>
              <span class="eg-val eg-val-inp">
                <el-select v-model="editForm.tag_names"
                  multiple collapse-tags collapse-tags-tooltip
                  allow-create filterable placeholder="选择标签" class="ei-sel">
                  <el-option
                    v-for="tag in tagOptions"
                    :key="tag.id"
                    :value="tag.name"
                    :label="tag.name" />
                </el-select>
              </span>
            </div>
          </div>

        </template>

      </div><!-- /ec-card -->
      </div><!-- /ec-row -->

      <!-- 折叠分组（参数 / 数据）── -->
      <div class="ec-sections">
        <div class="eg-sec">
          <div class="eg-sec-hd" @click="toggleSec('params')">
            <span class="eg-arr">{{ isSec('params') ? '▾' : '›' }}</span>参数
          </div>
          <div v-if="isSec('params')" class="eg-sec-bd">
            <span class="eg-dim">暂未定义</span>
          </div>
        </div>
        <div class="eg-sec">
          <div class="eg-sec-hd" @click="toggleSec('data')">
            <span class="eg-arr">{{ isSec('data') ? '▾' : '›' }}</span>数据
          </div>
          <div v-if="isSec('data')" class="eg-sec-bd">
            <span class="eg-dim">暂未定义</span>
          </div>
        </div>
      </div>

    </div><!-- /ec-main -->

  </div>
</template>

<style scoped>
/* ── 展开区外壳 ───────────────────────────────── */
.ec {
  padding: 12px 14px;
  background: #f5f0e8;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── 顶栏（在 ec-main 内，底部分隔线） ─────────── */
.ec-top {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #e8ddd0;
}
.ec-code {
  font-size: 15px; font-weight: 700; color: #2c2420;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
}
.lc-badge {
  display: inline-block; font-size: 11px; font-weight: 600;
  padding: 2px 7px; border-radius: 3px; border: 1px solid;
}
.lc-on      { color: #389e0d; background: #f6ffed; border-color: #b7eb8f; }
.lc-out     { color: #cf1322; background: #fff1f0; border-color: #ffa39e; }
.lc-unknown { color: #8a7a6a; background: #f5f0e8; border-color: #d4c8b8; }
.ec-acts { margin-left: auto; display: flex; gap: 8px; }
.eb {
  padding: 4px 12px; border-radius: 5px; font-size: 12px;
  cursor: pointer; border: 1px solid; transition: all 0.15s; font-family: inherit;
  background: #fff;
}
.eb-edit   { border-color: #c0d4f0; color: #3a7bc8; }
.eb-edit:hover { background: #edf4ff; }
.eb-more   { border-color: #ddd5c4; color: #8a7a6a; letter-spacing: 2px; padding: 4px 8px; }
.eb-save   { background: #c4883a; border-color: #c4883a; color: #fff; }
.eb-save:hover:not(:disabled) { background: #b07830; }
.eb-save:disabled { opacity: 0.6; cursor: not-allowed; }
.eb-cancel { border-color: #ffa39e; color: #cf1322; }
.eb-cancel:hover { background: #fff1f0; }

/* ── 大卡片容器 ───────────────────────────────── */
.ec-main {
  width: 1200px;
  margin-left: 25px;
  background: #fff;
  border: 1px solid #e8ddd0;
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.ec-row {
  display: flex;
  align-items: flex-start;
  padding: 12px;
  gap: 10px;
}

/* 图片：宽度固定，高度自动跟随信息区（align-self:stretch） */
.ec-img {
  width: 282px;
  flex-shrink: 0;
  align-self: stretch;
  background: #f8f5f0;
  border: 1px solid #e8ddd0;
  border-radius: 8px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 6px;
  position: relative;   /* 遮罩定位基准 */
  overflow: hidden;
  cursor: default;
}
.ec-img-ico  { font-size: 26px; opacity: 0.2; }
.ec-img-hint { font-size: 11px; color: #c8bfb0; }

/* 图片本体 */
.ec-img-photo {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
  border-radius: 8px;
}

/* ── 遮罩（查看 / 编辑两种） ────────────────────── */
.ec-img-overlay {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.38);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
/* 查看遮罩：居中大图标 */
.ec-img-overlay:not(.ec-img-overlay-edit) {
  flex-direction: column;
}
.ec-img-overlay:not(.ec-img-overlay-edit):hover {
  background: rgba(0,0,0,0.52);
}
.ov-icon  { font-size: 28px; color: #fff; }

/* 编辑遮罩：圆形按钮横排 */
.ec-img-overlay-edit {
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 10px;
  padding: 16px;
  cursor: default;
  align-content: center;
  justify-content: center;
}

/* 遮罩按钮：圆形，无文字 */
.ov-btn {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px;
  background: rgba(255,255,255,0.18);
  border: 1px solid rgba(255,255,255,0.45);
  border-radius: 50%;
  color: #fff;
  cursor: pointer; transition: background 0.15s, transform 0.12s;
  flex-shrink: 0;
}
.ov-btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.35);
  transform: scale(1.08);
}
.ov-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.ov-btn .el-icon { font-size: 17px; }

.ov-btn-danger:hover:not(:disabled) {
  background: rgba(207,19,34,0.6);
  border-color: rgba(255,120,120,0.7);
}

/* 新增子菜单 */
.ov-btn-wrap { position: relative; }
.ov-submenu {
  position: absolute; bottom: calc(100% + 6px); left: 50%;
  transform: translateX(-50%);
  background: #fff; border: 1px solid #e8ddd0;
  border-radius: 6px; overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  white-space: nowrap; z-index: 10;
}
.ov-submenu-item {
  padding: 8px 14px; font-size: 12px; color: #3a3028;
  cursor: pointer; transition: background 0.12s;
}
.ov-submenu-item:hover { background: #faf5ee; color: #c4883a; }

/* 信息区：flex列，行间距5px，无统一卡片背景 */
.ec-card {
  flex: 1; min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

/* ── 每一行：36px固定高，白底，有边框圆角 ──────── */
.eg-row {
  display: flex;
  height: 36px;
  flex-shrink: 0;
  box-sizing: border-box;
  background: #fff;
  border: 1px solid #e8ddd0;
  border-radius: 6px;
  overflow: hidden;
}

/* 每行里的格子 */
.eg-cell {
  flex: 1; display: flex; align-items: center;
  border-right: 1px solid #f0e8dc;
  overflow: hidden;
}
.eg-cell-edit {
  border-right: none;
}
.eg-cell:last-child { border-right: none; }
.eg-full { flex: 3; }

/* label 格：100px宽，居中，有右边框 */
.eg-lbl {
  flex-shrink: 0;
  width: 100px;
  font-size: 12px; color: #6b5e4e; font-weight: 600;
  background: #faf7f2;
  border-right: 1px solid #e8ddd0;
  padding: 0 10px;
  align-self: stretch;
  display: flex; align-items: center; justify-content: center;
}
.eg-lbl-em { color: #3a3028; font-weight: 700; }

/* 编辑模式 label：加左/上/下边框（右边框已有） */
.eg-lbl-edit {
  border-left: 1px solid #e8ddd0;
  border-top: 1px solid #e8ddd0;
  border-bottom: 1px solid #e8ddd0;
}

/* value 格（查看） */
.eg-val {
  flex: 1; min-width: 0;
  padding: 0 10px;
  font-size: 13px; color: #2c2420;
  display: flex; align-items: center; gap: 6px;
  overflow: hidden;
}
.eg-txt  { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eg-mono { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace; }
.eg-dim  { color: #bbb; font-size: 12px; }

/* market tag */
.eg-inner-tag {
  flex-shrink: 0; font-size: 10px; border: 1px solid; border-radius: 3px; padding: 1px 5px;
}
.eg-tag-domestic { color: #c4883a; border-color: #f5d6a8; background: #fff7ed; }
.eg-tag-foreign  { color: #3a7bc8; border-color: #c5d9f5; background: #edf4ff; }

/* 产成品 tag */
.pk-tag {
  display: inline-block; font-size: 11px; color: #3a7bc8;
  background: #edf4ff; border: 1px solid #c5d9f5;
  border-radius: 3px; padding: 1px 5px; margin-right: 3px; flex-shrink: 0;
  font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
}

/* ── 编辑模式行：取消整行外边框和背景 ─────────── */
.eg-row-edit {
  border: none;
  background: transparent;
}
/* 自动高度行（产成品清单等内容可能超过一行）*/
.eg-row-grow {
  height: auto;
  min-height: 36px;
}
.eg-row-edit .eg-lbl {
  border-radius: 6px;
}

/* ── 编辑模式 value 格 ────────────────────────── */
.eg-val-inp {
  padding: 0 6px;
  gap: 6px;
}

/* el-autocomplete：始终显示边框，白色背景 */
.ei-auto { flex: 1; min-width: 0; }
.ei-auto :deep(.el-input__wrapper) {
  height: 26px; padding: 0 8px; border-radius: 4px;
  box-shadow: none !important;
  border: 1px solid #e8ddd0;
  background: #fff;
  transition: border-color 0.15s;
}
.ei-auto :deep(.el-input__wrapper):hover      { border-color: #c4883a; }
.ei-auto :deep(.el-input__wrapper.is-focus)   { border-color: #c4883a !important; }
.ei-auto :deep(.el-input__inner) { height: 24px; font-size: 13px; color: #2c2420; background: #fff; }

/* el-date-picker：始终显示边框，白色背景 */
.ei-date { flex: 1; min-width: 0; }
.ei-date :deep(.el-input__wrapper) {
  height: 26px; padding: 0 8px; border-radius: 4px;
  box-shadow: none !important;
  border: 1px solid #e8ddd0;
  background: #fff;
  transition: border-color 0.15s;
}
.ei-date :deep(.el-input__wrapper):hover      { border-color: #c4883a; }
.ei-date :deep(.el-input__wrapper.is-focus)   { border-color: #c4883a !important; }
.ei-date :deep(.el-input__inner) { height: 24px; font-size: 13px; color: #2c2420; background: #fff; }

/* el-select（多选，行6/7）：始终显示边框，高度与 autocomplete 一致 */
.ei-sel { flex: 1; min-width: 0; }
.ei-sel :deep(.el-select__wrapper) {
  height: 32px; min-height: 32px; padding: 0 8px; border-radius: 4px;
  box-shadow: none !important;
  border: 1px solid #e8ddd0;
  background: #fff;
  transition: border-color 0.15s;
}
.ei-sel :deep(.el-select__wrapper):hover      { border-color: #c4883a; }
.ei-sel :deep(.el-select__wrapper.is-focused) { border-color: #c4883a; box-shadow: none !important; }
.ei-sel :deep(.el-select__placeholder),
.ei-sel :deep(.el-select__input)              { font-size: 13px; }
.ei-sel :deep(.el-select__tags-text)          { font-size: 12px; }
.ei-sel :deep(.el-tag:first-child)            { margin-left: 2px; }


/* checkbox */
.ei-check { flex-shrink: 0; margin-left: auto; }
.ei-check :deep(.el-checkbox__label) { font-size: 12px; color: #6b5e4e; padding-left: 4px; }

/* ── 折叠分组区（在 ec-main 内，顶部分隔线） ── */
.ec-sections {
  border-top: 1px solid #e8ddd0;
}
.eg-sec { border-top: 1px solid #f0e8dc; }
.eg-sec:first-child { border-top: none; }
.eg-sec-hd {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 12px; cursor: pointer;
  font-size: 12px; color: #6b5e4e; font-weight: 600;
  user-select: none; transition: background 0.15s;
}
.eg-sec-hd:hover { background: #faf5ee; }
.eg-arr { color: #aaa; width: 12px; font-size: 11px; }
.eg-sec-bd { padding: 8px 12px 10px 30px; }
</style>
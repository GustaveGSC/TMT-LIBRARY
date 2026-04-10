<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import WindowControls from '@/components/common/WindowControls.vue'
import ProductTable  from './ProductTable.vue'
import ProductImage  from './ProductImage.vue'
import ProductChart  from './ProductChart.vue'
import { ArrowLeft, Upload, Setting, Folder, Collection, Memo, Timer } from '@element-plus/icons-vue'
import { usePermission } from '@/composables/usePermission'
import http from '@/api/http'

// ── 权限 ──────────────────────────────────────────
const { canEditProduct } = usePermission()
import ProductImport    from './ProductImport.vue'
import ProductRules     from './ProductRules.vue'
import ProductCategory  from './ProductCategory.vue'
import ProductTag     from './ProductTag.vue'
import ProductParam   from './ProductParam.vue'
import iconTable  from '@/assets/icons/icon_table.png'
import iconImage  from '@/assets/icons/icon_image.png'
import iconEchart from '@/assets/icons/icon_echart.png'
import { initProductStore, resetProductStore, ensureTableData, useFinishedStore, usePackagedStore } from '@/stores/product'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 当前页面 ──────────────────────────────────────
const activePage  = ref('overview')
const pageLoading = ref(false)

// ── 各页面数据加载器（按需扩展）──────────────────
const finishedStore = useFinishedStore()
const packagedStore = usePackagedStore()

const PAGE_LOADERS = {
  table: ensureTableData,
  chart: ensureTableData,
}

async function navigateTo(page) {
  if (page === activePage.value) return
  const loader = PAGE_LOADERS[page]
  const dataReady = (page === 'table' || page === 'chart')
    ? finishedStore.loaded && packagedStore.loaded
    : true
  if (loader && !dataReady) {
    // 先显示 loading 遮罩，等两帧确保浏览器完成绘制，再切页 + 加载数据
    pageLoading.value = true
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
  }
  activePage.value = page
  if (loader && !dataReady) {
    const t0 = performance.now()
    await loader()
    const loadMs = (performance.now() - t0).toFixed(0)
    // 等两帧：第一帧让 el-table 渲染数据，第二帧让 calcColWidths 完成
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    pageLoading.value = false
    console.log(`[导航] → ${page}  数据加载 ${loadMs} ms  总耗时（含渲染）${(performance.now() - t0).toFixed(0)} ms`)
  }
}

// ── 搜索 ──────────────────────────────────────────

// ── 弹窗状态 ──────────────────────────────────────
const showImportDialog   = ref(false)
const showRulesDialog    = ref(false)
const showCategoryDialog = ref(false)
const showTagDialog    = ref(false)
const showParamDialog  = ref(false)

// ── 生命周期更新状态 ──────────────────────────────
const showLifecycleDialog = ref(false)
const lifecycleRunning    = ref(false)
const lifecycleCurrent    = ref(0)
const lifecycleTotal      = ref(0)
const lifecycleProgress   = computed(() =>
  lifecycleTotal.value > 0 ? Math.round((lifecycleCurrent.value / lifecycleTotal.value) * 100) : 0
)

// ── 顶部导航配置 ──────────────────────────────────
const navItems = [
  {
    key: 'overview', label: '概览',
    svg: 'M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z M9 21V12h6v9'
  },
  { key: 'table', label: '表格', img: iconTable  },
  { key: 'image', label: '图片', img: iconImage  },
  { key: 'chart', label: '图表', img: iconEchart },
]

// ── 概览数据 ──────────────────────────────────────
const overviewStats = ref({
  totalProducts:   0,
  unprocessed:     0,
  lastImportTime:  null,
  daysSinceImport: null,
})

// 分类配色循环
const CAT_COLORS = ['#c4883a', '#4a8fc0', '#6ab47a', '#9c6fba', '#e07070', '#70aacc', '#e0a040', '#7abcaa']
const categoryStats = ref([])

// ── 生命周期更新 ──────────────────────────────────
async function handleLifecycleUpdate() {
  if (lifecycleRunning.value) return
  showLifecycleDialog.value = true
  lifecycleRunning.value  = true
  lifecycleCurrent.value  = 0
  lifecycleTotal.value    = 0

  try {
    const { ElMessage } = await import('element-plus')
    const res = await http.post('/api/product/lifecycle/update')
    if (!res.success) {
      ElMessage.error(res.message || '启动失败')
      showLifecycleDialog.value = false
      return
    }
    const taskId = res.data.task_id

    await new Promise((resolve, reject) => {
      const es = new EventSource(
        `http://127.0.0.1:8765/api/product/lifecycle/progress/${taskId}`
      )
      es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.step === 'processing') {
          lifecycleCurrent.value = data.current
          lifecycleTotal.value   = data.total
        } else if (data.step === 'done') {
          es.close()
          const d = data.data
          ElMessage.success(
            `生命周期更新完成，共更新 ${d.updated} 条记录（${d.total_models} 个型号）`
          )
          showLifecycleDialog.value = false
          resolve()
        } else if (data.step === 'error') {
          es.close()
          ElMessage.error(data.message || '更新失败')
          showLifecycleDialog.value = false
          reject(new Error(data.message))
        }
      }
      es.onerror = () => {
        es.close()
        ElMessage.error('连接中断，请重试')
        showLifecycleDialog.value = false
        reject(new Error('SSE 连接中断'))
      }
    })
  } catch {
    // ElMessage 已在内部处理
  } finally {
    lifecycleRunning.value = false
  }
}

// ── 返回首页并还原窗口尺寸 ────────────────────────
function handleBack() {
  resetProductStore()
  window.electronAPI?.unmaximizeApp?.()
  router.back()
}

// ── 生命周期 ──────────────────────────────────────
onMounted(async () => {
  window.electronAPI?.maximizeApp?.()
  initProductStore()
  // 只加载概览所需数据
  try {
    const res = await http.get('/api/product/stats')
    if (res.success) {
      overviewStats.value = {
        totalProducts:   res.data.total_finished   ?? 0,
        unprocessed:     res.data.unprocessed      ?? 0,
        lastImportTime:  res.data.last_imported_at ?? null,
        daysSinceImport: res.data.days_since_import ?? null,
      }
      categoryStats.value = (res.data.categories || []).map((cat, i) => ({
        label:       cat.description || '未分类',
        count:       cat.count,
        unprocessed: cat.unprocessed ?? 0,
        color:       CAT_COLORS[i % CAT_COLORS.length],
      }))
    }
  } catch {}
})
</script>

<template>
  <div class="product-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- ── 顶部导航栏 ──────────────────────────── -->
    <header class="top-bar">

      <!-- 左：返回 + 标题 -->
      <div class="top-left">
        <button class="btn-back" @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="page-title">产品库</span>
        <div class="title-divider"></div>
      </div>

      <!-- 中：功能导航 -->
      <nav class="top-nav">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: activePage === item.key }"
          @click="navigateTo(item.key)"
        >
          <svg v-if="item.svg" class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path :d="item.svg" />
          </svg>
          <img v-else :src="item.img" class="nav-img" :alt="item.label" />
          <span>{{ item.label }}</span>
          <span v-if="activePage === item.key" class="nav-indicator"></span>
        </button>
      </nav>

    </header>

    <!-- ── 加载遮罩 ────────────────────────────── -->
    <div v-if="pageLoading" class="page-loading">
      <div class="page-spinner"></div>
      <div class="page-loading-text">加载中…</div>
    </div>

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">

      <!-- ① 概览 -->
      <div v-show="activePage === 'overview'" class="page-overview">
        <div class="overview-body">
          <div class="welcome-title">产品库</div>
          <div class="welcome-sub">管理和查看所有产品信息</div>

          <!-- 统计卡片 -->
          <div class="stat-grid">
            <div class="stat-card">
              <div class="stat-label">成品总数</div>
              <div class="stat-value">{{ overviewStats.totalProducts || '—' }}</div>
            </div>
            <div class="stat-card warn">
              <div class="stat-label">待处理</div>
              <div class="stat-value warn-val">{{ overviewStats.unprocessed || '—' }}</div>
              <div class="stat-hint">无图片 / 无额外信息 / 无产成品</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">最近导入时间</div>
              <div class="stat-value stat-time">{{ overviewStats.lastImportTime || '暂无' }}</div>
              <div v-if="overviewStats.daysSinceImport !== null" class="stat-hint">
                {{ overviewStats.daysSinceImport === 0 ? '今天导入' : `距今 ${overviewStats.daysSinceImport} 天` }}
              </div>
            </div>
          </div>

          <!-- 分类数量 -->
          <div class="section-title">成品分类</div>
          <div class="category-cards">
            <div v-for="cat in categoryStats" :key="cat.label" class="category-card">
              <div class="cat-header">
                <span class="cat-dot" :style="{ background: cat.color }"></span>
                <span class="cat-label">{{ cat.label }}</span>
              </div>
              <div class="cat-count" :style="{ color: cat.color }">{{ cat.count }}</div>
              <div class="cat-unit">个成品</div>
              <div v-if="cat.unprocessed > 0" class="cat-unprocessed">{{ cat.unprocessed }} 个待处理</div>
            </div>
          </div>

          <!-- 快捷操作（查看数据）-->
          <div class="section-title">快捷操作</div>
          <div class="quick-grid">
            <button class="quick-btn" @click="navigateTo('table')">
              <img class="quick-img" :src="iconTable" alt="表格" />
              <span>以表格形式查看</span>
            </button>
            <button class="quick-btn" @click="navigateTo('image')">
              <img class="quick-img" :src="iconImage" alt="图片" />
              <span>以图片形式查看</span>
            </button>
            <button class="quick-btn" @click="navigateTo('chart')">
              <img class="quick-img" :src="iconEchart" alt="图表" />
              <span>以图表形式查看</span>
            </button>
          </div>
        </div>

        <!-- 工具区：固定底部，横向按钮 -->
        <div v-if="canEditProduct" class="tool-section">
          <div class="tool-section-label">数据管理</div>
          <div class="tool-btns">
            <button class="tool-btn" @click="showImportDialog = true">
              <div class="tool-btn-icon"><el-icon><Upload /></el-icon></div>
              <div class="tool-btn-body">
                <div class="tool-btn-title">导入数据</div>
                <div class="tool-btn-desc">从 ERP 导出的 Excel 文件导入</div>
              </div>
            </button>
            <button class="tool-btn" @click="showRulesDialog = true">
              <div class="tool-btn-icon"><el-icon><Setting /></el-icon></div>
              <div class="tool-btn-body">
                <div class="tool-btn-title">编码规则</div>
                <div class="tool-btn-desc">维护品号前缀与类型的映射</div>
              </div>
            </button>
            <button class="tool-btn" @click="showCategoryDialog = true">
              <div class="tool-btn-icon"><el-icon><Folder /></el-icon></div>
              <div class="tool-btn-body">
                <div class="tool-btn-title">分类管理</div>
                <div class="tool-btn-desc">维护成品的分类、系列、型号</div>
              </div>
            </button>
            <button class="tool-btn" @click="showTagDialog = true">
              <div class="tool-btn-icon"><el-icon><Collection /></el-icon></div>
              <div class="tool-btn-body">
                <div class="tool-btn-title">标签管理</div>
                <div class="tool-btn-desc">维护成品标签及颜色</div>
              </div>
            </button>
            <button class="tool-btn" @click="showParamDialog = true">
              <div class="tool-btn-icon"><el-icon><Memo /></el-icon></div>
              <div class="tool-btn-body">
                <div class="tool-btn-title">参数管理</div>
                <div class="tool-btn-desc">维护成品参数键名与分组</div>
              </div>
            </button>
            <button class="tool-btn" @click="handleLifecycleUpdate">
              <div class="tool-btn-icon"><el-icon><Timer /></el-icon></div>
              <div class="tool-btn-body">
                <div class="tool-btn-title">更新生命周期</div>
                <div class="tool-btn-desc">按发货数据推算上市/退市日期</div>
              </div>
            </button>
          </div>
        </div>

      </div>

      <!-- ② 表格视图：始终挂载，v-show 切换显示 -->
      <ProductTable v-show="activePage === 'table'" />

      <!-- ③ 图片视图 -->
      <ProductImage v-show="activePage === 'image'" />

      <!-- ④ 图表视图 -->
      <ProductChart v-show="activePage === 'chart'" />

    </main>

    <!-- ── 导入数据弹窗 ────────────────────────────── -->
    <el-dialog v-model="showImportDialog" title="导入 ERP 数据" width="640" align-center>
      <ProductImport />
    </el-dialog>

    <!-- ── 编码规则弹窗 ────────────────────────────── -->
    <el-dialog v-model="showRulesDialog" title="编码规则" width="600" align-center>
      <ProductRules />
    </el-dialog>

    <!-- ── 分类管理弹窗 ────────────────────────────── -->
    <el-dialog v-model="showCategoryDialog" title="分类管理" width="680" align-center>
      <ProductCategory />
    </el-dialog>

    <!-- ── 标签管理弹窗 ────────────────────────────── -->
    <el-dialog v-model="showTagDialog" title="标签管理" width="600" align-center>
      <ProductTag />
    </el-dialog>

    <!-- ── 参数管理弹窗 ────────────────────────────── -->
    <el-dialog v-model="showParamDialog" title="参数管理" width="640" align-center :close-on-click-modal="false">
      <ProductParam />
    </el-dialog>

    <!-- ── 生命周期更新进度弹窗 ──────────────────────── -->
    <el-dialog
      v-model="showLifecycleDialog"
      title="更新生命周期"
      width="420"
      align-center
      :close-on-click-modal="false"
      :show-close="false"
    >
      <div class="lifecycle-progress-body">
        <div class="lifecycle-progress-tip">
          正在根据发货数据推算各型号上市/退市日期，请稍候…
        </div>
        <el-progress
          :percentage="lifecycleProgress"
          :stroke-width="10"
          :color="'#c4883a'"
          style="width: 100%"
        />
        <div class="lifecycle-progress-text">
          {{ lifecycleCurrent }} / {{ lifecycleTotal }} 个型号
        </div>
      </div>
    </el-dialog>

  </div>
</template>

<style scoped>
.product-page {
  width: 100vw; height: 100vh;
  background: var(--bg);
  display: flex; flex-direction: column;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── 顶部栏 ───────────────────────────────────── */
.top-bar {
  height: 50px; display: flex; align-items: center;
  padding: 0 14px;
  background: rgba(255,255,255,0.65);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  flex-shrink: 0; z-index: 10;
}
.top-left {
  display: flex; align-items: center;
  gap: 8px; flex-shrink: 0;
}
.btn-back {
  width: 30px; height: 30px;
  border: 1px solid var(--border); border-radius: 7px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.btn-back:hover { background: var(--bg-card); color: var(--text-primary); }
.page-title { font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.05em; }
.title-divider { width: 1px; height: 16px; background: var(--border); margin-left: 8px; }

.top-nav { display: flex; align-items: center; gap: 2px; flex: 1; padding: 0 8px; }
.nav-item {
  position: relative;
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: none; border-radius: 7px;
  background: transparent; color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.18s; white-space: nowrap;
}
.nav-item:hover { background: rgba(196,136,58,0.07); color: var(--text-primary); }
.nav-item.active {
  color: var(--accent); font-weight: 600;
  background: transparent;
}
.nav-svg { width: 15px; height: 15px; flex-shrink: 0; transition: all 0.18s; }
.nav-img { width: 15px; height: 15px; flex-shrink: 0; object-fit: contain; }
/* 底部指示线 */
.nav-indicator {
  position: absolute;
  bottom: -9px; left: 50%;
  transform: translateX(-50%);
  width: 20px; height: 2px;
  background: var(--accent);
  border-radius: 1px;
}

.top-right { flex-shrink: 0; margin-left: 8px; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ── 主内容区 ─────────────────────────────────── */
.main-content {
  flex: 1; overflow: hidden;
  display: flex; flex-direction: column;
}

/* ── 概览页 ───────────────────────────────────── */
.page-overview {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  overflow: hidden;
  padding: 0;
}

/* 上方内容区：独立滚动，撑满剩余高度 */
.overview-body {
  flex: 1; min-height: 0;
  overflow-y: auto;
  padding: 36px 48px 28px;
}
.overview-body::-webkit-scrollbar { width: 4px; }
.overview-body::-webkit-scrollbar-track { background: transparent; }
.overview-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.welcome-title { font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.welcome-sub   { font-size: 13px; color: var(--text-muted); margin-bottom: 28px; }

.section-title {
  font-size: 11px; font-weight: 600; color: var(--text-muted);
  letter-spacing: 0.08em; text-transform: uppercase;
  margin: 28px 0 12px;
}

/* 统计卡片 */
.stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.stat-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px 24px; transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 4px 16px var(--shadow); }
.stat-card.warn { border-color: rgba(208,90,60,0.25); background: rgba(208,90,60,0.03); }
.stat-label  { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
.stat-value  { font-size: 34px; font-weight: 700; color: var(--accent); letter-spacing: -0.02em; }
.warn-val    { color: #d05a3c; }
.stat-time   { font-size: 16px; font-weight: 500; letter-spacing: 0; margin-top: 6px; }
.stat-hint   { font-size: 11px; color: #d05a3c; opacity: 0.7; margin-top: 6px; }

/* 分类卡片 */
.category-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.category-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px 24px; transition: box-shadow 0.2s;
}
.category-card:hover { box-shadow: 0 4px 16px var(--shadow); }
.cat-header { display: flex; align-items: center; gap: 7px; margin-bottom: 14px; }
.cat-dot    { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.cat-label  { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.cat-count  { font-size: 36px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 4px; }
.cat-unit        { font-size: 12px; color: var(--text-muted); }
.cat-unprocessed { font-size: 12px; color: #c05040; margin-top: 6px; }

/* 快捷操作 */
.quick-grid { display: flex; gap: 12px; }
.quick-btn {
  display: flex; align-items: center; gap: 10px;
  padding: 13px 20px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; color: var(--text-muted);
  font-size: 13px; font-family: inherit;
  cursor: pointer; transition: all 0.2s;
}
.quick-btn:hover {
  border-color: var(--accent); color: var(--accent);
  box-shadow: 0 4px 16px var(--shadow); transform: translateY(-1px);
}
.quick-svg { width: 18px; height: 18px; flex-shrink: 0; }
.quick-img { width: 28px; height: 28px; flex-shrink: 0; object-fit: contain; }

/* 工具区：固定在概览底部 */
.tool-section {
  border-top: 1px solid var(--border);
  padding: 16px 48px 20px;
  background: rgba(255,255,255,0.4);
  backdrop-filter: blur(8px);
  flex-shrink: 0;
}
.tool-section-label {
  font-size: 11px; font-weight: 600; color: var(--text-muted);
  letter-spacing: 0.08em; text-transform: uppercase;
  margin-bottom: 12px;
}
.tool-btns { display: flex; gap: 12px; }
.tool-btn {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 18px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; text-align: left;
  cursor: pointer; font-family: inherit;
  transition: all 0.2s;
}
.tool-btn:hover {
  border-color: var(--accent);
  box-shadow: 0 2px 12px var(--shadow);
  transform: translateY(-1px);
}
.tool-btn-icon {
  width: 34px; height: 34px; border-radius: 8px;
  background: var(--accent-bg); border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  color: var(--accent); font-size: 15px; flex-shrink: 0;
  transition: all 0.2s;
}
.tool-btn:hover .tool-btn-icon { background: var(--accent); color: #fff; border-color: var(--accent); }
.tool-btn-title { font-size: 13px; font-weight: 500; color: var(--text-primary); margin-bottom: 2px; }
.tool-btn-desc  { font-size: 11px; color: var(--text-muted); white-space: nowrap; }

/* ── 占位页 ───────────────────────────────────── */
.page-placeholder {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; opacity: 0.4;
}
.ph-img  { width: 52px; height: 52px; opacity: 0.4; }
.ph-icon  { font-size: 52px; color: var(--text-muted); }
.ph-title { font-size: 17px; font-weight: 600; color: var(--text-primary); }
.ph-desc  { font-size: 13px; color: var(--text-muted); }

/* ── 加载遮罩 ─────────────────────────────────── */
.page-loading {
  position: absolute; inset: 50px 0 0 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 14px; z-index: 100;
  background: var(--bg);
}
.page-spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.page-loading-text { font-size: 13px; color: var(--text-muted); }

/* ── 生命周期进度弹窗 ─────────────────────────── */
.lifecycle-progress-body {
  display: flex; flex-direction: column;
  align-items: center; gap: 16px;
  padding: 8px 0 4px;
}
.lifecycle-progress-tip {
  font-size: 13px; color: var(--text-muted);
  line-height: 1.6; text-align: center;
}
.lifecycle-progress-text {
  font-size: 12px; color: var(--text-muted);
}

/* ── 弹窗占位 ─────────────────────────────────── */
.dialog-placeholder {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; padding: 40px 0; opacity: 0.4;
}
.dlg-ph-icon { font-size: 36px; color: var(--text-muted); }
.dlg-ph-text { font-size: 14px; color: var(--text-muted); }
</style>
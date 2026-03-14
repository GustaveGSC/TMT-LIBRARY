<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import WindowControls from '@/components/common/WindowControls.vue'
import ProductTable  from './ProductTable.vue'
import ProductImage  from './ProductImage.vue'
import { ArrowLeft, Upload, Setting, Folder, Collection } from '@element-plus/icons-vue'
import { usePermission } from '@/composables/usePermission'

// ── 权限 ──────────────────────────────────────────
const { canEditProduct } = usePermission()
import ProductImport    from './ProductImport.vue'
import ProductRules     from './ProductRules.vue'
import ProductCategory  from './ProductCategory.vue'
import ProductTag     from './ProductTag.vue'
import iconTable  from '@/assets/icons/icon_table.png'
import iconImage  from '@/assets/icons/icon_image.png'
import iconEchart from '@/assets/icons/icon_echart.png'
import { initProductStore, resetProductStore } from '@/stores/product'

// ── 路由 ──────────────────────────────────────────
const router = useRouter()

// ── 当前页面 ──────────────────────────────────────
const activePage = ref('overview')

// ── 搜索 ──────────────────────────────────────────

// ── 弹窗状态 ──────────────────────────────────────
const showImportDialog   = ref(false)
const showRulesDialog    = ref(false)
const showCategoryDialog = ref(false)
const showTagDialog    = ref(false)

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

// ── 概览数据（后续替换为接口）────────────────────
const overviewStats = ref({
  totalProducts:  0,
  unprocessed:    0,
  lastImportTime: null,
})

const categoryStats = ref([
  { label: '学习桌', count: 0, color: '#c4883a' },
  { label: '学习椅', count: 0, color: '#4a8fc0' },
  { label: '学习灯', count: 0, color: '#6ab47a' },
])

// ── 返回首页并还原窗口尺寸 ────────────────────────
function handleBack() {
  resetProductStore()
  window.electronAPI?.unmaximizeApp?.()
  router.back()
}

// ── 生命周期 ──────────────────────────────────────
onMounted(() => {
  window.electronAPI?.maximizeApp?.()
  initProductStore()
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
          @click="activePage = item.key"
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

    <!-- ── 主内容区 ────────────────────────────── -->
    <main class="main-content">

      <!-- ① 概览 -->
      <div v-if="activePage === 'overview'" class="page-overview">
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
            </div>
          </div>

          <!-- 快捷操作（查看数据）-->
          <div class="section-title">快捷操作</div>
          <div class="quick-grid">
            <button class="quick-btn" @click="activePage = 'table'">
              <img class="quick-img" :src="iconTable" alt="表格" />
              <span>以表格形式查看</span>
            </button>
            <button class="quick-btn" @click="activePage = 'image'">
              <img class="quick-img" :src="iconImage" alt="图片" />
              <span>以图片形式查看</span>
            </button>
            <button class="quick-btn" @click="activePage = 'chart'">
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
          </div>
        </div>

      </div>

      <!-- ② 表格视图 -->
      <ProductTable v-else-if="activePage === 'table'" />

      <!-- ③ 图片视图 -->
      <ProductImage v-else-if="activePage === 'image'" />

      <!-- ④ 图表（占位）-->
      <div v-else-if="activePage === 'chart'" class="page-placeholder">
        <img :src="iconEchart" class="ph-img" alt="图表" />
        <div class="ph-title">图表视图</div>
        <div class="ph-desc">产品结构图表，即将上线</div>
      </div>

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
  flex: 1; overflow-y: auto;
  display: flex; flex-direction: column;
  padding: 0;
}
.page-overview::-webkit-scrollbar { width: 4px; }
.page-overview::-webkit-scrollbar-track { background: transparent; }
.page-overview::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* 上方内容区 */
.overview-body { padding: 36px 48px 28px; }

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
.cat-unit   { font-size: 12px; color: var(--text-muted); }

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

/* 工具区：贴底 */
.tool-section {
  margin-top: auto;
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

/* ── 弹窗占位 ─────────────────────────────────── */
.dialog-placeholder {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; padding: 40px 0; opacity: 0.4;
}
.dlg-ph-icon { font-size: 36px; color: var(--text-muted); }
.dlg-ph-text { font-size: 14px; color: var(--text-muted); }
</style>
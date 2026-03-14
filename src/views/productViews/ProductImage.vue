<script setup>
// ── 导入 ──────────────────────────────────────────
import { ref, computed } from 'vue'
import { Picture } from '@element-plus/icons-vue'

// ── Props ─────────────────────────────────────────
const props = defineProps({
  searchText: { type: String, default: '' }
})

// ── mock 数据（后续替换为接口）───────────────────
const products = ref([
  { code: '1101DL01-A', name: '成品_桌类_德罗', spec: '(V1.1)手摇1.6米榉木白色_A', market_status: 'active',       components_count: 2, image_url: null },
  { code: '1101DL02-A', name: '成品_桌类_德罗', spec: '(V1.1)手摇1.8米榉木白色_A', market_status: 'active',       components_count: 2, image_url: null },
  { code: '1101DL03-A', name: '成品_桌类_德罗', spec: '(V1.1)抽屉版手摇1.6米榉木白色_A', market_status: 'discontinued', components_count: 0, image_url: null },
])

// ── 过滤列表 ──────────────────────────────────────
const filteredProducts = computed(() => {
  const q = props.searchText.trim().toLowerCase()
  if (!q) return products.value
  return products.value.filter(p =>
    p.code.toLowerCase().includes(q) ||
    p.name.toLowerCase().includes(q) ||
    p.spec.toLowerCase().includes(q)
  )
})

// ── 状态标签 ──────────────────────────────────────
function statusLabel(s) {
  return { active: '上市中', discontinued: '已停用', pending: '待上市' }[s] || s
}
function statusType(s) {
  return { active: 'success', discontinued: 'info', pending: 'warning' }[s] || 'info'
}
</script>

<template>
  <div class="product-image">
    <div class="image-grid">
      <div
        v-for="row in filteredProducts"
        :key="row.code"
        class="image-card"
      >
        <!-- 图片区 -->
        <div class="img-area">
          <img v-if="row.image_url" :src="row.image_url" class="img-actual" :alt="row.code" />
          <div v-else class="img-placeholder">
            <el-icon class="img-ph-icon"><Picture /></el-icon>
            <span class="img-ph-text">暂无图片</span>
          </div>
        </div>

        <!-- 信息区 -->
        <div class="img-info">
          <div class="img-code">{{ row.code }}</div>
          <div class="img-name">{{ row.name }}</div>
          <div class="img-spec">{{ row.spec }}</div>
          <div class="img-footer">
            <el-tag :type="statusType(row.market_status)" size="small" round>
              {{ statusLabel(row.market_status) }}
            </el-tag>
            <span class="img-comp-count">{{ row.components_count }} 个产成品</span>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!filteredProducts.length" class="empty-state">
        <div class="empty-icon">📦</div>
        <div class="empty-text">暂无数据</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.product-image {
  flex: 1; overflow-y: auto; padding: 20px 24px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.product-image::-webkit-scrollbar { width: 4px; }
.product-image::-webkit-scrollbar-track { background: transparent; }
.product-image::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.image-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; overflow: hidden;
  cursor: pointer; transition: all 0.2s;
}
.image-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px var(--shadow);
  border-color: var(--accent);
}

.img-area {
  aspect-ratio: 4/3;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
}
.img-actual {
  width: 100%; height: 100%;
  object-fit: cover;
}
.img-placeholder {
  width: 100%; height: 100%;
  background: var(--bg);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 6px;
}
.img-ph-icon { font-size: 28px; color: var(--border); }
.img-ph-text { font-size: 11px; color: var(--text-muted); }

.img-info { padding: 12px; }
.img-code { font-family: monospace; font-size: 11px; color: var(--accent); margin-bottom: 4px; }
.img-name {
  font-size: 13px; font-weight: 500; color: var(--text-primary);
  margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.img-spec {
  font-size: 11px; color: var(--text-muted);
  margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.img-footer { display: flex; align-items: center; justify-content: space-between; }
.img-comp-count { font-size: 11px; color: var(--text-muted); }

.empty-state {
  grid-column: 1 / -1;
  display: flex; flex-direction: column;
  align-items: center; padding: 80px 0; gap: 10px;
}
.empty-icon { font-size: 36px; }
.empty-text { font-size: 13px; color: var(--text-muted); }
</style>
<!-- ─────────────────────────────────────────
  页面：page-permissions
  功能：管理员权限管理，包含角色管理（创建/删除角色、
        给角色绑定权限）和权限项管理（创建权限项）
        admin 角色不可删除，默认拥有所有权限
───────────────────────────────────────── -->

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/http'
import WindowControls from '@/components/common/WindowControls.vue'

// ── 路由 ──────────────────────────────────
const router = useRouter()

// ── 角色列表 ──────────────────────────────
const rolesLoading = ref(false)
const roles        = ref([])

// ── 角色拖拽排序 ──────────────────────────
const ROLE_ORDER_KEY = 'role_sort_order'
const dragSrcIndex   = ref(null)

// 读取保存的排序顺序（role.id 数组），对 roles 重排
function applySavedOrder(list) {
  try {
    const saved = JSON.parse(localStorage.getItem(ROLE_ORDER_KEY) || 'null')
    if (!Array.isArray(saved) || saved.length === 0) return list
    const idxMap = new Map(saved.map((id, i) => [id, i]))
    return [...list].sort((a, b) => {
      const ia = idxMap.has(a.id) ? idxMap.get(a.id) : Infinity
      const ib = idxMap.has(b.id) ? idxMap.get(b.id) : Infinity
      return ia - ib
    })
  } catch { return list }
}

function saveOrder() {
  localStorage.setItem(ROLE_ORDER_KEY, JSON.stringify(roles.value.map(r => r.id)))
}

function onDragStart(index) {
  dragSrcIndex.value = index
}

function onDragOver(e, index) {
  e.preventDefault()
  if (dragSrcIndex.value === null || dragSrcIndex.value === index) return
  const list = [...roles.value]
  const [moved] = list.splice(dragSrcIndex.value, 1)
  list.splice(index, 0, moved)
  roles.value = list
  dragSrcIndex.value = index
}

function onDragEnd() {
  dragSrcIndex.value = null
  saveOrder()
}

// ── 权限项列表 ────────────────────────────
const permsLoading = ref(false)
const permissions  = ref([])

// ── 新增角色弹窗 ──────────────────────────
const roleFormVisible = ref(false)
const roleFormLoading = ref(false)
const roleForm        = ref({ name: '', description: '' })

// ── 绑定权限弹窗 ──────────────────────────
const bindVisible   = ref(false)
const bindLoading   = ref(false)
const bindRoleId    = ref(null)
const bindRoleName  = ref('')
const selectedPerms = ref([])   // 当前勾选的权限 code 列表
const currentPerms  = ref([])   // 绑定前已有的权限 code 列表

// ── 新增/编辑权限项弹窗 ──────────────────
const permFormVisible = ref(false)
const permFormLoading = ref(false)
const permFormMode    = ref('add')   // 'add' | 'edit'
const permEditingId   = ref(null)
const permForm        = ref({ code: '', description: '' })

// ── 加载角色列表 ──────────────────────────
async function loadRoles() {
  rolesLoading.value = true
  try {
    const res = await http.get('/api/account/roles')
    if (res.success) roles.value = applySavedOrder(res.data || [])
  } catch {
    ElMessage.error('加载角色列表失败')
  } finally {
    rolesLoading.value = false
  }
}

// ── 加载权限项列表 ────────────────────────
async function loadPermissions() {
  permsLoading.value = true
  try {
    const res = await http.get('/api/account/permissions')
    if (res.success) permissions.value = res.data || []
  } catch {
    ElMessage.error('加载权限列表失败')
  } finally {
    permsLoading.value = false
  }
}

// ── 新增角色 ──────────────────────────────
function handleAddRole() {
  roleForm.value        = { name: '', description: '' }
  roleFormVisible.value = true
}

async function handleRoleFormSubmit() {
  if (!roleForm.value.name) {
    ElMessage.warning('角色名称不能为空'); return
  }
  roleFormLoading.value = true
  try {
    const res = await http.post('/api/account/roles', {
      name:        roleForm.value.name,
      description: roleForm.value.description || undefined,
    })
    if (res.success) {
      ElMessage.success('角色创建成功')
      roleFormVisible.value = false
      loadRoles()
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } catch {
    ElMessage.error('网络错误，请重试')
  } finally {
    roleFormLoading.value = false
  }
}

// 内置角色不可删除
const BUILTIN_ROLES = ['admin', 'guest']

// ── 删除角色（内置角色不可删除） ──────────
async function handleDeleteRole(row) {
  if (BUILTIN_ROLES.includes(row.name)) {
    ElMessage.warning(`「${row.name}」是内置角色，不可删除`)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除角色「${row.name}」？已分配该角色的用户将失去对应权限。`,
      '删除角色',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await http.delete(`/api/account/roles/${row.id}`)
    if (res.success) {
      ElMessage.success('角色已删除')
      loadRoles()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } catch { }
}

// ── 绑定权限弹窗 ──────────────────────────
function handleBindPermissions(row) {
  bindRoleId.value    = row.id
  bindRoleName.value  = row.name
  // 从角色已有权限中提取 code 列表
  currentPerms.value  = row.permissions || []
  selectedPerms.value = [...currentPerms.value]
  bindVisible.value   = true
}

async function handleBindSubmit() {
  bindLoading.value = true
  try {
    // 新增：在 selectedPerms 但不在 currentPerms 的权限
    const toAdd = selectedPerms.value.filter(c => !currentPerms.value.includes(c))
    for (const code of toAdd) {
      await http.post(`/api/account/roles/${bindRoleId.value}/permissions/${code}`)
    }
    ElMessage.success('权限绑定成功')
    bindVisible.value = false
    loadRoles()
  } catch {
    ElMessage.error('权限绑定失败')
  } finally {
    bindLoading.value = false
  }
}

// ── 新增权限项 ────────────────────────────
function handleAddPerm() {
  permFormMode.value    = 'add'
  permEditingId.value   = null
  permForm.value        = { code: '', name: '', description: '' }
  permFormVisible.value = true
}

// ── 编辑权限项 ────────────────────────────
function handleEditPerm(perm) {
  permFormMode.value    = 'edit'
  permEditingId.value   = perm.id
  permForm.value        = { code: perm.code, description: perm.description || '' }
  permFormVisible.value = true
}

async function handlePermFormSubmit() {
  if (!permForm.value.code) {
    ElMessage.warning('权限代码不能为空'); return
  }
  permFormLoading.value = true
  try {
    let res
    if (permFormMode.value === 'add') {
      res = await http.post('/api/account/permissions', {
        code:        permForm.value.code,
        description: permForm.value.description || undefined,
      })
    } else {
      res = await http.put(`/api/account/permissions/${permEditingId.value}`, {
        code:        permForm.value.code,
        description: permForm.value.description || undefined,
      })
    }
    if (res.success) {
      ElMessage.success(permFormMode.value === 'add' ? '权限项创建成功' : '权限项已更新')
      permFormVisible.value = false
      loadPermissions()
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } catch {
    ElMessage.error('网络错误，请重试')
  } finally {
    permFormLoading.value = false
  }
}

// ── 生命周期 ──────────────────────────────
onMounted(() => {
  loadRoles()
  loadPermissions()
})
</script>

<template>
  <div class="admin-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- 页头 -->
    <div class="page-header">
      <button class="btn-back" @click="router.back()">← 返回</button>
      <h1 class="page-title">权限管理</h1>
    </div>

    <div class="content-grid">

      <!-- 左：角色管理 -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">角色列表</div>
          <el-button size="small" type="primary" @click="handleAddRole">+ 新增角色</el-button>
        </div>

        <div v-loading="rolesLoading" class="card-body">
          <div v-if="roles.length === 0 && !rolesLoading" class="empty-tip">暂无角色</div>

          <div
            v-for="(role, index) in roles"
            :key="role.id"
            class="role-item"
            draggable="true"
            @dragstart="onDragStart(index)"
            @dragover="onDragOver($event, index)"
            @dragend="onDragEnd"
          >
            <div class="drag-handle" title="拖拽排序">⠿</div>
            <div class="role-main">
              <!-- 角色名称和描述 -->
              <div class="role-name-row">
                <span class="role-name">{{ role.name }}</span>
                <!-- 内置角色标记 -->
                <el-tag v-if="BUILTIN_ROLES.includes(role.name)" size="small" type="warning">内置</el-tag>
              </div>
              <div class="role-desc">{{ role.description || '暂无描述' }}</div>

              <!-- 已绑定权限标签 -->
              <div class="role-perms">
                <template v-if="role.name === 'admin'">
                  <span class="admin-perm-tip">拥有全部权限</span>
                </template>
                <template v-else-if="role.permissions?.length">
                  <el-tag
                    v-for="perm in role.permissions"
                    :key="perm"
                    size="small"
                    type="info"
                    style="margin:2px;"
                  >
                    {{ perm }}
                  </el-tag>
                </template>
                <span v-else class="no-perm">未绑定权限</span>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="role-actions">
              <el-button size="small" text type="primary" @click="handleBindPermissions(role)">
                绑定权限
              </el-button>
              <el-button
                v-if="!BUILTIN_ROLES.includes(role.name)"
                size="small" text type="danger"
                @click="handleDeleteRole(role)"
              >
                删除
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：权限项管理 -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">权限项</div>
          <el-button size="small" type="primary" @click="handleAddPerm">+ 新增权限</el-button>
        </div>

        <div v-loading="permsLoading" class="card-body">
          <div v-if="permissions.length === 0 && !permsLoading" class="empty-tip">暂无权限项</div>
          <div v-for="perm in permissions" :key="perm.code" class="perm-item">
            <div class="perm-item-main">
              <div class="perm-code">{{ perm.code }}</div>
              <div v-if="perm.description" class="perm-desc">{{ perm.description }}</div>
            </div>
            <el-button size="small" text type="primary" @click="handleEditPerm(perm)">编辑</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增角色弹窗 -->
    <el-dialog v-model="roleFormVisible" title="新增角色" width="380" align-center>
      <div class="dialog-form">
        <div class="field">
          <div class="field-label">角色名称 <span class="required">*</span></div>
          <el-input v-model="roleForm.name" placeholder="如 editor、viewer" />
        </div>
        <div class="field">
          <div class="field-label">描述</div>
          <el-input v-model="roleForm.description" placeholder="可选" />
        </div>
      </div>
      <template #footer>
        <el-button @click="roleFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="roleFormLoading" @click="handleRoleFormSubmit">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 绑定权限弹窗 -->
    <el-dialog v-model="bindVisible" :title="`绑定权限 — ${bindRoleName}`" width="420" align-center>
      <div class="bind-perm-list">
        <el-checkbox-group v-model="selectedPerms">
          <div
            v-for="perm in permissions"
            :key="perm.code"
            class="bind-perm-item"
          >
            <el-checkbox :value="perm.code">
              <div class="bind-perm-info">
                <span class="bind-perm-name">{{ perm.code }}</span>
                <span v-if="perm.description" class="bind-perm-desc">{{ perm.description }}</span>
              </div>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="bindVisible = false">取消</el-button>
        <el-button type="primary" :loading="bindLoading" @click="handleBindSubmit">
          确认绑定
        </el-button>
      </template>
    </el-dialog>

    <!-- 新增/编辑权限项弹窗 -->
    <el-dialog v-model="permFormVisible" :title="permFormMode === 'add' ? '新增权限项' : '编辑权限项'" width="380" align-center>
      <div class="dialog-form">
        <div class="field">
          <div class="field-label">权限代码 <span class="required">*</span></div>
          <el-input v-model="permForm.code" placeholder="如 product:edit" />
          <div class="field-hint">格式：模块:操作，如 product:edit</div>
        </div>
        <div class="field">
          <div class="field-label">描述</div>
          <el-input v-model="permForm.description" placeholder="可选" />
        </div>
      </div>
      <template #footer>
        <el-button @click="permFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="permFormLoading" @click="handlePermFormSubmit">
          {{ permFormMode === 'add' ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>

  </div>
</template>

<style scoped>
/* ── 页面基础 ─────────────────────────────── */
.admin-page {
  width: 100vw;
  min-height: 100vh;
  background: var(--bg);
  padding: 32px 40px 48px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow-y: auto;
  box-sizing: border-box;
}

/* ── 页头 ──────────────────────────────────── */
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.btn-back {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  font-family: inherit;
  transition: all 0.2s;
}
.btn-back:hover { border-color: var(--accent); color: var(--accent); }

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.03em;
}

/* ── 两列布局 ─────────────────────────────── */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
  /* 防止卡片撑出视口 */
  max-height: calc(100vh - 120px);
}

/* ── 卡片 ──────────────────────────────────── */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 2px 12px var(--shadow);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-body {
  padding: 8px 0;
  min-height: 200px;
  max-height: calc(100vh - 240px);
  overflow-y: auto;
}

.card-body::-webkit-scrollbar { width: 4px; }
.card-body::-webkit-scrollbar-track { background: transparent; }
.card-body::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}
.card-body::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ── 空状态 ────────────────────────────────── */
.empty-tip {
  text-align: center;
  padding: 40px 0;
  font-size: 13px;
  color: var(--text-muted);
}

/* ── 角色列表项 ────────────────────────────── */
.role-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  gap: 12px;
  cursor: default;
}
.role-item:last-child { border-bottom: none; }
.role-item[draggable="true"]:hover { background: var(--bg); }

.drag-handle {
  flex-shrink: 0;
  font-size: 16px;
  color: var(--text-muted);
  opacity: 0.45;
  cursor: grab;
  user-select: none;
  padding-top: 1px;
  letter-spacing: -1px;
}
.drag-handle:hover { opacity: 0.9; }
.drag-handle:active { cursor: grabbing; }

.role-main { flex: 1; min-width: 0; }

.role-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.role-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.role-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.role-perms { display: flex; flex-wrap: wrap; align-items: center; }

.admin-perm-tip {
  font-size: 11px;
  color: var(--accent);
  background: var(--accent-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 7px;
}

.no-perm {
  font-size: 11px;
  color: var(--text-muted);
  opacity: 0.6;
}

.role-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}

/* ── 权限项列表 ────────────────────────────── */
.perm-item {
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 12px;
}
.perm-item:last-child { border-bottom: none; }
.perm-item-main { flex: 1; min-width: 0; }

.perm-code {
  font-size: 11px;
  font-family: monospace;
  color: var(--accent);
  margin-bottom: 2px;
}
.perm-name {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.perm-desc { font-size: 12px; color: var(--text-muted); }

/* ── 弹窗表单 ─────────────────────────────── */
.dialog-form { padding: 4px 0; }
.field { margin-bottom: 16px; }
.field-label {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.06em;
  margin-bottom: 7px;
}
.field-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 5px;
  opacity: 0.7;
}
.required { color: var(--accent); }

/* ── 绑定权限列表 ─────────────────────────── */
.bind-perm-list {
  max-height: 360px;
  overflow-y: auto;
  padding: 4px 0;
}

.bind-perm-item {
  padding: 10px 4px;
  border-bottom: 1px solid var(--border);
}
.bind-perm-item:last-child { border-bottom: none; }

.bind-perm-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bind-perm-name {
  font-size: 13px;
  color: var(--text-primary);
  font-family: monospace;
}

.bind-perm-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: 8px;
}
</style>
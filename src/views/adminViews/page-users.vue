<!-- ─────────────────────────────────────────
  页面：page-users
  功能：管理员用户管理，包含实时搜索、用户列表、
        新增用户、编辑用户信息、重置密码、分配角色
        admin 用户固定显示管理员，无禁用/分配角色操作
───────────────────────────────────────── -->

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import http from '@/api/http'
import WindowControls from '@/components/common/WindowControls.vue'

// ── 路由 ──────────────────────────────────
const router = useRouter()

// ── 用户列表状态 ──────────────────────────
const loading = ref(false)
const users   = ref([])

// ── 搜索关键词（实时过滤） ────────────────
const keyword = ref('')

// 本地实时过滤：匹配用户名或显示名称；非 author 登录时隐藏 author 账号
const filteredUsers = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return users.value.filter(u => {
    if (u.username === 'author' && !isAuthorLogin) return false
    if (!kw) return true
    return u.username?.toLowerCase().includes(kw) ||
           u.display_name?.toLowerCase().includes(kw)
  })
})

// ── 新增/编辑弹窗状态 ────────────────────
const formVisible = ref(false)
const formMode    = ref('add')  // 'add' | 'edit'
const formLoading = ref(false)
const editingId   = ref(null)
const form        = ref({ username: '', display_name: '', password: '' })

// ── 重置密码弹窗状态 ──────────────────────
const resetVisible  = ref(false)
const resetLoading  = ref(false)
const resetTargetId = ref(null)
const resetUsername = ref('')
const resetPassword = ref('')

// ── 分配角色弹窗状态 ──────────────────────
const roleVisible   = ref(false)
const roleLoading   = ref(false)
const roleTargetId  = ref(null)
const allRoles      = ref([])
const selectedRoles = ref([])
const currentRoles  = ref([])

// ── 当前登录用户 ──────────────────────────
const currentUser = JSON.parse(localStorage.getItem('user') || '{}')
const isAuthorLogin = currentUser.username === 'author'

// ── 判断是否为受保护用户（admin / author）──
function isAdminUser(row)  { return row.roles?.includes('admin') }
function isAuthorUser(row) { return row.username === 'author' }
function isProtectedUser(row) { return row.username === 'admin' || row.username === 'author' }

// ── 加载用户列表 ──────────────────────────
async function loadUsers() {
  loading.value = true
  try {
    const res = await http.get('/api/account/users')
    if (res.success) users.value = res.data?.items || res.data || []
  } catch {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

// ── 加载角色列表 ──────────────────────────
async function loadRoles() {
  try {
    const res = await http.get('/api/account/roles')
    if (res.success) allRoles.value = res.data || []
  } catch {
    ElMessage.error('加载角色列表失败')
  }
}

// ── 新增用户 ──────────────────────────────
function handleAdd() {
  formMode.value    = 'add'
  editingId.value   = null
  form.value        = { username: '', display_name: '', password: '' }
  formVisible.value = true
}

// ── 编辑用户 ──────────────────────────────
function handleEdit(row) {
  formMode.value    = 'edit'
  editingId.value   = row.id
  form.value        = { username: row.username, display_name: row.display_name || '', password: '' }
  formVisible.value = true
}

// ── 提交新增/编辑 ─────────────────────────
async function handleFormSubmit() {
  if (!form.value.username) {
    ElMessage.warning('用户名不能为空'); return
  }
  if (formMode.value === 'add' && form.value.password.length < 6) {
    ElMessage.warning('初始密码至少 6 位'); return
  }
  formLoading.value = true
  try {
    let res
    if (formMode.value === 'add') {
      res = await http.post('/api/account/users', {
        username:     form.value.username,
        password:     form.value.password,
        display_name: form.value.display_name || undefined,
      })
    } else {
      res = await http.put(`/api/account/users/${editingId.value}`, {
        display_name: form.value.display_name || undefined,
      })
    }
    if (res.success) {
      ElMessage.success(formMode.value === 'add' ? '用户创建成功' : '用户信息已更新')
      formVisible.value = false
      loadUsers()
    } else {
      ElMessage.error(res.message || '操作失败')
    }
  } catch {
    ElMessage.error('网络错误，请重试')
  } finally {
    formLoading.value = false
  }
}

// ── 重置密码弹窗 ──────────────────────────
function handleResetPassword(row) {
  resetTargetId.value = row.id
  resetUsername.value = row.display_name || row.username
  resetPassword.value = ''
  resetVisible.value  = true
}

async function handleResetSubmit() {
  if (!resetPassword.value || resetPassword.value.length < 6) {
    ElMessage.warning('新密码至少 6 位'); return
  }
  resetLoading.value = true
  try {
    const res = await http.post(`/api/account/users/${resetTargetId.value}/reset-password`, {
      new_password: resetPassword.value
    })
    if (res.success) {
      ElMessage.success('密码重置成功')
      resetVisible.value = false
    } else {
      ElMessage.error(res.message || '重置失败')
    }
  } catch {
    ElMessage.error('网络错误，请重试')
  } finally {
    resetLoading.value = false
  }
}

// ── 分配角色弹窗（admin 用户不显示此操作） ─
async function handleAssignRole(row) {
  roleTargetId.value = row.id
  await loadRoles()
  // roles 是字符串数组，通过 name 匹配到 allRoles 里的 id
  currentRoles.value  = allRoles.value.filter(r => row.roles?.includes(r.name)).map(r => r.id)
  selectedRoles.value = [...currentRoles.value]
  roleVisible.value   = true
}

async function handleRoleSubmit() {
  roleLoading.value = true
  try {
    const toAdd    = selectedRoles.value.filter(id => !currentRoles.value.includes(id))
    const toRemove = currentRoles.value.filter(id => !selectedRoles.value.includes(id))

    for (const rid of toAdd) {
      await http.post(`/api/account/users/${roleTargetId.value}/roles/${rid}`)
    }
    for (const rid of toRemove) {
      await http.delete(`/api/account/users/${roleTargetId.value}/roles/${rid}`)
    }
    ElMessage.success('角色分配成功')
    roleVisible.value = false
    loadUsers()
  } catch {
    ElMessage.error('角色分配失败')
  } finally {
    roleLoading.value = false
  }
}

// ── 生命周期 ──────────────────────────────
onMounted(() => {
  loadUsers()
})
</script>

<template>
  <div class="admin-page">
    <WindowControls :confirm-close="true" confirm-text="确认退出两平米软件库？" />

    <!-- 页头 -->
    <div class="page-header">
      <button class="btn-back" @click="router.back()">← 返回</button>
      <h1 class="page-title">用户管理</h1>
    </div>

    <!-- 搜索栏 -->
    <div class="search-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名或显示名称..."
        clearable
        class="search-input"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <span class="search-count">共 {{ filteredUsers.length }} 位用户</span>
    </div>

    <!-- 用户表格 -->
    <div class="table-wrap">
      <el-table
        :data="filteredUsers"
        v-loading="loading"
        row-key="id"
        height="100%"
        class="user-table"
      >
        <!-- 用户名 -->
        <el-table-column prop="username" label="用户名" min-width="120" />

        <!-- 显示名称 -->
        <el-table-column prop="display_name" label="显示名称" min-width="120">
          <template #default="{ row }">
            {{ row.display_name || '—' }}
          </template>
        </el-table-column>

        <!-- 角色：admin 固定显示「管理员」 -->
        <el-table-column label="角色" min-width="140">
          <template #default="{ row }">
            <template v-if="isAdminUser(row)">
              <el-tag size="small" type="warning">管理员</el-tag>
            </template>
            <template v-else>
              <el-tag
                v-for="role in row.roles"
                :key="role"
                size="small"
                style="margin-right:4px;"
              >
                {{ role }}
              </el-tag>
              <span v-if="!row.roles?.length" class="no-role">无角色</span>
            </template>
          </template>
        </el-table-column>

        <!-- 创建时间 -->
        <el-table-column label="创建时间" min-width="120">
          <template #default="{ row }">
            {{ row.created_at?.slice(0, 10) || '—' }}
          </template>
        </el-table-column>

        <!-- 操作栏：admin 用户只显示编辑和重置密码 -->
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="action-row">
              <el-button size="small" text type="primary" @click="handleEdit(row)">编辑</el-button>
              <el-button size="small" text type="primary" @click="handleResetPassword(row)">重置密码</el-button>
              <el-button
                v-if="!isProtectedUser(row)"
                size="small" text type="primary"
                @click="handleAssignRole(row)"
              >
                分配角色
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 底栏：新增按钮 -->
      <div class="table-footer">
        <el-button type="primary" @click="handleAdd">+ 新增用户</el-button>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="formVisible"
      :title="formMode === 'add' ? '新增用户' : '编辑用户'"
      width="400"
      align-center
    >
      <div class="dialog-form">
        <div class="field">
          <div class="field-label">用户名 <span class="required">*</span></div>
          <el-input
            v-model="form.username"
            placeholder="输入用户名"
            :disabled="formMode === 'edit'"
          />
        </div>
        <div class="field">
          <div class="field-label">显示名称</div>
          <el-input v-model="form.display_name" placeholder="可选" />
        </div>
        <div v-if="formMode === 'add'" class="field">
          <div class="field-label">初始密码 <span class="required">*</span></div>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="至少 6 位"
            show-password
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="formLoading" @click="handleFormSubmit">
          {{ formMode === 'add' ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="360" align-center>
      <div class="dialog-form">
        <div class="reset-target">为「{{ resetUsername }}」设置新密码</div>
        <div class="field">
          <div class="field-label">新密码 <span class="required">*</span></div>
          <el-input
            v-model="resetPassword"
            type="password"
            placeholder="至少 6 位"
            show-password
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetLoading" @click="handleResetSubmit">
          确认重置
        </el-button>
      </template>
    </el-dialog>

    <!-- 分配角色弹窗 -->
    <el-dialog v-model="roleVisible" title="分配角色" width="360" align-center>
      <div class="role-list">
        <el-checkbox-group v-model="selectedRoles">
          <div v-for="role in allRoles" :key="role.id" class="role-item">
            <el-checkbox :value="role.id">
              <span class="role-name">{{ role.name }}</span>
              <span v-if="role.description" class="role-desc">{{ role.description }}</span>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="roleVisible = false">取消</el-button>
        <el-button type="primary" :loading="roleLoading" @click="handleRoleSubmit">确认</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<style scoped>
/* ── 页面基础 ─────────────────────────────── */
.admin-page {
  width: 100vw;
  height: 100vh;
  background: var(--bg);
  padding: 24px 40px 24px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 页头 ──────────────────────────────────── */
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
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
  flex: 1;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.03em;
}

/* ── 搜索栏 ────────────────────────────────── */
.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.search-input { width: 280px; }

.search-count {
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* ── 表格容器 ─────────────────────────────── */
.table-wrap {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 2px 12px var(--shadow);
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* el-table 撑满剩余空间 */
.table-wrap :deep(.el-table) {
  flex: 1;
  min-height: 0;
}
.table-wrap :deep(.el-table__body-wrapper) {
  overflow-y: auto;
}

/* ── 操作栏（单行） ────────────────────────── */
.action-row {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: nowrap;
}

/* ── 无角色提示 ────────────────────────────── */
.no-role {
  font-size: 12px;
  color: var(--text-muted);
  opacity: 0.6;
}

/* ── 表格底栏 ──────────────────────────────── */
.table-footer {
  display: flex;
  align-items: center;
  padding-top: 16px;
}

/* ── 弹窗表单 ─────────────────────────────── */
.dialog-form { padding: 4px 0; }

.reset-target {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
  padding: 10px 14px;
  background: var(--accent-bg);
  border-radius: 8px;
  border: 1px solid var(--border);
}

.field { margin-bottom: 16px; }
.field-label {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.06em;
  margin-bottom: 7px;
}
.required { color: var(--accent); }

/* ── 角色列表 ─────────────────────────────── */
.role-list { padding: 4px 0; }
.role-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.role-item:last-child { border-bottom: none; }
.role-name { font-size: 14px; color: var(--text-primary); }
.role-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
}
</style>
/**
 * usePermission — 权限判断 composable
 *
 * 用法：
 *   import { usePermission } from '@/composables/usePermission'
 *   const { can, canEdit } = usePermission()
 *
 * 权限码约定：
 *   developer:analytics:view
 *   account:users:view / account:users:edit
 *   account:roles:view / account:roles:edit
 *   ops:login-config:edit
 *   product:view / product:edit
 *   shipping:view / shipping:edit / shipping:export
 *   aftersale:view / aftersale:edit / aftersale:export
 *   rd:view / rd:edit / rd:admin
 *
 * 功能授权只认显式权限码，角色名/用户名不构成授权（与后端一致）。
 * isAdmin 仅用于账号保护类展示（如"管理员"标签），不能用于业务权限判断；
 * version 蓝图仍是后端唯一保留的角色名鉴权（Electron 冻结功能，未纳入本次重做）。
 */

export function usePermission() {
  // 从 localStorage 读取登录用户信息
  const userInfo = JSON.parse(localStorage.getItem('user') || '{}')

  // 仅用于展示（如"管理员"标签）或冻结的 version 页面入口，不参与业务权限判断
  const isAdmin = userInfo.roles?.includes('admin') ?? false

  // 权限码集合
  const permSet = new Set(userInfo.permissions || [])

  /**
   * 判断是否拥有某个权限码
   * @param {string} code  例如 'product:edit'
   */
  function can(code) {
    return permSet.has(code)
  }

  // ── 开发者 ────────────────────────────────────────
  const canViewAnalytics = can('developer:analytics:view')

  // ── 管理者 ────────────────────────────────────────
  const canViewUsers = can('account:users:view')
  const canEditUsers = can('account:users:edit')
  const canViewRoles = can('account:roles:view')
  const canEditRoles = can('account:roles:edit')

  // ── 运维 ──────────────────────────────────────────
  const canEditOpsLoginConfig = can('ops:login-config:edit')

  // ── 产品库 ────────────────────────────────────────
  const canViewProduct   = can('product:view')
  const canEditProduct   = can('product:edit')

  // ── 发货数据 / 数据管理 ───────────────────────────
  const canViewShipping   = can('shipping:view')
  const canEditShipping   = can('shipping:edit')
  const canExportShipping = can('shipping:export')

  // ── 售后数据 ──────────────────────────────────────
  const canViewAftersale   = can('aftersale:view')
  const canEditAftersale   = can('aftersale:edit')
  const canExportAftersale = can('aftersale:export')

  // ── 研发数据 ──────────────────────────────────────
  const canViewRd  = can('rd:view')
  const canEditRd  = can('rd:edit')
  const canAdminRd = can('rd:admin')   // 研发部管理员：管理变更提醒

  return {
    userInfo,
    isAdmin,
    can,
    canViewAnalytics,
    canViewUsers,
    canEditUsers,
    canViewRoles,
    canEditRoles,
    canEditOpsLoginConfig,
    canViewProduct,
    canEditProduct,
    canViewShipping,
    canEditShipping,
    canExportShipping,
    canViewAftersale,
    canEditAftersale,
    canExportAftersale,
    canViewRd,
    canEditRd,
    canAdminRd,
  }
}
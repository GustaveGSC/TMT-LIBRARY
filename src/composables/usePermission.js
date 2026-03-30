/**
 * usePermission — 权限判断 composable
 *
 * 用法：
 *   import { usePermission } from '@/composables/usePermission'
 *   const { isAdmin, can, canEdit } = usePermission()
 *
 * 权限码约定：
 *   product:view / product:edit / product:delete
 *   shipping:view / shipping:edit / shipping:export
 *   aftersale:view / aftersale:edit / aftersale:export
 *   rd:view / rd:edit
 */

export function usePermission() {
  // 从 localStorage 读取登录用户信息
  const userInfo = JSON.parse(localStorage.getItem('user') || '{}')

  // admin 角色直接放行
  const isAdmin = userInfo.roles?.includes('admin') ?? false

  // 权限码集合（admin 直接视为拥有全部权限）
  const permSet = new Set(userInfo.permissions || [])

  /**
   * 判断是否拥有某个权限码
   * @param {string} code  例如 'product:edit'
   */
  function can(code) {
    if (isAdmin) return true
    return permSet.has(code)
  }

  // ── 产品库 ────────────────────────────────────────
  const canViewProduct   = can('product:view')
  const canEditProduct   = can('product:edit')
  const canDeleteProduct = can('product:delete')

  // ── 发货数据 / 数据管理 ───────────────────────────
  const canViewShipping   = can('shipping:view')
  const canEditShipping   = can('shipping:edit')
  const canExportShipping = can('shipping:export')

  return {
    userInfo,
    isAdmin,
    can,
    canViewProduct,
    canEditProduct,
    canDeleteProduct,
    canViewShipping,
    canEditShipping,
    canExportShipping,
  }
}
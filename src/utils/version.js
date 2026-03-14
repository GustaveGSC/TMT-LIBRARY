/**
 * 版本检测工具
 *
 * 版本号格式：
 *   Beta x.x.x  →  测试版，强制升级
 *   V主.次.修    →  正式版
 *
 * 更新规则：
 *   当前是 Beta 版本      →  force
 *   主版本或次版本不同    →  force
 *   仅修订版更高          →  optional（小红点）
 *   相同                 →  none
 */

function parseVersion(ver = '') {
  const str = ver.trim()
  if (/^beta/i.test(str)) {
    const nums = str.replace(/^beta\s*/i, '').split('.').map(Number)
    return { isBeta: true, major: nums[0] ?? 0, minor: nums[1] ?? 0, patch: nums[2] ?? 0 }
  }
  const nums = str.replace(/^v/i, '').split('.').map(Number)
  return { isBeta: false, major: nums[0] ?? 0, minor: nums[1] ?? 0, patch: nums[2] ?? 0 }
}

/**
 * @param {string} current  当前本地版本号
 * @param {string} latest   服务器最新版本号
 * @returns {'none' | 'optional' | 'force'}
 */
export function checkUpdateType(current, latest) {
  const cur = parseVersion(current)
  const lat = parseVersion(latest)

  if (cur.isBeta) return 'force'
  if (lat.major !== cur.major || lat.minor !== cur.minor) return 'force'
  if (lat.patch > cur.patch) return 'optional'
  return 'none'
}
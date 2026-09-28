import { test, expect } from '@playwright/test'

// 登录流程：点一次登录就进主页；登录后不再额外调 /api/account/me；
// 分类树预热要等主页出来之后才发、chart-options 不预热（单 worker 下不能堵住主页请求）
const OK = (data) => ({ success: true, message: '', data })
const USER = { id: 1, username: 'tester', display_name: '测试', roles: [], permissions: ['shipping:view'],
               department_id: 1, employee_no: '001' }

async function mockApi(page, { meStatus = 200 } = {}) {
  const calls = []
  // 兜底 mock 必须放行 script：dev 下 @/api/http 模块就挂在 /api/http.js
  await page.route(url => new URL(url).pathname.startsWith('/api/'), r => {
    if (r.request().resourceType() === 'script') return r.continue()
    calls.push({ path: new URL(r.request().url()).pathname, at: Date.now() })
    return r.fulfill({ json: OK([]) })
  })
  await page.route('**/api/account/me', r => {
    calls.push({ path: '/api/account/me', at: Date.now() })
    return meStatus === 200 ? r.fulfill({ json: OK(USER) }) : r.fulfill({ status: meStatus, body: 'err' })
  })
  await page.route('**/api/account/login', r => {
    calls.push({ path: '/api/account/login', at: Date.now() })
    return r.fulfill({ json: OK(USER) })
  })
  return calls
}

test('点一次登录直接进主页，不再调 /me，预热请求在主页出来之后才发', async ({ page }) => {
  const calls = await mockApi(page)
  await page.goto('/#/login')
  await page.locator('[data-testid="login-username"]').fill('tester')
  await page.locator('input[type="password"]').fill('pw')
  await page.locator('[data-testid="login-submit"]').click()
  await expect(page).toHaveURL(/#\/index/)
  const arrivedAt = Date.now()
  expect(calls.filter(c => c.path === '/api/account/login')).toHaveLength(1)
  expect(calls.some(c => c.path === '/api/account/me')).toBe(false)
  // 分类树预热在进入主页之后才发；chart-options（缓存未命中约 11 秒）不再预热
  await expect.poll(() => calls.find(c => c.path === '/api/category/tree')?.at ?? 0,
                    { timeout: 5000 }).toBeGreaterThan(arrivedAt)
  expect(calls.some(c => c.path === '/api/shipping/chart-options')).toBe(false)
})

test('收藏夹进入时 /me 网络异常(5xx)不把人踢回登录页；401 才回登录页', async ({ page }) => {
  await page.addInitScript((u) => {
    localStorage.setItem('user', JSON.stringify(u))
    localStorage.setItem('login_time', String(Date.now()))
  }, USER)
  await mockApi(page, { meStatus: 502 })
  await page.goto('/#/index')
  await expect(page).toHaveURL(/#\/index/)

  const other = await page.context().newPage()
  await other.addInitScript((u) => {
    localStorage.setItem('user', JSON.stringify(u))
    localStorage.setItem('login_time', String(Date.now()))
  }, USER)
  await mockApi(other, { meStatus: 401 })
  await other.goto('/#/index')
  await expect(other).toHaveURL(/#\/login/)
})

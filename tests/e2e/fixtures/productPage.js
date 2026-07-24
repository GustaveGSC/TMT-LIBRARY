// page-product.vue 回归测试用固定 fixture，不依赖真实后端/账号。

export async function mockProductPage(page, { permissions = ['product:view', 'product:edit'] } = {}) {
  await page.addInitScript((perms) => {
    localStorage.setItem('user', JSON.stringify({
      id: 1,
      username: 'e2e-tester',
      display_name: 'E2E 测试账号',
      roles: [],
      permissions: perms,
    }))
    localStorage.setItem('login_time', String(Date.now()))
  }, permissions)

  await page.route('**/api/product/stats', (route) =>
    route.fulfill({
      json: {
        success: true,
        message: '',
        data: {
          total_finished: 0,
          unprocessed: 0,
          last_imported_at: null,
          days_since_import: null,
          categories: [],
        },
      },
    })
  )
}

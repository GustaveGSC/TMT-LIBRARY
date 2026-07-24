// DataMgmt 页面（/data-mgmt）回归测试用固定 fixture，不依赖真实后端/账号。
// page-data-mgmt.vue 用 v-show（非 v-if）挂载所有子组件，因此进入页面会同时触发
// DataImport/FinanceImport/OperatorConfig/EquivalentConfig/TagDimensionConfig/
// FinanceCustomerMapping 的 onMounted 请求，这里统一给一套空成功响应兜底，
// 再由具体用例按需覆盖关心的接口。

const EMPTY_OK = { success: true, message: '', data: [] }

export async function mockDataMgmtPage(page, { permissions = ['shipping:view', 'shipping:edit'] } = {}) {
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

  // 兜底：其余未特别声明的 GET 一律返回空成功，避免页面因未 mock 的请求卡在 loading
  await page.route('**/api/shipping/stats', (route) => route.fulfill({ json: EMPTY_OK }))
  await page.route('**/api/shipping/shipped-dates', (route) => route.fulfill({ json: EMPTY_OK }))
  await page.route('**/api/shipping/operators', (route) => route.fulfill({ json: EMPTY_OK }))
  await page.route('**/api/shipping/equivalents', (route) => route.fulfill({ json: EMPTY_OK }))
  await page.route('**/api/shipping/finance-customer-aliases*', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { items: [], total: 0 } } })
  )
  await page.route('**/api/product/tags/categories/*', (route) => route.fulfill({ json: EMPTY_OK }))
  await page.route('**/api/shipping/warehouses', (route) => route.fulfill({ json: EMPTY_OK }))
}

export const WAREHOUSE_LIST_RESPONSE = {
  success: true,
  message: '',
  data: [
    { warehouse_name: '主仓', is_excluded: false },
    { warehouse_name: '临时仓', is_excluded: true },
  ],
}

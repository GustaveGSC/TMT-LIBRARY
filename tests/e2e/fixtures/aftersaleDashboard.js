// AftersaleDashboard 布局回归测试用固定 fixture，独立于 shippingDashboard.js——
// 字段形状参照 src/views/aftersaleViews/AftersaleDashboard.vue 里
// loadStaticOptions()/loadCrossFilterOptions()/loadChartData() 对响应的实际读取方式。

export const CATEGORY_TREE_RESPONSE = { success: true, message: '', data: [] }
export const REASONS_RESPONSE = { success: true, message: '', data: [] }
export const SHIPPING_ALIASES_RESPONSE = { success: true, message: '', data: [] }

export const CROSS_FILTER_OPTIONS_RESPONSE = {
  success: true,
  message: '',
  data: {
    model_ids: [],
    reason_ids: [],
    shipping_alias_ids: [],
    channels: ['渠道A', '渠道B'],
    provinces: ['广东', '浙江'],
    cities: ['深圳', '杭州'],
  },
}

const PRODUCT_ITEMS = [
  { name: '产品A', value: 42, sale_ratio: 12.5 },
  { name: '产品B', value: 30, sale_ratio: 8.2 },
  { name: '产品C', value: 18, sale_ratio: null },
]

const DIM_ITEMS = [
  { name: '原因分类1', value: 25, sale_ratio: null },
  { name: '原因分类2', value: 20, sale_ratio: null },
  { name: '原因分类3', value: 15, sale_ratio: null },
]

export function chartDataResponse(groupBy) {
  return {
    success: true,
    message: '',
    data: {
      summary: { overall_ratio: 9.6 },
      items: groupBy ? DIM_ITEMS : PRODUCT_ITEMS,
    },
  }
}

/** 注入前端路由守卫需要的最小登录态，并拦截 AftersaleDashboard 挂载时会请求的接口 */
export async function mockAftersaleDashboard(page) {
  await page.addInitScript(() => {
    localStorage.setItem('user', JSON.stringify({
      id: 1,
      username: 'e2e-tester',
      display_name: 'E2E 测试账号',
      roles: [],
      permissions: ['aftersale:view', 'aftersale:edit'],
    }))
    localStorage.setItem('login_time', String(Date.now()))
  })

  // page-aftersale.vue 默认激活"概览"Tab（AftersaleOverview.vue 会挂载并请求 stats），
  // 外层 shell 自己也请求待处理数量；不拦截的话这两个请求会打到真实后端返回 401/500，
  // 污染 assertNoConsoleErrors 的控制台错误检查
  await page.route('**/api/aftersale/stats', (route) =>
    route.fulfill({ json: { success: true, message: '', data: {} } })
  )
  await page.route('**/api/aftersale/pending/count', (route) =>
    route.fulfill({ json: { success: true, message: '', data: { count: 0 } } })
  )

  await page.route('**/api/category/tree', (route) => route.fulfill({ json: CATEGORY_TREE_RESPONSE }))
  await page.route('**/api/aftersale/reasons', (route) => route.fulfill({ json: REASONS_RESPONSE }))
  await page.route('**/api/aftersale/shipping-aliases', (route) => route.fulfill({ json: SHIPPING_ALIASES_RESPONSE }))
  await page.route('**/api/aftersale/chart-filter-options', (route) =>
    route.fulfill({ json: CROSS_FILTER_OPTIONS_RESPONSE })
  )
  await page.route('**/api/aftersale/chart-data', async (route) => {
    const body = route.request().postDataJSON()
    await route.fulfill({ json: chartDataResponse(body?.group_by) })
  })
}

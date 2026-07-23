// ShippingDashboard 布局回归测试用固定 fixture，不依赖真实后端/账号。
// 字段形状参照 src/views/shippingViews/ShippingDashboard.vue 里
// loadOptions()/loadChartData() 对响应的实际读取方式。

export const CHART_OPTIONS_RESPONSE = {
  success: true,
  message: '',
  data: {
    channels: [
      { code: 'CH01', name: '渠道A' },
      { code: 'CH02', name: '渠道B' },
    ],
    provinces: ['广东', '浙江', '江苏'],
    active_category_ids: [],
    active_series_ids: [],
    active_model_ids: [],
    data_date_min: '2024-01-01',
    data_date_max: '2026-07-22',
    tag_dimensions: [],
  },
}

export const CATEGORY_TREE_RESPONSE = {
  success: true,
  message: '',
  data: [],
}

const REGION_ITEMS = [
  { label: '捷克', quantity: 5200, return_quantity: 70, actual_quantity: 5130 },
  { label: '德国', quantity: 2150, return_quantity: 56, actual_quantity: 2094 },
  { label: '台湾', quantity: 1950, return_quantity: 35, actual_quantity: 1915 },
  { label: '蒙古', quantity: 600,  return_quantity: 22, actual_quantity: 578 },
  { label: '香港', quantity: 460,  return_quantity: 19, actual_quantity: 441 },
]

const PRODUCT_ITEMS = [
  { label: '产品A', quantity: 3200, return_quantity: 40, actual_quantity: 3160 },
  { label: '产品B', quantity: 2100, return_quantity: 30, actual_quantity: 2070 },
  { label: '产品C', quantity: 1500, return_quantity: 20, actual_quantity: 1480 },
]

export function chartDataResponse(groupBy) {
  return {
    success: true,
    message: '',
    data: {
      summary: { total_quantity: 6800, total_return_quantity: 90, total_actual_quantity: 6710 },
      items: groupBy === 'province' ? REGION_ITEMS : PRODUCT_ITEMS,
    },
  }
}

/** 注入前端路由守卫需要的最小登录态（只影响前端路由判断，不涉及真实后端鉴权），
 *  并拦截 ShippingDashboard 挂载时会请求的接口，返回固定数据。 */
export async function mockShippingDashboard(page) {
  await page.addInitScript(() => {
    localStorage.setItem('user', JSON.stringify({
      id: 1,
      username: 'e2e-tester',
      display_name: 'E2E 测试账号',
      roles: [],
      permissions: ['shipping:view', 'shipping:edit'],
    }))
    localStorage.setItem('login_time', String(Date.now()))
  })

  await page.route('**/api/shipping/chart-options*', (route) =>
    route.fulfill({ json: CHART_OPTIONS_RESPONSE })
  )
  await page.route('**/api/category/tree', (route) =>
    route.fulfill({ json: CATEGORY_TREE_RESPONSE })
  )
  await page.route('**/api/shipping/chart-data', async (route) => {
    const body = route.request().postDataJSON()
    await route.fulfill({ json: chartDataResponse(body?.group_by) })
  })
}

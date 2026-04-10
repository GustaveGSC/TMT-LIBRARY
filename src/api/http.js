import axios from 'axios'

const http = axios.create({ timeout: 60000 })

// 缓存 baseURL，避免每次请求都调用 IPC
let baseURL = null

const getBaseURL = () => {
  // 不用 IPC，直接返回固定地址
  if (window.electronAPI) {
    return 'http://127.0.0.1:8765'
  }
  return import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8765'
}

// 请求拦截：动态设置 baseURL
http.interceptors.request.use(async config => {
  config.baseURL = await getBaseURL()
  return config
})

// 响应拦截：统一错误处理
http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 400) {
      return Promise.resolve(err.response.data)
    }
    const msg = err.response?.data?.message ?? err.message
    console.error('[http error]', msg)
    return Promise.reject(err)
  }
)

export default http
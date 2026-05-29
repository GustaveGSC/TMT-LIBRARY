import axios from 'axios'

const http = axios.create({ timeout: 60000 })

// 缓存 baseURL，避免每次请求都调用 IPC
let baseURL = null

export const getBaseURL = () => {
  if (window.electronAPI) {
    // 桌面端直接使用云端后端，不再本地启动 Flask
    return 'http://47.99.100.138'
  }
  return import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8765'
}

// 请求拦截：动态设置 baseURL，附加 JWT token
http.interceptors.request.use(async config => {
  config.baseURL = await getBaseURL()
  const token = localStorage.getItem('tmt_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// 响应拦截：统一错误处理
http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 401) {
      // token 过期或无效，清除会话并跳转登录页
      localStorage.removeItem('user')
      localStorage.removeItem('login_time')
      localStorage.removeItem('tmt_token')
      window.location.hash = '#/login'
      return Promise.reject(err)
    }
    if (err.response?.status === 400) {
      return Promise.resolve(err.response.data)
    }
    const msg = err.response?.data?.message ?? err.message
    console.error('[http error]', msg)
    return Promise.reject(err)
  }
)

export default http
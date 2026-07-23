import axios from 'axios'

// 会话改用 httpOnly Cookie（tmt_session），浏览器自动携带，前端不再手动存/读 token；
// withCredentials 让跨域请求（本地开发时 Vite 代理链路）也带上 Cookie
const http = axios.create({ timeout: 60000, withCredentials: true })

// 缓存 baseURL，避免每次请求都调用 IPC
let baseURL = null

export const getBaseURL = () => {
  if (window.electronAPI) {
    // 桌面端直接使用云端后端，不再本地启动 Flask
    // 必须走 HTTPS 域名：nginx 只在 tmt-library.cn:443 这个 vhost 下代理 /api/，
    // 明文 HTTP 直连 IP:80 会 404（gunicorn 只绑 127.0.0.1:8765，不对外）
    return 'https://tmt-library.cn'
  }
  return import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8765'
}

/** 读取指定名称的 Cookie 值；tmt_csrf 不是 httpOnly，前端需要读出来放进请求头做 CSRF 校验 */
function readCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

const WRITE_METHODS = new Set(['post', 'put', 'delete', 'patch'])

// 请求拦截：动态设置 baseURL，写请求附加 CSRF 请求头
http.interceptors.request.use(async config => {
  config.baseURL = await getBaseURL()
  if (WRITE_METHODS.has((config.method || '').toLowerCase())) {
    const csrf = readCookie('tmt_csrf')
    if (csrf) {
      config.headers = config.headers || {}
      config.headers['X-CSRF-Token'] = csrf
    }
  }
  return config
})

// 响应拦截：统一错误处理
http.interceptors.response.use(
  res => res.data,
  err => {
    if (err.response?.status === 401) {
      // 会话失效：只清本地展示状态并跳转登录页，Cookie 由后端 401 响应统一清除，
      // 这里不再主动调登出接口（避免 401 → 登出请求又 401 的重复处理）
      localStorage.removeItem('user')
      localStorage.removeItem('login_time')
      window.location.hash = '#/login'
      return Promise.reject(err)
    }
    if (err.response?.status === 400 || err.response?.status === 429) {
      return Promise.resolve(err.response.data)
    }
    const msg = err.response?.data?.message ?? err.message
    console.error('[http error]', msg)
    return Promise.reject(err)
  }
)

export default http
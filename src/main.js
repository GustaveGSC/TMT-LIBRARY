import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './app.vue' 
import router from './routers/index.js'

import '@/styles/themes.css'

// 恢复上次选择的主题
const savedTheme = localStorage.getItem('theme')
if (savedTheme && savedTheme !== 'theme-a') {
  document.documentElement.className = savedTheme
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
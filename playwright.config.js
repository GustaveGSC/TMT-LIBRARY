import { defineConfig } from '@playwright/test'

// 开发环境可能配置了系统级 HTTP(S)_PROXY，会拦截对 localhost 的请求返回 502，
// 导致 webServer 就绪探测和测试请求本身都失败；显式豁免本地地址。
const localHosts = 'localhost,127.0.0.1,::1'
process.env.NO_PROXY = process.env.NO_PROXY
  ? `${process.env.NO_PROXY},${localHosts}`
  : localHosts

// 响应式回归测试配置。视口矩阵覆盖笔记本分辨率+系统缩放的常见等效尺寸，
// 见 handoff/2026-07-23-codex-responsive-ui-redesign-proposal.md 第八节。
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev:web',
        url: 'http://localhost:5174',
        reuseExistingServer: true,
        timeout: 60_000,
      },
})

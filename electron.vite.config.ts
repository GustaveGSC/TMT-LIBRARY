import { resolve } from 'path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // ── 主进程 ──────────────────────────────────────
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, 'electron/main/index.ts') }
      }
    }
  },

  // ── Preload ─────────────────────────────────────
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, 'electron/preload/index.ts') }
      }
    }
  },

  // ── Vue 渲染进程 ─────────────────────────────────
  renderer: {
    root: 'src',
    plugins: [vue()],
    resolve: {
      alias: { '@': resolve('src') }
    },
    build: {
      rollupOptions: {
        // ⭐ 明确指定渲染进程入口
        input: { index: resolve(__dirname, 'src/index.html') }
      }
    }
  },

})
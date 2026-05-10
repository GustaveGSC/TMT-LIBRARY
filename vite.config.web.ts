import { resolve } from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  root: 'src',
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') }
  },
  define: {
    'import.meta.env.VITE_PLATFORM': JSON.stringify('web'),
    'import.meta.env.VITE_API_BASE': JSON.stringify(''),
  },
  build: {
    outDir: resolve(__dirname, 'dist-web'),
    emptyOutDir: true,
    rollupOptions: {
      input: { index: resolve(__dirname, 'src/index.html') }
    }
  },
  server: {
    port: 5174,
    proxy: {
      '/api': 'http://127.0.0.1:8765'
    }
  }
})

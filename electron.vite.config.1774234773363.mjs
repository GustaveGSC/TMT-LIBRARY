// electron.vite.config.ts
import { resolve } from "path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import vue from "@vitejs/plugin-vue";
var __electron_vite_injected_dirname = "E:\\Project\\tmt-library";
var electron_vite_config_default = defineConfig({
  // ── 主进程 ──────────────────────────────────────
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__electron_vite_injected_dirname, "electron/main/index.ts") }
      }
    }
  },
  // ── Preload ─────────────────────────────────────
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__electron_vite_injected_dirname, "electron/preload/index.ts") }
      }
    }
  },
  // ── Vue 渲染进程 ─────────────────────────────────
  renderer: {
    root: "src",
    plugins: [vue()],
    resolve: {
      alias: { "@": resolve("src") }
    },
    build: {
      rollupOptions: {
        // ⭐ 明确指定渲染进程入口
        input: { index: resolve(__electron_vite_injected_dirname, "src/index.html") }
      }
    }
  }
});
export {
  electron_vite_config_default as default
};

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发环境代理：/api、/ws 转发到后端 8000（与队友骨架约定一致，WS 需 ws:true）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})

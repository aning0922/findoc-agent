import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 测试可显式覆盖代理目标；普通开发默认仍使用原来的本机 8000 端口。
const apiOrigin = process.env.FINDOC_API_ORIGIN ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  envDir: process.env.FINDOC_E2E_DISABLE_ENV_FILES === '1' ? false : undefined,
  server: {
    proxy: {
      "/api": {
        target: apiOrigin,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
})

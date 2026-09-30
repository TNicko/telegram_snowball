import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxy = process.env.SNOWBALL_API_PROXY ?? 'http://127.0.0.1:8000'
const hmrClientPort = process.env.SNOWBALL_HMR_CLIENT_PORT
const dockerDev = Boolean(process.env.SNOWBALL_API_PROXY)
const dockerDevPort = Number(hmrClientPort || 8080)

export default defineConfig({
  plugins: [react()],
  server: {
    host: dockerDev ? '0.0.0.0' : '127.0.0.1',
    port: dockerDev ? dockerDevPort : 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: hmrClientPort ? { clientPort: Number(hmrClientPort) } : undefined,
    watch: dockerDev ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      '/api': {
        target: apiProxy,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})

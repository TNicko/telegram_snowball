import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxy = process.env.SNOWBALL_API_PROXY ?? 'http://127.0.0.1:8000'
const hmrClientPort = process.env.SNOWBALL_HMR_CLIENT_PORT
const dockerDev = Boolean(process.env.SNOWBALL_API_PROXY)
const dockerDevPort = Number(hmrClientPort || 8080)

function openUrlPlugin(): Plugin {
  const port = dockerDev ? dockerDevPort : 5173
  return {
    name: 'snowball-open-url',
    configureServer(server) {
      server.httpServer?.once('listening', () => {
        server.config.logger.info(`Open the UI at http://127.0.0.1:${port}`)
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), openUrlPlugin()],
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

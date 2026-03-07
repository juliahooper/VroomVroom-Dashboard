import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Load .env so VITE_API_PROXY works (backend on VM or different host)
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY || 'http://127.0.0.1:5000'

  return {
    plugins: [react()],
    root: '.',
    publicDir: 'public',
    base: '/dashboard/',
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
    server: {
      port: 5176,
      host: true, /* listen on 0.0.0.0 so port forwarding from host works */
      proxy: {
        '/orm': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
        '/dashboard/assets': { target: apiTarget, changeOrigin: true },
      },
    },
  }
})

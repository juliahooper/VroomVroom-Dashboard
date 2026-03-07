import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
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
    proxy: {
      '/orm': { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/dashboard/assets': { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
})

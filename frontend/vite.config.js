import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_DATE__: JSON.stringify(process.env.VITE_BUILD_DATE || '')
  },
  server: {
    port: 5173,
    proxy: {
      // В режиме разработки проксируем /api на бэкенд
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
  }
})

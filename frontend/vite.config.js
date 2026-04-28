import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/web-ws': {
        target: 'ws://127.0.0.1:7860',
        ws: true,
      },
      '/api': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true,
      },
      '/recordings': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true,
      },
    },
  },
})

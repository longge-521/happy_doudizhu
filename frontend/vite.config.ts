import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/ws/game': {
        target: 'ws://127.0.0.1:18088',
        ws: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:18088',
        ws: true,
      },
      '/api/game': {
        target: 'http://127.0.0.1:18088',
        changeOrigin: true,
      },
      '/api/messages': {
        target: 'http://127.0.0.1:18088',
        changeOrigin: true,
      },
      '/api/uploads': {
        target: 'http://127.0.0.1:18088',
        changeOrigin: true,
      },
      '/api/audit-logs': {
        target: 'http://127.0.0.1:18088',
        changeOrigin: true,
      },
    },
  },
})

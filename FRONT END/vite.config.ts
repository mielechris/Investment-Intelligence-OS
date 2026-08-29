import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/__iios_api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/__iios_api/, ''),
      },
      '/living': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
})

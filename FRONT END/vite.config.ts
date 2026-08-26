import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The experience preview may run on 5188 while the governed Batch 8 backend
// remains on 8002. The proxy is inert during normal frontend operation unless
// requests are explicitly sent through /__iios_api.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/__iios_api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/__iios_api/, ''),
      },
    },
  },
})

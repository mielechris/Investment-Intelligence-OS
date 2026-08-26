import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The X3 experience preview runs on 5188 while the existing governed backend
// remains on 8002. Proxying through Vite keeps preview telemetry same-origin
// without changing backend CORS, supervisor state, or execution permissions.
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

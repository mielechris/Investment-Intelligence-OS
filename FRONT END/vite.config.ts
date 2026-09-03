import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const app = env.VITE_EXPANSION_WING_APP === '1'
  const fixture = env.VITE_EXPANSION_WING_FIXTURE === '1'
  const live = env.VITE_EXPANSION_WING_LIVE_READONLY === '1'
  const recovered = env.VITE_BACKEND_RECOVERY_GREEN === '1'
  const livePair = live && recovered
  const invalid = (app && fixture === livePair) || (!app && (fixture || live || recovered)) || (live !== recovered)
  if (invalid) throw new Error('INVALID_EXPANSION_WING_BUILD_GATES')
  if (livePair && !/^http:\/\/127\.0\.0\.1:\d+\/snapshot$/.test(env.VITE_EXPANSION_WING_READONLY_ENDPOINT || '')) {
    throw new Error('INVALID_EXPANSION_WING_READONLY_ENDPOINT')
  }
  return {
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
  }
})

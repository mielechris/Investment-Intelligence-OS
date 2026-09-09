import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const app = env.VITE_EXPANSION_WING_APP === '1'
  const unified = env.VITE_UNIFIED_LIVING_FACTORY === '1'
  const fixture = env.VITE_EXPANSION_WING_FIXTURE === '1'
  const live = env.VITE_EXPANSION_WING_LIVE_READONLY === '1'
  const recovered = env.VITE_BACKEND_RECOVERY_GREEN === '1'
  const livePair = live && recovered
  const invalid = (app && fixture === livePair) || (!app && (fixture || live || recovered || unified)) || (live !== recovered)
    || (unified && !app)
  if (invalid) throw new Error('INVALID_EXPANSION_WING_BUILD_GATES')
  const defaultEndpoint = unified ? '/expansion-wing/snapshot' : '/snapshot'
  if (livePair && !/^(\/snapshot|\/expansion-wing\/snapshot|http:\/\/127\.0\.0\.1:\d+\/snapshot)$/.test(env.VITE_EXPANSION_WING_READONLY_ENDPOINT || defaultEndpoint)) {
    throw new Error('INVALID_EXPANSION_WING_READONLY_ENDPOINT')
  }
  const selectedApp = resolve(process.cwd(), unified ? 'src/LivingWallApp.tsx' : app ? 'src/ExpansionWing.tsx' : 'src/PaperFundOperationsShell.tsx')
  return {
  ...(env.VITE_TRUTH_SPINE_PREVIEW === '1' ? { base: '/review/', build: { rollupOptions: { input: resolve(process.cwd(), 'truth-spine.html') } } } : {}),
  plugins: [{
    name: 'iios-selected-app',
    resolveId(id) { return id === 'virtual:iios-selected-app' ? '\0virtual:iios-selected-app' : null },
    load(id) { return id === '\0virtual:iios-selected-app' ? `export { default } from ${JSON.stringify(selectedApp)}` : null },
  }, react()],
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

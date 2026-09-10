import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const northstar = env.VITE_NORTHSTAR_FULL_SESSION === '1'
  const app = env.VITE_EXPANSION_WING_APP === '1'
  const unified = env.VITE_UNIFIED_LIVING_FACTORY === '1'
  const fixture = env.VITE_EXPANSION_WING_FIXTURE === '1'
  const live = env.VITE_EXPANSION_WING_LIVE_READONLY === '1'
  const recovered = env.VITE_BACKEND_RECOVERY_GREEN === '1'
  const livePair = live && recovered
  const invalid = (app && fixture === livePair) || (!app && (fixture || live || recovered || unified)) || (live !== recovered)
    || (unified && !app)
  if (invalid || (northstar && (app || unified || fixture || live || recovered || env.VITE_TRUTH_SPINE_PREVIEW === '1' || env.VITE_TRUTH_INTEGRATION_PREVIEW === '1'))) throw new Error('INVALID_EXPANSION_WING_BUILD_GATES')
  const defaultEndpoint = unified ? '/expansion-wing/snapshot' : '/snapshot'
  if (livePair && !/^(\/snapshot|\/expansion-wing\/snapshot|http:\/\/127\.0\.0\.1:\d+\/snapshot)$/.test(env.VITE_EXPANSION_WING_READONLY_ENDPOINT || defaultEndpoint)) {
    throw new Error('INVALID_EXPANSION_WING_READONLY_ENDPOINT')
  }
  const selectedApp = resolve(process.cwd(), unified ? 'src/LivingWallApp.tsx' : app ? 'src/ExpansionWing.tsx' : 'src/PaperFundOperationsShell.tsx')
  return {
  ...(northstar ? { base: '/review/', publicDir: false, build: { rollupOptions: { input: resolve(process.cwd(), 'northstar-session.html') } } } : {}),
  ...(env.VITE_TRUTH_SPINE_PREVIEW === '1' || env.VITE_TRUTH_INTEGRATION_PREVIEW === '1' ? { base: '/review/', build: { rollupOptions: { input: resolve(process.cwd(), env.VITE_TRUTH_INTEGRATION_PREVIEW === '1' ? 'truth-integration.html' : 'truth-spine.html') } } } : {}),
  plugins: [{
    name: 'iios-selected-app',
    resolveId(id) { return id === 'virtual:iios-selected-app' ? '\0virtual:iios-selected-app' : null },
    load(id) { return id === '\0virtual:iios-selected-app' ? `export { default } from ${JSON.stringify(selectedApp)}` : null },
  }, react(), ...(northstar ? [{
    name: 'northstar-unused-portrait-pruning',
    generateBundle(_options: unknown, bundle: import('rolldown').OutputBundle) {
      // Vite emits imported moving portraits even when their unused export was
      // tree-shaken. Package only assets referenced by the emitted application.
      const code = Object.values(bundle).map(x => x.type === 'chunk' ? x.code : typeof x.source === 'string' ? x.source : '').join('\n')
      for (const name of Object.keys(bundle)) if (/-move-[A-Za-z0-9_-]+\.webp$/.test(name) && !code.includes(name)) delete bundle[name]
    },
  }] : [])],
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

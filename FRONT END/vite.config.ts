import { defineConfig, type ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'

const READ_ONLY_SIDECAR = 'http://127.0.0.1:5176'

// These are browser artifacts already published into the active, localhost-only
// IIOS sidecar by the preserved 9O–10M publishers. V6 only reads them; it does
// not create, mutate, or infer any of their investment state.
const PRESERVED_BROWSER_ARTIFACTS = [
  'daily_factory_episode.json',
  'chief_intelligence_office.json',
  'experiment_ab_laboratory.json',
  'data_expansion_factory.json',
  'agent_performance_league.json',
  'market_regime_intelligence.json',
  'unified_production_browser.json',
  'paper_performance_qualification.json',
  'portfolio_intelligence.json',
  'capital_preservation_stress_lab.json',
  'governed_capital_readiness.json',
  'institutional_investment_firm_os.json',
  'qualification_watch.json',
  'historical_market_intelligence.json',
  'chief_intelligence_office_v2.json',
  'historical_event_reconstruction.json',
  'historical_macro_regime_library.json',
  'benchmark_alpha_attribution.json',
  'data_health_watchdog.json',
  'model_cost_governor.json',
] as const

function proxyConfig(): Record<string, string | ProxyOptions> {
  const proxy: Record<string, string | ProxyOptions> = {
    '/__iios_api': {
      target: 'http://127.0.0.1:8002',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/__iios_api/, ''),
    },
    '/living': {
      target: READ_ONLY_SIDECAR,
      changeOrigin: true,
    },
    '/validation': {
      target: READ_ONLY_SIDECAR,
      changeOrigin: true,
    },
    '/health': {
      target: READ_ONLY_SIDECAR,
      changeOrigin: true,
    },
  }

  for (const artifact of PRESERVED_BROWSER_ARTIFACTS) {
    proxy[`/${artifact}`] = {
      target: READ_ONLY_SIDECAR,
      changeOrigin: true,
    }
  }

  return proxy
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: proxyConfig(),
  },
  preview: {
    proxy: proxyConfig(),
  },
})

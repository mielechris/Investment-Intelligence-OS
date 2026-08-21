import { useEffect, useState } from 'react'

const API_BASE = 'http://localhost:8000'

type Candidate = {
  candidate_id: string
  status: string
  risk_review_id: string
  packet?: {
    risk_result?: {
      headline?: string
      decision?: string
      risk_level?: string
      paper_execution_eligible?: boolean
    }
  }
  simulated_order?: {
    execution?: string
    simulated_notional?: number
    real_notional?: number
    broker_order_sent?: boolean
  } | null
}

type Response = {
  counts: { ready: number; simulated: number }
  items: Candidate[]
}

export default function PaperExecutionPanel() {
  const [data, setData] = useState<Response | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const refresh = async () => {
      try {
        const response = await fetch(`${API_BASE}/intelligence/feeds/paper-execution?limit=10`)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const next = (await response.json()) as Response
        if (!cancelled) {
          setData(next)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Paper execution feed unavailable')
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return (
    <section
      style={{
        border: '1px solid #315a49',
        background: '#07100c',
        borderRadius: '16px',
        padding: '24px',
        marginBottom: '26px',
        color: '#eef6ff',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ color: '#69c89d', fontSize: '11px', letterSpacing: '4px' }}>PAPER EXECUTION // READINESS</div>
          <h2 style={{ margin: '7px 0 6px', fontSize: '25px' }}>Simulation Gate</h2>
          <div style={{ color: '#82988f', fontSize: '13px' }}>
            Only Risk-cleared WATCH_ONLY cases can become simulated paper orders.
          </div>
        </div>
        <div style={{ border: '1px solid #6e3440', background: '#190a0f', color: '#ef8092', borderRadius: '8px', padding: '10px 14px', fontWeight: 800, letterSpacing: '2px', fontSize: '11px' }}>
          REAL CAPITAL $0
        </div>
      </div>

      <div style={{ display: 'flex', gap: '12px', marginTop: '18px', flexWrap: 'wrap' }}>
        <div style={{ border: '1px solid #29483b', borderRadius: '10px', padding: '13px 18px', minWidth: '150px' }}>
          <div style={{ color: '#728b81', fontSize: '10px', letterSpacing: '2px' }}>READY</div>
          <strong style={{ fontSize: '25px' }}>{data?.counts.ready ?? 0}</strong>
        </div>
        <div style={{ border: '1px solid #29483b', borderRadius: '10px', padding: '13px 18px', minWidth: '150px' }}>
          <div style={{ color: '#728b81', fontSize: '10px', letterSpacing: '2px' }}>SIMULATED</div>
          <strong style={{ fontSize: '25px' }}>{data?.counts.simulated ?? 0}</strong>
        </div>
      </div>

      {error && <div style={{ marginTop: '14px', color: '#e68191' }}>{error}</div>}

      <div style={{ marginTop: '16px', borderTop: '1px solid #20352c' }}>
        {(data?.items ?? []).length === 0 ? (
          <div style={{ padding: '18px 0', color: '#71857d', fontSize: '13px' }}>
            No paper-ready candidates yet. Current Risk vetoes remain blocked.
          </div>
        ) : (
          data!.items.slice(0, 6).map((item) => {
            const result = item.packet?.risk_result
            return (
              <div key={item.candidate_id} style={{ padding: '13px 0', borderBottom: '1px solid #20352c' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                  <strong style={{ fontSize: '13px' }}>{result?.headline ?? 'Paper execution candidate'}</strong>
                  <span style={{ color: '#69c89d', fontSize: '10px', fontWeight: 800 }}>{item.status.toUpperCase()}</span>
                </div>
                <div style={{ color: '#789187', fontSize: '11px', marginTop: '4px' }}>
                  {result?.risk_level ?? '—'} risk · {result?.decision ?? '—'} · broker order sent: NO
                </div>
                {item.simulated_order && (
                  <div style={{ color: '#9db3a9', fontSize: '11px', marginTop: '5px' }}>
                    Simulated notional ${Math.round(item.simulated_order.simulated_notional ?? 0).toLocaleString()} · real notional $0
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </section>
  )
}

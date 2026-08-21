import { useCallback, useEffect, useState } from 'react'

const API_BASE = 'http://localhost:8000'

type Position = {
  position_id: string
  symbol: string
  side: string
  quantity: number
  entry_price: number
  mark_price: number
  simulated_notional: number
  unrealized_pnl: number
  realized_pnl: number
  status: string
  synthetic_fixture: boolean
}

type PortfolioResponse = {
  summary: {
    positions: number
    open_positions: number
    simulated_notional: number
    unrealized_pnl: number
    realized_pnl: number
    real_capital: number
  }
  positions: Position[]
}

export default function PaperPortfolioPanel() {
  const [data, setData] = useState<PortfolioResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/intelligence/feeds/paper-portfolio?limit=20`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setData((await response.json()) as PortfolioResponse)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Paper portfolio unavailable')
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const markUpFivePercent = async (position: Position) => {
    setBusy(true)
    try {
      const nextMark = position.entry_price * 1.05
      const response = await fetch(
        `${API_BASE}/intelligence/feeds/paper-portfolio/${position.position_id}/mark?mark_price=${encodeURIComponent(nextMark)}&source=synthetic_ui_test`,
        { method: 'POST' },
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await refresh()
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not mark paper position')
    } finally {
      setBusy(false)
    }
  }

  const summary = data?.summary

  return (
    <section style={{ border: '1px solid #35566f', background: '#071019', borderRadius: '16px', padding: '24px', marginBottom: '26px', color: '#eef6ff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ color: '#72b9e6', fontSize: '11px', letterSpacing: '4px' }}>PAPER PORTFOLIO // P&L LEDGER</div>
          <h2 style={{ margin: '7px 0 6px', fontSize: '25px' }}>Learning Ledger</h2>
          <div style={{ color: '#8193a4', fontSize: '13px' }}>Every simulated order becomes a traceable position tied back to its Risk and thesis context.</div>
        </div>
        <div style={{ border: '1px solid #6e3440', background: '#190a0f', color: '#ef8092', borderRadius: '8px', padding: '10px 14px', fontWeight: 800, letterSpacing: '2px', fontSize: '11px' }}>REAL CAPITAL $0</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))', gap: '12px', marginTop: '18px' }}>
        {[['OPEN POSITIONS', summary?.open_positions ?? 0], ['PAPER NOTIONAL', `$${Math.round(summary?.simulated_notional ?? 0).toLocaleString()}`], ['UNREALIZED P&L', `$${Math.round(summary?.unrealized_pnl ?? 0).toLocaleString()}`], ['REALIZED P&L', `$${Math.round(summary?.realized_pnl ?? 0).toLocaleString()}`]].map(([label, value]) => (
          <div key={String(label)} style={{ border: '1px solid #294257', borderRadius: '10px', padding: '13px 16px' }}>
            <div style={{ color: '#718599', fontSize: '10px', letterSpacing: '2px' }}>{label}</div>
            <strong style={{ fontSize: '24px' }}>{value}</strong>
          </div>
        ))}
      </div>

      {error && <div style={{ marginTop: '14px', color: '#e68191' }}>{error}</div>}

      <div style={{ marginTop: '16px', borderTop: '1px solid #22384a' }}>
        {(data?.positions ?? []).length === 0 ? (
          <div style={{ padding: '18px 0', color: '#718599', fontSize: '13px' }}>No paper positions yet.</div>
        ) : (
          data!.positions.slice(0, 8).map((position) => (
            <div key={position.position_id} style={{ padding: '13px 0', borderBottom: '1px solid #22384a' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start' }}>
                <div>
                  <strong style={{ fontSize: '13px' }}>{position.symbol} · {position.side}</strong>
                  {position.synthetic_fixture && <div style={{ color: '#d8ad59', fontSize: '10px', marginTop: '4px', fontWeight: 800 }}>SYNTHETIC TEST POSITION</div>}
                </div>
                <span style={{ color: position.unrealized_pnl >= 0 ? '#6dc9a1' : '#e27d8d', fontWeight: 800, fontSize: '12px' }}>
                  {position.unrealized_pnl >= 0 ? '+' : ''}${Math.round(position.unrealized_pnl).toLocaleString()}
                </span>
              </div>
              <div style={{ color: '#8193a4', fontSize: '11px', marginTop: '5px' }}>
                entry ${position.entry_price.toFixed(2)} · mark ${position.mark_price.toFixed(2)} · qty {position.quantity.toFixed(2)} · paper notional ${Math.round(position.simulated_notional).toLocaleString()}
              </div>
              {position.synthetic_fixture && position.mark_price === position.entry_price && (
                <button type="button" disabled={busy} onClick={() => void markUpFivePercent(position)} style={{ marginTop: '9px', border: '1px solid #386080', background: '#0b1822', color: '#78bde8', borderRadius: '8px', padding: '8px 12px', fontWeight: 800, cursor: busy ? 'wait' : 'pointer' }}>
                  {busy ? 'MARKING…' : 'TEST MARK +5%'}
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  )
}

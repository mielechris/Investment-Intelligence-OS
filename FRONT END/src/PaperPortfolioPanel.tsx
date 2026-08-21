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
    closed_positions?: number
    simulated_notional: number
    unrealized_pnl: number
    realized_pnl: number
    real_capital: number
  }
  positions: Position[]
}

type OutcomeItem = {
  review_id: string
  outcome: string
  return_pct: number
  review: {
    symbol?: string
    side?: string
    realized_pnl?: number
    return_pct?: number
    synthetic_fixture?: boolean
    original_risk_decision?: string
  }
}

type OutcomeResponse = { items: OutcomeItem[] }

export default function PaperPortfolioPanel() {
  const [data, setData] = useState<PortfolioResponse | null>(null)
  const [outcomes, setOutcomes] = useState<OutcomeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [portfolioResponse, outcomeResponse] = await Promise.all([
        fetch(`${API_BASE}/intelligence/feeds/paper-portfolio?limit=20`),
        fetch(`${API_BASE}/intelligence/feeds/outcome-learning?limit=10`),
      ])
      if (!portfolioResponse.ok) throw new Error(`Portfolio HTTP ${portfolioResponse.status}`)
      if (!outcomeResponse.ok) throw new Error(`Outcome HTTP ${outcomeResponse.status}`)
      setData((await portfolioResponse.json()) as PortfolioResponse)
      setOutcomes((await outcomeResponse.json()) as OutcomeResponse)
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

  const closeAtMark = async (position: Position) => {
    setBusy(true)
    try {
      const response = await fetch(
        `${API_BASE}/intelligence/feeds/paper-portfolio/${position.position_id}/close?exit_price=${encodeURIComponent(position.mark_price)}&source=synthetic_ui_close`,
        { method: 'POST' },
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await refresh()
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not close paper position')
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '12px', marginTop: '18px' }}>
        {[
          ['OPEN', summary?.open_positions ?? 0],
          ['CLOSED', summary?.closed_positions ?? 0],
          ['PAPER NOTIONAL', `$${Math.round(summary?.simulated_notional ?? 0).toLocaleString()}`],
          ['UNREALIZED P&L', `$${Math.round(summary?.unrealized_pnl ?? 0).toLocaleString()}`],
          ['REALIZED P&L', `$${Math.round(summary?.realized_pnl ?? 0).toLocaleString()}`],
        ].map(([label, value]) => (
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
          data!.positions.slice(0, 8).map((position) => {
            const displayPnl = position.status === 'closed' ? position.realized_pnl : position.unrealized_pnl
            return (
              <div key={position.position_id} style={{ padding: '13px 0', borderBottom: '1px solid #22384a' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start' }}>
                  <div>
                    <strong style={{ fontSize: '13px' }}>{position.symbol} · {position.side}</strong>
                    <div style={{ color: position.status === 'closed' ? '#b78bfa' : '#72b9e6', fontSize: '10px', marginTop: '4px', fontWeight: 800 }}>{position.status.toUpperCase()}</div>
                    {position.synthetic_fixture && <div style={{ color: '#d8ad59', fontSize: '10px', marginTop: '4px', fontWeight: 800 }}>SYNTHETIC TEST POSITION</div>}
                  </div>
                  <span style={{ color: displayPnl >= 0 ? '#6dc9a1' : '#e27d8d', fontWeight: 800, fontSize: '12px' }}>
                    {displayPnl >= 0 ? '+' : ''}${Math.round(displayPnl).toLocaleString()}
                  </span>
                </div>
                <div style={{ color: '#8193a4', fontSize: '11px', marginTop: '5px' }}>
                  entry ${position.entry_price.toFixed(2)} · {position.status === 'closed' ? 'exit' : 'mark'} ${position.mark_price.toFixed(2)} · qty {position.quantity.toFixed(2)} · original paper notional ${Math.round(position.simulated_notional).toLocaleString()}
                </div>
                {position.synthetic_fixture && position.status === 'open' && position.mark_price === position.entry_price && (
                  <button type="button" disabled={busy} onClick={() => void markUpFivePercent(position)} style={{ marginTop: '9px', border: '1px solid #386080', background: '#0b1822', color: '#78bde8', borderRadius: '8px', padding: '8px 12px', fontWeight: 800, cursor: busy ? 'wait' : 'pointer' }}>
                    {busy ? 'MARKING…' : 'TEST MARK +5%'}
                  </button>
                )}
                {position.status === 'open' && (
                  <button type="button" disabled={busy} onClick={() => void closeAtMark(position)} style={{ marginTop: '9px', marginLeft: '8px', border: '1px solid #684d82', background: '#160e20', color: '#c4a0ee', borderRadius: '8px', padding: '8px 12px', fontWeight: 800, cursor: busy ? 'wait' : 'pointer' }}>
                    {busy ? 'CLOSING…' : 'CLOSE @ MARK'}
                  </button>
                )}
              </div>
            )
          })
        )}
      </div>

      <div style={{ marginTop: '20px', borderTop: '1px solid #39405b', paddingTop: '16px' }}>
        <div style={{ color: '#b78bfa', fontSize: '10px', letterSpacing: '3px' }}>OUTCOME LEARNING // HISTORY FEEDBACK</div>
        <h3 style={{ margin: '7px 0 10px' }}>Closed-Trade Postmortems</h3>
        {(outcomes?.items ?? []).length === 0 ? (
          <div style={{ color: '#718599', fontSize: '13px' }}>No closed outcomes yet.</div>
        ) : (
          outcomes!.items.slice(0, 6).map((item) => (
            <div key={item.review_id} style={{ borderTop: '1px solid #2c3042', padding: '10px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                <strong style={{ fontSize: '12px' }}>{item.review.symbol ?? 'Paper position'} · {item.outcome}</strong>
                <span style={{ color: item.return_pct >= 0 ? '#6dc9a1' : '#e27d8d', fontSize: '11px', fontWeight: 800 }}>{item.return_pct >= 0 ? '+' : ''}{item.return_pct.toFixed(2)}%</span>
              </div>
              <div style={{ color: '#8193a4', fontSize: '11px', marginTop: '4px' }}>
                realized ${Math.round(item.review.realized_pnl ?? 0).toLocaleString()} · original risk {item.review.original_risk_decision ?? '—'} · routed back to market-history evidence
              </div>
              {item.review.synthetic_fixture && <div style={{ color: '#d8ad59', fontSize: '10px', marginTop: '4px', fontWeight: 800 }}>SYNTHETIC LEARNING FIXTURE</div>}
            </div>
          ))
        )}
      </div>
    </section>
  )
}

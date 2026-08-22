import { FormEvent, useState } from 'react'

const API_BASE = 'http://localhost:8000'

type Stance = 'SUPPORT' | 'NEUTRAL' | 'OPPOSE'

type AgentReview = {
  agent_id: string
  agent_name: string
  headline?: string
  stance: Stance
  confidence: number
  view?: string
  supporting_points?: string[]
  risks?: string[]
  missing_evidence?: string[]
  invalidation_checks?: string[]
  disposition?: string
  error?: boolean
}

type VoteSummary = {
  support: number
  neutral: number
  oppose: number
  average_confidence: number
  agent_count: number
}

type CouncilChair = {
  decision?: string
  confidence?: number
  headline?: string
  summary?: string
  strongest_support?: string
  strongest_objection?: string
  unresolved_disagreements?: string[]
  missing_evidence?: string[]
  disposition?: string
}

type RiskGate = {
  decision?: string
  risk_level?: string
  headline?: string
  primary_risks?: string[]
  downside_scenarios?: string[]
  liquidity_assessment?: string
  sizing_constraints?: string[]
  hard_vetoes?: string[]
  missing_evidence?: string[]
  allowed_notional?: number
  confidence?: number
  paper_execution_eligible?: boolean
}

type Diagnostics = {
  alpha_vantage_history?: string
  alpha_vantage_overview?: string
  alpha_vantage_earnings?: string
  alpha_vantage_earnings_calendar?: string
  alpha_vantage_macro?: Record<string, string>
  sec_company?: string
  sec_filings?: number
  fred?: Record<string, string>
  archive_matches?: number
}

type CouncilResult = {
  mode?: string
  simulation_only?: boolean
  paper_mode?: boolean
  live_execution?: boolean
  real_capital?: number
  vote_summary: VoteSummary
  agent_reviews: AgentReview[]
  council_chair: CouncilChair
  risk_gate: RiskGate
  paper_execution_eligible: boolean
  simulated_order?: {
    execution?: string
    asset?: string
    side?: string
    simulated_notional?: number
    real_notional?: number
    broker_order_sent?: boolean
    live_execution?: boolean
    paper_mode?: boolean
  } | null
  live_evidence_enrichment?: {
    requested_asset?: string
    evidence_item_count?: number
    diagnostics?: Diagnostics
    provider_evidence?: unknown[]
  }
}

function splitLines(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function stanceColor(stance: Stance) {
  if (stance === 'SUPPORT') return '#70caa5'
  if (stance === 'OPPOSE') return '#ef8092'
  return '#d8ad59'
}

function decisionColor(value?: string) {
  const normalized = (value ?? '').toUpperCase()
  if (normalized.includes('PASS') || normalized.includes('WATCH_ONLY')) return '#70caa5'
  if (normalized.includes('REJECT') || normalized.includes('VETO')) return '#ef8092'
  return '#d8ad59'
}

function statusColor(value?: string) {
  if ((value ?? '').startsWith('ok')) return '#70caa5'
  if ((value ?? '').includes('not_configured')) return '#d8ad59'
  return '#ef8092'
}

export default function CouncilPanel() {
  const [asset, setAsset] = useState('MSFT')
  const [aliases, setAliases] = useState('Microsoft, Microsoft Corp, Microsoft Corporation')
  const [direction, setDirection] = useState<'LONG' | 'SHORT' | 'WATCH'>('LONG')
  const [horizon, setHorizon] = useState('1-3 months')
  const [thesis, setThesis] = useState('Microsoft may offer a favorable paper-trade setup if strong cloud and AI growth, cash generation, valuation, market structure, and macro conditions remain supportive.')
  const [catalysts, setCatalysts] = useState('Continued Azure and AI revenue growth\nOngoing enterprise adoption of Microsoft 365 Copilot and Azure AI\nExecution against forward cloud guidance')
  const [invalidation, setInvalidation] = useState('Azure growth materially decelerates\nFree cash flow weakens materially\nValuation expands beyond defensible historical or peer levels\nPrice structure breaks down on heavy volume\nHigher rates materially compress large-cap technology valuations')
  const [simulatedNotional, setSimulatedNotional] = useState(10000)
  const [result, setResult] = useState<CouncilResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function runCouncil(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(`${API_BASE}/intelligence/council/simulate-live`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: `${asset.toUpperCase()} live-evidence 8-agent council test`,
          asset: asset.toUpperCase(),
          aliases: aliases.split(',').map((item) => item.trim()).filter(Boolean),
          direction,
          horizon,
          thesis,
          catalysts: splitLines(catalysts),
          invalidation: splitLines(invalidation),
          simulated_notional: simulatedNotional,
        }),
      })
      if (!response.ok) {
        const text = await response.text()
        throw new Error(`Council HTTP ${response.status}: ${text}`)
      }
      setResult(await response.json() as CouncilResult)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Council simulation failed')
    } finally {
      setLoading(false)
    }
  }

  const diagnostics = result?.live_evidence_enrichment?.diagnostics

  return (
    <section style={{ border: '1px solid #2d6c79', background: '#061014', borderRadius: '16px', padding: '24px', marginBottom: '26px', color: '#eef6ff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ color: '#63c6d8', fontSize: '11px', letterSpacing: '4px' }}>EIGHT-AGENT COUNCIL // LIVE EVIDENCE</div>
          <h2 style={{ margin: '7px 0 6px', fontSize: '25px' }}>Full Council Paper Simulator</h2>
          <div style={{ color: '#89a7ad', fontSize: '13px' }}>Live evidence → 8 independent specialists → Council Chair → isolated Risk gate → hypothetical paper order.</div>
        </div>
        <div style={{ border: '1px solid #6e3440', background: '#190a0f', color: '#ef8092', borderRadius: '8px', padding: '10px 14px', fontWeight: 800, letterSpacing: '2px', fontSize: '11px', height: 'fit-content' }}>REAL CAPITAL $0</div>
      </div>

      <form onSubmit={runCouncil} style={{ marginTop: '18px', display: 'grid', gap: '12px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 0.7fr) minmax(160px, 1fr) minmax(130px, 0.8fr) minmax(150px, 0.9fr)', gap: '10px' }}>
          <input value={asset} onChange={(event) => setAsset(event.target.value)} placeholder="Ticker" style={inputStyle} />
          <input value={aliases} onChange={(event) => setAliases(event.target.value)} placeholder="Aliases, comma separated" style={inputStyle} />
          <select value={direction} onChange={(event) => setDirection(event.target.value as 'LONG' | 'SHORT' | 'WATCH')} style={inputStyle}>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
            <option value="WATCH">WATCH</option>
          </select>
          <input value={horizon} onChange={(event) => setHorizon(event.target.value)} placeholder="Horizon" style={inputStyle} />
        </div>

        <textarea value={thesis} onChange={(event) => setThesis(event.target.value)} rows={3} placeholder="Paper thesis" style={textareaStyle} />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <textarea value={catalysts} onChange={(event) => setCatalysts(event.target.value)} rows={5} placeholder="Catalysts, one per line" style={textareaStyle} />
          <textarea value={invalidation} onChange={(event) => setInvalidation(event.target.value)} rows={5} placeholder="Invalidation checks, one per line" style={textareaStyle} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <label style={{ color: '#91abb0', fontSize: '12px' }}>Paper notional</label>
          <input type="number" min={0} max={1000000} step={1000} value={simulatedNotional} onChange={(event) => setSimulatedNotional(Number(event.target.value))} style={{ ...inputStyle, width: '150px' }} />
          <button type="submit" disabled={loading || !asset.trim() || !thesis.trim()} style={{ border: '1px solid #2d8fa1', background: loading ? '#102126' : '#09252c', color: '#82dceb', borderRadius: '8px', padding: '11px 18px', fontWeight: 900, letterSpacing: '1px', cursor: loading ? 'wait' : 'pointer' }}>
            {loading ? 'RUNNING 8 AGENTS + CHAIR + RISK…' : 'RUN LIVE COUNCIL'}
          </button>
          <span style={{ color: '#617e84', fontSize: '11px' }}>Simulation-only. No production Committee/Risk/Portfolio/Memory writes.</span>
        </div>
      </form>

      {error && <div style={{ marginTop: '14px', color: '#ef8092', border: '1px solid #5a2731', background: '#16090d', borderRadius: '8px', padding: '10px 12px' }}>{error}</div>}

      {result && (
        <div style={{ marginTop: '20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px' }}>
            <Metric label="SUPPORT" value={result.vote_summary.support} color="#70caa5" />
            <Metric label="NEUTRAL" value={result.vote_summary.neutral} color="#d8ad59" />
            <Metric label="OPPOSE" value={result.vote_summary.oppose} color="#ef8092" />
            <Metric label="AVG CONF" value={`${Math.round(result.vote_summary.average_confidence * 100)}%`} color="#82dceb" />
            <Metric label="LIVE EVIDENCE" value={result.live_evidence_enrichment?.evidence_item_count ?? 0} color="#b5d7de" />
          </div>

          <div style={{ marginTop: '16px', border: '1px solid #183e46', borderRadius: '10px', padding: '13px 15px', background: '#07181d' }}>
            <div style={{ color: '#63c6d8', fontSize: '10px', letterSpacing: '2px', marginBottom: '7px' }}>LIVE EVIDENCE DIAGNOSTICS</div>
            <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', color: '#9eb9bf', fontSize: '11px' }}>
              <span>SEC: <strong style={{ color: statusColor(diagnostics?.sec_company) }}>{diagnostics?.sec_company ?? '—'}</strong> · {diagnostics?.sec_filings ?? 0} filings</span>
              <span>Price history: <strong style={{ color: statusColor(diagnostics?.alpha_vantage_history) }}>{diagnostics?.alpha_vantage_history ?? '—'}</strong></span>
              <span>Overview: <strong style={{ color: statusColor(diagnostics?.alpha_vantage_overview) }}>{diagnostics?.alpha_vantage_overview ?? '—'}</strong></span>
              <span>Earnings: <strong style={{ color: statusColor(diagnostics?.alpha_vantage_earnings) }}>{diagnostics?.alpha_vantage_earnings ?? '—'}</strong></span>
              <span>Calendar: <strong style={{ color: statusColor(diagnostics?.alpha_vantage_earnings_calendar) }}>{diagnostics?.alpha_vantage_earnings_calendar ?? '—'}</strong></span>
              <span>AV Macro: <strong>{diagnostics?.alpha_vantage_macro ? Object.values(diagnostics.alpha_vantage_macro).join(' · ') : '—'}</strong></span>
              <span>Archive matches: <strong>{diagnostics?.archive_matches ?? 0}</strong></span>
              <span>FRED: <strong>{diagnostics?.fred ? Object.values(diagnostics.fred).join(' · ') : '—'}</strong></span>
            </div>
          </div>

          <div style={{ marginTop: '18px' }}>
            <div style={{ color: '#63c6d8', fontSize: '10px', letterSpacing: '3px', marginBottom: '10px' }}>EIGHT INDEPENDENT REVIEWS</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(285px, 1fr))', gap: '10px' }}>
              {result.agent_reviews.map((review) => (
                <div key={review.agent_id} style={{ border: `1px solid ${stanceColor(review.stance)}55`, background: '#081318', borderRadius: '10px', padding: '14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'start' }}>
                    <strong style={{ fontSize: '12px' }}>{review.agent_name}</strong>
                    <span style={{ color: stanceColor(review.stance), fontSize: '10px', fontWeight: 900, letterSpacing: '1px' }}>{review.stance} · {Math.round((review.confidence ?? 0) * 100)}%</span>
                  </div>
                  <div style={{ color: '#c6d7db', fontSize: '12px', marginTop: '7px', fontWeight: 700 }}>{review.headline}</div>
                  <div style={{ color: '#8fa5aa', fontSize: '11px', marginTop: '6px', lineHeight: 1.45 }}>{review.view}</div>
                  {(review.risks ?? []).slice(0, 2).map((item, index) => <div key={`risk-${index}`} style={{ color: '#d899a5', fontSize: '10px', marginTop: '5px' }}>Risk: {item}</div>)}
                  {(review.missing_evidence ?? []).slice(0, 2).map((item, index) => <div key={`missing-${index}`} style={{ color: '#b8a36e', fontSize: '10px', marginTop: '4px' }}>Missing: {item}</div>)}
                  {review.error && <div style={{ color: '#ef8092', fontSize: '10px', marginTop: '5px', fontWeight: 800 }}>AGENT EXECUTION ERROR</div>}
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '18px' }}>
            <DecisionCard title="COUNCIL CHAIR" decision={result.council_chair.decision} confidence={result.council_chair.confidence} headline={result.council_chair.headline} body={result.council_chair.summary} details={[
              result.council_chair.strongest_support ? `Support: ${result.council_chair.strongest_support}` : '',
              result.council_chair.strongest_objection ? `Objection: ${result.council_chair.strongest_objection}` : '',
              ...(result.council_chair.unresolved_disagreements ?? []).slice(0, 2).map((item) => `Disagreement: ${item}`),
            ].filter(Boolean)} />
            <DecisionCard title="RISK GATE" decision={result.risk_gate.decision} confidence={result.risk_gate.confidence} headline={result.risk_gate.headline} body={result.risk_gate.liquidity_assessment} details={[
              ...(result.risk_gate.primary_risks ?? []).slice(0, 2).map((item) => `Risk: ${item}`),
              ...(result.risk_gate.hard_vetoes ?? []).slice(0, 2).map((item) => `Veto: ${item}`),
            ]} />
          </div>

          <div style={{ marginTop: '14px', border: `1px solid ${result.paper_execution_eligible ? '#2d765f' : '#5a2731'}`, background: result.paper_execution_eligible ? '#081a14' : '#16090d', borderRadius: '10px', padding: '14px 16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
              <div>
                <div style={{ color: result.paper_execution_eligible ? '#70caa5' : '#ef8092', fontSize: '10px', letterSpacing: '2px', fontWeight: 900 }}>PAPER EXECUTION</div>
                <strong style={{ fontSize: '16px' }}>{result.paper_execution_eligible ? 'ELIGIBLE FOR HYPOTHETICAL PAPER ORDER' : 'NO PAPER ORDER'}</strong>
              </div>
              <div style={{ color: '#ef8092', fontWeight: 900, fontSize: '11px' }}>REAL NOTIONAL $0 · BROKER SENT NO</div>
            </div>
            {result.simulated_order ? (
              <div style={{ color: '#9fc8b8', fontSize: '12px', marginTop: '8px' }}>
                {result.simulated_order.asset} {result.simulated_order.side} · simulated ${Number(result.simulated_order.simulated_notional ?? 0).toLocaleString()} · {result.simulated_order.execution}
              </div>
            ) : (
              <div style={{ color: '#a47f88', fontSize: '12px', marginTop: '8px' }}>Council or Risk did not clear the setup. No hypothetical order was produced.</div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

const inputStyle = {
  minWidth: 0,
  background: '#050b0d',
  color: '#e8f3f5',
  border: '1px solid #244b54',
  borderRadius: '8px',
  padding: '10px 12px',
} as const

const textareaStyle = {
  ...inputStyle,
  resize: 'vertical' as const,
  fontFamily: 'inherit',
}

function Metric({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div style={{ border: '1px solid #193b43', borderRadius: '10px', padding: '12px 15px', background: '#071216' }}>
      <div style={{ color: '#6f9299', fontSize: '10px', letterSpacing: '2px' }}>{label}</div>
      <strong style={{ fontSize: '23px', color }}>{value}</strong>
    </div>
  )
}

function DecisionCard({ title, decision, confidence, headline, body, details }: { title: string; decision?: string; confidence?: number; headline?: string; body?: string; details: string[] }) {
  return (
    <div style={{ border: '1px solid #234650', background: '#081318', borderRadius: '10px', padding: '15px' }}>
      <div style={{ color: '#6f9299', fontSize: '10px', letterSpacing: '2px' }}>{title}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', marginTop: '5px' }}>
        <strong style={{ color: decisionColor(decision), fontSize: '14px' }}>{decision ?? '—'}</strong>
        <span style={{ color: '#8da6ac', fontSize: '11px' }}>{typeof confidence === 'number' ? `${Math.round(confidence * 100)}% confidence` : ''}</span>
      </div>
      <div style={{ color: '#d2e1e4', fontSize: '12px', marginTop: '8px', fontWeight: 700 }}>{headline}</div>
      {body && <div style={{ color: '#91a8ad', fontSize: '11px', lineHeight: 1.45, marginTop: '6px' }}>{body}</div>}
      {details.filter(Boolean).slice(0, 4).map((detail, index) => <div key={index} style={{ color: '#9cabb0', fontSize: '10px', marginTop: '5px' }}>{detail}</div>)}
    </div>
  )
}

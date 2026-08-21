import { useCallback, useEffect, useState } from 'react'

const API_BASE = 'http://localhost:8000'

type Counts = { pending: number; running: number; complete: number; error: number }
type PostmortemJob = {
  job_id: string
  review_id: string
  status: string
  error?: string | null
  review?: { symbol?: string; outcome?: string; return_pct?: number; synthetic_fixture?: boolean }
  result?: { headline?: string; thesis_assessment?: string; confidence?: number; synthetic_fixture?: boolean } | null
}
type Pattern = {
  pattern_id: string
  symbol: string
  outcome: string
  return_pct: number
  headline: string
  tags: string[]
  synthetic_fixture: boolean
  lesson: {
    thesis_assessment?: string
    outcome_interpretation?: string
    reusable_patterns?: string[]
    anti_patterns?: string[]
    next_time_rules?: string[]
    causal_unknowns?: string[]
    confidence?: number
  }
}

export default function PostmortemPanel() {
  const [counts, setCounts] = useState<Counts>({ pending: 0, running: 0, complete: 0, error: 0 })
  const [jobs, setJobs] = useState<PostmortemJob[]>([])
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (search = query) => {
    try {
      const [jobsResponse, patternsResponse] = await Promise.all([
        fetch(`${API_BASE}/intelligence/feeds/postmortems?limit=10`),
        fetch(`${API_BASE}/intelligence/feeds/pattern-library?q=${encodeURIComponent(search)}&limit=20`),
      ])
      if (!jobsResponse.ok) throw new Error(`Postmortems HTTP ${jobsResponse.status}`)
      if (!patternsResponse.ok) throw new Error(`Patterns HTTP ${patternsResponse.status}`)
      const jobsPayload = await jobsResponse.json()
      const patternsPayload = await patternsResponse.json()
      setCounts(jobsPayload.counts as Counts)
      setJobs((jobsPayload.items ?? []) as PostmortemJob[])
      setPatterns((patternsPayload.items ?? []) as Pattern[])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Postmortem intelligence unavailable')
    }
  }, [query])

  useEffect(() => {
    void refresh('')
    const timer = window.setInterval(() => void refresh(query), 5000)
    return () => window.clearInterval(timer)
  }, [refresh, query])

  return (
    <section style={{ border: '1px solid #65478a', background: '#0d0914', borderRadius: '16px', padding: '24px', marginBottom: '26px', color: '#eef6ff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ color: '#b38ee7', fontSize: '11px', letterSpacing: '4px' }}>POSTMORTEM INTELLIGENCE // PATTERN LIBRARY</div>
          <h2 style={{ margin: '7px 0 6px', fontSize: '25px' }}>History Agent Learning</h2>
          <div style={{ color: '#9585a8', fontSize: '13px' }}>Closed paper outcomes become structured lessons, not hindsight folklore.</div>
        </div>
        <div style={{ border: '1px solid #6e3440', background: '#190a0f', color: '#ef8092', borderRadius: '8px', padding: '10px 14px', fontWeight: 800, letterSpacing: '2px', fontSize: '11px' }}>REAL CAPITAL $0</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(125px, 1fr))', gap: '10px', marginTop: '18px' }}>
        {[['PENDING', counts.pending], ['RUNNING', counts.running], ['LEARNED', counts.complete], ['ERROR', counts.error]].map(([label, value]) => (
          <div key={String(label)} style={{ border: '1px solid #342746', borderRadius: '10px', padding: '12px 15px' }}>
            <div style={{ color: '#847398', fontSize: '10px', letterSpacing: '2px' }}>{label}</div>
            <strong style={{ fontSize: '23px' }}>{value}</strong>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: '10px', marginTop: '16px', flexWrap: 'wrap' }}>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter') void refresh(query) }}
          placeholder="Search patterns: IPO, liquidity, synthetic, loss..."
          style={{ flex: '1 1 300px', minWidth: 0, background: '#08060c', color: '#e8def6', border: '1px solid #3e3052', borderRadius: '8px', padding: '10px 12px' }}
        />
        <button type="button" onClick={() => void refresh(query)} style={{ border: '1px solid #65478a', background: '#171022', color: '#c3a4ee', borderRadius: '8px', padding: '10px 15px', fontWeight: 800 }}>SEARCH LIBRARY</button>
      </div>

      {error && <div style={{ marginTop: '14px', color: '#e68191' }}>{error}</div>}

      <div style={{ marginTop: '18px', borderTop: '1px solid #31243f', paddingTop: '14px' }}>
        <div style={{ color: '#b38ee7', fontSize: '10px', letterSpacing: '3px', marginBottom: '8px' }}>RECENT HISTORY REVIEWS</div>
        {jobs.length === 0 ? <div style={{ color: '#7f718d', fontSize: '13px' }}>No postmortem jobs yet.</div> : jobs.slice(0, 5).map((job) => (
          <div key={job.job_id} style={{ padding: '10px 0', borderBottom: '1px solid #251c30', display: 'grid', gridTemplateColumns: '1fr auto', gap: '12px' }}>
            <div>
              <strong style={{ fontSize: '12px' }}>{job.result?.headline ?? `${job.review?.symbol ?? 'Outcome'} postmortem`}</strong>
              <div style={{ color: '#877a95', fontSize: '11px', marginTop: '4px' }}>
                {job.review?.outcome ?? '—'} · {typeof job.review?.return_pct === 'number' ? `${job.review.return_pct >= 0 ? '+' : ''}${job.review.return_pct.toFixed(2)}%` : '—'} · {job.result?.thesis_assessment ?? 'awaiting analysis'}
              </div>
              {(job.review?.synthetic_fixture || job.result?.synthetic_fixture) && <div style={{ color: '#d8ad59', fontSize: '10px', marginTop: '4px', fontWeight: 800 }}>SYNTHETIC PROCESS-LEARNING ONLY</div>}
              {job.error && <div style={{ color: '#e68191', fontSize: '11px', marginTop: '4px' }}>{job.error}</div>}
            </div>
            <span style={{ color: job.status === 'complete' ? '#70caa5' : job.status === 'error' ? '#e68191' : '#d8ad59', fontSize: '10px', fontWeight: 800 }}>{job.status.toUpperCase()}</span>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '18px', borderTop: '1px solid #31243f', paddingTop: '14px' }}>
        <div style={{ color: '#b38ee7', fontSize: '10px', letterSpacing: '3px', marginBottom: '8px' }}>SEARCHABLE PATTERN LIBRARY</div>
        {patterns.length === 0 ? <div style={{ color: '#7f718d', fontSize: '13px' }}>No learned patterns match this search yet.</div> : patterns.slice(0, 8).map((pattern) => (
          <div key={pattern.pattern_id} style={{ padding: '13px 0', borderBottom: '1px solid #251c30' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
              <strong style={{ fontSize: '13px' }}>{pattern.headline}</strong>
              <span style={{ color: pattern.return_pct >= 0 ? '#70caa5' : '#e68191', fontSize: '11px', fontWeight: 800 }}>{pattern.symbol} · {pattern.outcome} · {pattern.return_pct >= 0 ? '+' : ''}{pattern.return_pct.toFixed(2)}%</span>
            </div>
            <div style={{ color: '#9688a4', fontSize: '11px', marginTop: '5px' }}>{pattern.lesson?.outcome_interpretation}</div>
            {pattern.synthetic_fixture && <div style={{ color: '#d8ad59', fontSize: '10px', marginTop: '5px', fontWeight: 800 }}>SYNTHETIC: NO REAL-MARKET INFERENCE</div>}
            {(pattern.lesson?.reusable_patterns ?? []).slice(0, 2).map((item, index) => <div key={index} style={{ color: '#b8a9c7', fontSize: '11px', marginTop: '4px' }}>Pattern: {item}</div>)}
            {(pattern.lesson?.next_time_rules ?? []).slice(0, 2).map((item, index) => <div key={`rule-${index}`} style={{ color: '#9ab3c6', fontSize: '11px', marginTop: '4px' }}>Next time: {item}</div>)}
            <div style={{ color: '#736680', fontSize: '10px', marginTop: '6px' }}>Tags: {(pattern.tags ?? []).join(' · ')} · confidence {Math.round((pattern.lesson?.confidence ?? 0) * 100)}%</div>
          </div>
        ))}
      </div>
    </section>
  )
}

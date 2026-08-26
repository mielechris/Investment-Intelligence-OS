import { useCallback, useEffect, useMemo, useState } from "react";

const API = "http://127.0.0.1:8002";

type Scorecard = { agent_key: string; agent?: string; observations: number; accuracy?: number | null; average_confidence?: number; average_calibration_score?: number };
type State = { scorecards: Scorecard[]; online: boolean };

export default function JudgmentCommandCard() {
  const [state, setState] = useState<State>({ scorecards: [], online: false });
  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API}/judgment-bank/scorecards/all`);
      if (!response.ok) throw new Error("Judgment telemetry unavailable");
      const data = await response.json() as { scorecards?: Scorecard[] };
      setState({ scorecards: data.scorecards || [], online: true });
    } catch { setState((current) => ({ ...current, online: false })); }
  }, []);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 15000); return () => window.clearInterval(timer); }, [load]);

  const totalObservations = state.scorecards.reduce((sum, item) => sum + Number(item.observations || 0), 0);
  const calibrated = state.scorecards.filter((item) => Number(item.observations || 0) > 0).length;
  const best = useMemo(() => [...state.scorecards].filter((item) => item.average_calibration_score != null).sort((a, b) => Number(b.average_calibration_score || 0) - Number(a.average_calibration_score || 0))[0], [state.scorecards]);
  const pct = (value?: number | null) => value == null ? "—" : `${Math.round(value * 100)}%`;

  return (
    <section className="judgment-command-card">
      <div className="judgment-command-head"><div><div className="judgment-command-eyebrow">JUDGMENT COMMAND</div><h2>Human Intelligence & Calibration</h2><p>Professional judgment is captured with provenance, restriction screening, human approval, and post-outcome calibration.</p></div><div className={state.online ? "judgment-command-live" : "judgment-command-offline"}>{state.online ? "JUDGMENT ONLINE" : "JUDGMENT OFFLINE"}</div></div>
      <div className="judgment-command-metrics">
        <div><span>Agent Scorecards</span><strong>{state.scorecards.length}</strong></div>
        <div><span>Calibrated Agents</span><strong>{calibrated}</strong></div>
        <div><span>Outcomes</span><strong>{totalObservations}</strong></div>
        <div><span>Best Calibration</span><strong>{best ? pct(best.average_calibration_score) : "—"}</strong></div>
        <div><span>Publication Gate</span><strong className="judgment-lock">HUMAN APPROVAL</strong></div>
      </div>
      <div className="judgment-command-next"><span>CALIBRATION LEADER</span><strong>{best ? `${best.agent || best.agent_key} · ${pct(best.average_calibration_score)} calibration · ${best.observations} outcomes` : "No calibrated outcomes yet. Interview capture remains available below."}</strong></div>
    </section>
  );
}

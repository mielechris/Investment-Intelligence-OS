import { useCallback, useEffect, useMemo, useState } from "react";

const API = "http://127.0.0.1:8002";

type Scorecard = {
  agent_key: string;
  agent?: string;
  observations: number;
  accuracy?: number | null;
  average_confidence?: number | null;
  average_calibration_score?: number | null;
};

type PortalStatus = {
  human_approval_required?: boolean;
  mnpi_screening?: boolean;
  auto_publish_to_trade_evidence?: boolean;
  paper_mode?: boolean;
};

type State = { scorecards: Scorecard[]; portal: PortalStatus | null; online: boolean };

const pct = (value?: number | null) => value == null ? "—" : `${Math.round(value * 100)}%`;

function calibrationBand(value?: number | null) {
  if (value == null) return "UNOBSERVED";
  if (value >= .8) return "STRONG";
  if (value >= .6) return "DEVELOPING";
  return "WEAK";
}

export default function JudgmentBankWorkspace() {
  const [state, setState] = useState<State>({ scorecards: [], portal: null, online: false });

  const load = useCallback(async () => {
    try {
      const [scoresResponse, portalResponse] = await Promise.all([
        fetch(`${API}/judgment-bank/scorecards/all`),
        fetch(`${API}/interview-portal/status`),
      ]);
      if (!scoresResponse.ok || !portalResponse.ok) throw new Error("Judgment Bank state unavailable");
      const scores = await scoresResponse.json() as { scorecards?: Scorecard[] };
      const portal = await portalResponse.json() as PortalStatus;
      setState({ scorecards: scores.scorecards || [], portal, online: true });
    } catch {
      setState((current) => ({ ...current, online: false }));
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  const ranked = useMemo(() => [...state.scorecards].sort((a, b) => Number(b.average_calibration_score ?? -1) - Number(a.average_calibration_score ?? -1)), [state.scorecards]);
  const observed = ranked.filter((item) => Number(item.observations || 0) > 0);
  const totalOutcomes = observed.reduce((sum, item) => sum + Number(item.observations || 0), 0);

  return (
    <section className="judgment-bank-workspace">
      <div className="judgment-bank-workspace-head">
        <div>
          <div className="judgment-bank-workspace-eyebrow">X4 · JUDGMENT BANK</div>
          <h2>Calibration & Human Approval Ledger</h2>
          <p>Agent judgment is measured against outcomes. Professional interview insight remains provenance-bound and cannot enter the bank without human approval.</p>
        </div>
        <div className={state.online ? "judgment-bank-workspace-live" : "judgment-bank-workspace-offline"}>{state.online ? "LEDGER LIVE" : "LEDGER OFFLINE"}</div>
      </div>

      <div className="judgment-bank-flow">
        <div><span>1</span><strong>INTERVIEW</strong><small>Public / non-confidential professional judgment</small></div>
        <div><span>2</span><strong>EXTRACT</strong><small>Transcript-supported insight + provenance</small></div>
        <div><span>3</span><strong>SCREEN</strong><small>{state.portal?.mnpi_screening ? "Restriction screening armed" : "Screening state unknown"}</small></div>
        <div><span>4</span><strong>HUMAN APPROVAL</strong><small>{state.portal?.human_approval_required ? "Mandatory gate" : "Gate state unknown"}</small></div>
        <div><span>5</span><strong>CALIBRATE</strong><small>{totalOutcomes} observed outcomes</small></div>
      </div>

      <div className="judgment-bank-table-wrap">
        <table>
          <thead><tr><th>AGENT</th><th>OUTCOMES</th><th>ACCURACY</th><th>AVG CONFIDENCE</th><th>CALIBRATION</th><th>BAND</th></tr></thead>
          <tbody>
            {ranked.map((item) => (
              <tr key={item.agent_key}>
                <td><strong>{item.agent || item.agent_key}</strong><small>{item.agent_key}</small></td>
                <td>{item.observations || 0}</td>
                <td>{pct(item.accuracy)}</td>
                <td>{pct(item.average_confidence)}</td>
                <td>{pct(item.average_calibration_score)}</td>
                <td><span className={`judgment-calibration-band judgment-calibration-band--${calibrationBand(item.average_calibration_score).toLowerCase()}`}>{calibrationBand(item.average_calibration_score)}</span></td>
              </tr>
            ))}
            {!ranked.length && <tr><td colSpan={6}>No scorecards have been written yet.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="judgment-bank-safety">
        <span>PUBLICATION AUTHORITY</span>
        <strong>{state.portal?.auto_publish_to_trade_evidence === false ? "NO AUTO-PUBLISH · HUMAN REVIEW REQUIRED" : "AUTHORITY STATE UNKNOWN"}</strong>
      </div>
    </section>
  );
}

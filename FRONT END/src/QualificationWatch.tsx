import { useEffect, useMemo, useState } from "react";
import "./QualificationWatch.css";

type Gate = { gate?: string; state?: string; observed?: unknown; required?: string; progress_pct?: number; remaining?: number | null };
type Watch = {
  status?: string;
  phase?: string;
  qualification_status?: string;
  capital_readiness_status?: string;
  qualification_progress_pct?: number;
  sample_ready?: boolean;
  progress?: Gate[];
  unresolved_readiness_gate_count?: number;
  unresolved_readiness_gates?: string[];
  next_action?: string;
};

function text(value: unknown, fallback = "—") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}

async function load(signal?: AbortSignal): Promise<Watch> {
  const response = await fetch(`/qualification_watch.json?ts=${Date.now()}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`Qualification Watch HTTP ${response.status}`);
  return response.json() as Promise<Watch>;
}

export default function QualificationWatch() {
  const [watch, setWatch] = useState<Watch | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      const controller = new AbortController();
      try { const next = await load(controller.signal); if (!disposed) { setWatch(next); setError(null); } }
      catch (reason) { if (!disposed) setError(reason instanceof Error ? reason.message : "Qualification Watch unavailable"); }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);
  const rows = useMemo(() => watch?.progress ?? [], [watch]);
  if (!watch) return <section className="qw-shell"><span>BATCH 10G · QUALIFICATION WATCH</span><h2>READING THE EVIDENCE CLOCK</h2><p>{error ?? "Waiting for 10B and 10E persisted artifacts."}</p></section>;
  return (
    <section className="qw-shell">
      <div className="qw-hero">
        <div><span>BATCH 10G · QUALIFICATION WATCH</span><h2>The build is done. Now the evidence has to earn it.</h2><p>10G tracks the governed paper-qualification campaign. It cannot manufacture trades, accelerate the sample, connect a broker, fund capital, or approve live execution.</p></div>
        <div className="qw-guard"><strong>{text(watch.phase).replaceAll("_", " ")}</strong><span>WATCH ONLY</span><em>LIVE EXECUTION FALSE</em></div>
      </div>
      <div className="qw-safety"><span>AUTO TRADE · FALSE</span><span>AUTO BROKER · FALSE</span><span>AUTO FUND · FALSE</span><span>CAPITAL AUTHORITY · FALSE</span></div>
      <div className="qw-score"><article><span>QUALIFICATION PROGRESS</span><strong>{text(watch.qualification_progress_pct, "0")}%</strong></article><article><span>10B STATUS</span><strong>{text(watch.qualification_status).replaceAll("_", " ")}</strong></article><article><span>10E STATUS</span><strong>{text(watch.capital_readiness_status).replaceAll("_", " ")}</strong></article><article><span>UNRESOLVED READINESS GATES</span><strong>{text(watch.unresolved_readiness_gate_count, "0")}</strong></article></div>
      <section className="qw-panel"><div className="qw-title"><div><span>PAPER QUALIFICATION CAMPAIGN</span><h3>Evidence remaining</h3></div><strong>NEXT · {text(watch.next_action).replaceAll("_", " ")}</strong></div><div className="qw-grid">{rows.map((row) => <article key={text(row.gate)}><header><strong>{text(row.gate).replaceAll("_", " ")}</strong><span>{text(row.state)}</span></header><div className="qw-bar"><i style={{ width: `${Math.max(0, Math.min(100, row.progress_pct ?? 0))}%` }} /></div><p>{text(row.observed)} observed · {text(row.required)} required</p>{typeof row.remaining === "number" ? <em>{row.remaining} remaining</em> : null}</article>)}</div></section>
      <section className="qw-panel"><div className="qw-title"><div><span>READINESS GATES</span><h3>What engineering cannot self-approve</h3></div></div><div className="qw-gates">{(watch.unresolved_readiness_gates ?? []).map((gate) => <span key={gate}>{gate.replaceAll("_", " ")}</span>)}</div></section>
      <div className="qw-footer"><span>ENGINEERING · COMPLETE</span><span>PAPER QUALIFICATION · EVIDENCE-DRIVEN</span><span>LIVE CAPITAL · HUMAN GATED</span><span>LIVE EXECUTION · FALSE</span></div>
      {error ? <div className="qw-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}

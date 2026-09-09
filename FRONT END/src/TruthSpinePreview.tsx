import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { validateProjection, projectionSelection, type Projection } from "./truthSpineProjection";
import "./TruthSpinePreview.css";

export function TruthSpinePreview() {
  const [snapshot, setSnapshot] = useState<Projection | null>(null);
  const selected = useRef<string | null>(null);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await fetch("/truth-spine/projection", { signal: controller.signal, credentials: "omit", cache: "no-store" });
        if (!response.ok) throw new Error("UNAVAILABLE");
        const next = await validateProjection(await response.json(), selected.current);
        if (!stopped) { selected.current = projectionSelection(next); setSnapshot(next); }
      } catch { if (!stopped) setSnapshot(null); }
      if (!stopped) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, []);
  return <main><header><p>IIOS · CANONICAL TRUTH SPINE</p><h1>Isolated evidence replay</h1><strong>REPLAY — NOT LIVE INVESTMENT RESEARCH</strong><p>Deterministic acceptance models. No provider access. No order authority.</p></header>
    {!snapshot ? <section role="status"><h2>UNAVAILABLE</h2><p>No current, hash-valid, coherent replay projection is available.</p></section> : <>
      <section aria-label="Decision"><h2>{snapshot.case_state}</h2><p>{snapshot.reason_codes.join(" · ")}</p><p>Session: {snapshot.phase} · Research: offline replay only · Market: disabled, zero allowance</p><p>Authority locked — broker, paper-order, promotion, ledger-write and live execution: false</p></section>
      <div className="truth-grid"><section><h2>Governed chain</h2><dl><dt>Committee</dt><dd>{snapshot.committee_state}</dd><dt>Risk</dt><dd>{snapshot.risk.decision}</dd><dt>Paper</dt><dd>{snapshot.paper.state} · Orders {snapshot.paper.orders}</dd><dt>Outcome</dt><dd>{snapshot.outcome.state}</dd><dt>Memory</dt><dd>{snapshot.memory.state}</dd></dl></section>
      <section><h2>Evidence provenance</h2><p>Existing licensed evidence; no new transmission.</p><dl><dt>Evidence</dt><dd>{snapshot.evidence_ids.join(", ")}</dd><dt>Receipt</dt><dd>{snapshot.receipt_id}</dd><dt>Trace</dt><dd>{snapshot.trace_id}</dd></dl></section>
      <section><h2>Agent routing</h2><ul>{Object.entries(snapshot.agent_states).map(([key, agent]) => <li key={key}>{agent.name}: {agent.invoked ? "REPLAY assessment" : "Not invoked"} — {agent.reason}</li>)}</ul></section>
      <section><h2>Paper fund reference</h2><p>Not a broker reconciliation or deployable comparison balance.</p><dl><dt>NAV / cash</dt><dd>{snapshot.paper_fund.nav ?? "UNAVAILABLE"} / {snapshot.paper_fund.cash ?? "UNAVAILABLE"}</dd><dt>Source</dt><dd>{snapshot.paper_fund.source}</dd><dt>Reconciled at</dt><dd>{snapshot.paper_fund.reconciled_at ?? "UNAVAILABLE"}</dd></dl></section></div>
      <details><summary>Canonical runtime and persisted events</summary><dl>{["release_id", "runtime_id", "ledger_identity", "generation_id", "topology_identity", "observed_at"].map(key => <div key={key}><dt>{key}</dt><dd>{String(snapshot[key as keyof Projection])}</dd></div>)}</dl><ol>{snapshot.event_ids.map(id => <li key={id}>{id}</li>)}</ol></details>
    </>}
  </main>;
}
createRoot(document.getElementById("root")!).render(<TruthSpinePreview />);

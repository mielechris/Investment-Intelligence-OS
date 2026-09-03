import { useEffect, useMemo, useState } from "react";
import "./ExpansionWing.css";

type TruthState = "AVAILABLE" | "CURRENT" | "STALE" | "INCOMPLETE" | "UNAVAILABLE" | "UNKNOWN";
type Section = { state: TruthState; data: unknown };
type WingStatus = { schema_version: string; mode?: string; sections: Record<string, Section>; authority: Record<string, boolean> };
type Room = { title: string; section: string; description: string };

const LIVE_READ_ONLY = import.meta.env.VITE_EXPANSION_WING_LIVE_READONLY === "1" && import.meta.env.VITE_BACKEND_RECOVERY_GREEN === "1";
const FIXTURE_MODE = !LIVE_READ_ONLY;
const ENDPOINT = FIXTURE_MODE ? "/fixtures/expansion-wing.json" : "http://127.0.0.1:8002/expansion-wing/status";
const ROOMS: Room[] = [
  { title: "Interview Studio", section: "cases", description: "Consent, transcript approval, and human review." },
  { title: "Investor Archive", section: "cases", description: "Attributable notes and limited quotations." },
  { title: "Philosophy Arena", section: "outcomes_9j", description: "Contrasting principles and failure cases." },
  { title: "Judgment Foundry", section: "outcomes_9j", description: "Reported through retired judgment lifecycle." },
  { title: "Pattern Laboratory", section: "shadow_9i", description: "Point-in-time walk-forward evidence." },
  { title: "Strictness Observatory", section: "shadow_9i", description: "Read-only governed policy counterfactuals." },
  { title: "Cross-Asset Observatory", section: "radar", description: "Common Opportunity Passports and asset gates." },
  { title: "Regime Chamber", section: "last_cycle", description: "Ten-dimension regime state and freshness." },
  { title: "Tactical Book", section: "books", description: "$3,000 maximum paper allocation." },
  { title: "Strategic Book", section: "books", description: "$5,000 maximum paper allocation." },
  { title: "Capital Allocation Room", section: "books", description: "Risk-aware paper allocation comparison." },
  { title: "Failure Museum", section: "benchmark_9h", description: "Misses, counterexamples, and drawdowns." },
  { title: "Strategy Incubator", section: "queue", description: "Governed provisional research only." },
  { title: "Learning Theater", section: "resources", description: "Owner reports, maturity, and approval inbox." },
];
const labels: Record<string, string> = {service_health:"Service health",last_cycle:"Last cycle",radar:"Radar flow",cases:"Governed cases",committee:"Committee",risk:"Risk",books:"Dual books",benchmark_9h:"9H benchmark",shadow_9i:"9I strictness",outcomes_9j:"9J outcomes",resources:"Resources",queue:"Queue"};

export default function ExpansionWing() {
  const [status, setStatus] = useState<WingStatus | null>(null);
  const [connection, setConnection] = useState<TruthState>("UNKNOWN");
  const [selected, setSelected] = useState<Room | null>(null);
  useEffect(() => {
    let live = true;
    const load = async () => { try { const response = await fetch(ENDPOINT); if (!response.ok) throw new Error(String(response.status)); const payload = await response.json() as WingStatus; if (live) { setStatus(payload); setConnection("CURRENT"); } } catch { if (live) { setStatus(null); setConnection("UNAVAILABLE"); } } };
    const initial = window.setTimeout(() => void load(), 0); const timer = window.setInterval(() => void load(), 15_000);
    return () => { live = false; window.clearTimeout(initial); window.clearInterval(timer); };
  }, []);
  useEffect(() => { if (!selected) return; const close = (event: KeyboardEvent) => { if (event.key === "Escape") setSelected(null); }; window.addEventListener("keydown", close); return () => window.removeEventListener("keydown", close); }, [selected]);
  const selectedSection = useMemo(() => selected ? status?.sections[selected.section] : undefined, [selected, status]);
  return <section className="expansion-wing" aria-labelledby="expansion-wing-title" data-mode={FIXTURE_MODE ? "fixture" : "read-only-live"}>
    <header><div><span>READ-ONLY OPERATIONS</span><h2 id="expansion-wing-title">Expansion Wing</h2></div><div className="wing-badges">{FIXTURE_MODE ? <strong className="wing-fixture">FIXTURE / NON-LIVE</strong> : null}<strong className={`wing-state wing-state--${connection.toLowerCase()}`}>{connection}</strong></div></header>
    <p className="wing-boundary">Paper simulation only · no credentials · no raw logs · no ledger writes · no broker or live-capital authority</p>
    <div className="wing-truth-grid" aria-label="Expansion Wing truth states">{Object.entries(labels).map(([key,label]) => { const state=status?.sections[key]?.state??"UNAVAILABLE"; return <article key={key}><span>{label}</span><strong className={`wing-state wing-state--${state.toLowerCase()}`}>{state}</strong></article>; })}</div>
    <div className="wing-rooms" aria-label="Expansion Wing room registry">{ROOMS.map((room) => { const state=status?.sections[room.section]?.state??"UNAVAILABLE"; return <button type="button" key={room.title} onClick={()=>setSelected(room)} aria-label={`Open ${room.title}, ${state}`}><span className={`wing-state wing-state--${state.toLowerCase()}`}>{state}</span><h3>{room.title}</h3><p>{room.description}</p></button>; })}</div>
    {selected ? <div className="wing-modal-backdrop" role="presentation" onMouseDown={()=>setSelected(null)}><div className="wing-modal" role="dialog" aria-modal="true" aria-labelledby="wing-dialog-title" onMouseDown={(event)=>event.stopPropagation()}><button type="button" className="wing-close" onClick={()=>setSelected(null)} aria-label="Close room dialog">×</button><span className={`wing-state wing-state--${(selectedSection?.state??"UNAVAILABLE").toLowerCase()}`}>{selectedSection?.state??"UNAVAILABLE"}</span><h3 id="wing-dialog-title">{selected.title}</h3><p>{selected.description}</p><pre>{selectedSection?.data==null?"No sanitized evidence available.":JSON.stringify(selectedSection.data,null,2)}</pre></div></div> : null}
  </section>;
}

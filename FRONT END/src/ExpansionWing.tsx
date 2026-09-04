import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./ExpansionWing.css";
import "./ExpansionWingStates.css";
import { useExpansionWingSnapshot } from "./ExpansionWingSnapshotContext";

type Room = { title: string; section: string; description: string };
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
  { title: "Resource Governor", section: "knowledge_operations", description: "Disabled acquisition, cost, queue, and authority boundaries." },
  { title: "Learning Theater", section: "resources", description: "Owner reports, maturity, and approval inbox." },
];
const labels: Record<string, string> = {service_health:"Service health",last_cycle:"Last cycle",radar:"Radar flow",cases:"Governed cases",committee:"Committee",risk:"Risk",books:"Dual books",benchmark_9h:"9H benchmark",shadow_9i:"9I shadow",outcomes_9j:"9J outcomes",resources:"Resources",queue:"Queue",knowledge_operations:"Knowledge security"};
const compactStatus: Record<string, string> = { AVAILABLE_FOR_REVIEWED_UPLOAD: "UPLOAD READY" };

export default function ExpansionWing() {
  const { snapshot: status, connection, fixtureMode: FIXTURE_MODE, snapshotAgeSeconds } = useExpansionWingSnapshot();
  const [selected, setSelected] = useState<Room | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<HTMLButtonElement | null>(null);
  const closeDialog = useCallback(() => { setSelected(null); window.requestAnimationFrame(() => openerRef.current?.focus()); }, []);
  useEffect(() => {
    if (!selected) return;
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeDialog(); return; }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", keydown); return () => window.removeEventListener("keydown", keydown);
  }, [selected, closeDialog]);
  const selectedSection = useMemo(() => selected ? status?.sections[selected.section] : undefined, [selected, status]);
  const selectedRoom = selected ? status?.room_states?.[selected.title] : undefined;
  return <section className="expansion-wing" aria-labelledby="expansion-wing-title" data-mode={FIXTURE_MODE ? "fixture" : "read-only-live"}>
    <header><div><span>READ-ONLY OPERATIONS</span><h2 id="expansion-wing-title">Expansion Wing</h2></div><div className="wing-badges">{FIXTURE_MODE ? <strong className="wing-fixture">FIXTURE / NON-LIVE</strong> : null}{snapshotAgeSeconds !== null ? <span>Snapshot age {snapshotAgeSeconds}s</span> : null}<strong className={`wing-state wing-state--${connection.toLowerCase()}`}>{connection}</strong></div></header>
    <p className="wing-boundary">Paper simulation only · no credentials · no raw logs · no ledger writes · no broker or live-capital authority</p>
    <div className="wing-truth-grid" aria-label="Expansion Wing truth states">{Object.entries(labels).map(([key,label]) => { const state=status?.sections[key]?.state??"UNAVAILABLE"; return <article key={key}><span>{label}</span><strong className={`wing-state wing-state--${state.toLowerCase()}`}>{state}</strong></article>; })}</div>
    <div className="wing-rooms" aria-label="Expansion Wing room registry">{ROOMS.map((room) => { const core=status?.room_states?.[room.title]?.state??status?.sections[room.section]?.state??"UNAVAILABLE"; const state=status?.room_states?.[room.title]?.presentation_status??core; return <button type="button" key={room.title} onClick={(event)=>{openerRef.current=event.currentTarget;setSelected(room);}} aria-label={`Open ${room.title}, ${state}`}><span className={`wing-state wing-state--${state.toLowerCase()}`} aria-hidden="true">{compactStatus[state]??state}</span><h3>{room.title}</h3><p>{room.description}</p></button>; })}</div>
    {selected ? <div className="wing-modal-backdrop" role="presentation" onMouseDown={closeDialog}><div ref={dialogRef} className="wing-modal" role="dialog" aria-modal="true" aria-labelledby="wing-dialog-title" onMouseDown={(event)=>event.stopPropagation()}><button type="button" className="wing-close" onClick={closeDialog} aria-label="Close room dialog">×</button><span className={`wing-state wing-state--${(selectedRoom?.presentation_status??selectedSection?.state??"UNAVAILABLE").toLowerCase()}`}>{selectedRoom?.presentation_status??selectedSection?.state??"UNAVAILABLE"}</span><h3 id="wing-dialog-title">{selected.title}</h3><p>{selected.description}</p><pre>{(selectedRoom?.data??selectedSection?.data)==null?"No sanitized evidence available.":JSON.stringify(selectedRoom?.data??selectedSection?.data,null,2)}</pre></div></div> : null}
  </section>;
}

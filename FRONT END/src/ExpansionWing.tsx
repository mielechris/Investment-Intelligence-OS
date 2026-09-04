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
const labels: Record<string, string> = {service_health:"Service health",market_session:"Market session",projection_freshness:"Projection freshness",authority_lock:"Authority lock",last_cycle:"Last source cycle",radar:"Scanner state",candidate_conveyor:"Candidate conveyor",multi_asset_factory:"Multi-asset factory",professional_strategy_observatory:"Professional strategy observatory",method_manager_scoreboard:"Manager / method scoreboard",paper_research_sleeves:"Paper research sleeves",post_close_control:"Post-close control",governed_cases:"Governed cases",primary_source_review_queue:"Primary-source review",provider_credit_meter:"Provider / credit meter",cases:"Case system",committee:"Committee",risk:"Risk",books:"Dual books",benchmark_9h:"9H benchmark",shadow_9i:"9I shadow",outcomes_9j:"9J outcomes",resources:"Resources",queue:"Queue",knowledge_operations:"Knowledge security",candidate_enrichment:"Candidate enrichment"};
const compactStatus: Record<string, string> = { AVAILABLE_FOR_REVIEWED_UPLOAD: "UPLOAD READY" };
const MULTI_ASSET_LANES = ["us_equities","equity_etfs","treasury_rates","bond_proxies","commodity_proxies","fx_proxies","crypto_reference","listed_options","intraday","relative_value"];
type ConveyorRow = {candidate_id:string;instrument_id?:string;ticker?:string;asset_lane?:string;originating_scanner?:string;discovered_at?:string;source_cycle_id?:string;completeness?:string;missing_fields?:string[];verification_state?:string;promotion_state?:string;blocked_reason?:string};

function characterLines(session: string, conveyor: string) {
  const max = session === "MARKET_CLOSED_WEEKEND" ? "Markets are closed for the expected weekend; IIOS is preserving the last trustworthy timestamp." : session === "PRE_MARKET" ? "Tuesday is pre-market; IIOS is waiting for fresh current-session evidence." : session === "REGULAR_SESSION" ? "The regular session is open; every lane must prove current-session evidence independently." : "Session evidence is unavailable or outside regular hours.";
  const factory = conveyor === "AVAILABLE_EMPTY" ? "The scanner completed with no immutable candidates; zero is an observed result." : conveyor === "AVAILABLE" || conveyor === "CURRENT" ? "Immutable candidates are waiting for independent evidence and primary review." : conveyor === "FAILED_CLOSED" ? "The scanner failed closed; no historical candidates were substituted." : conveyor === "STALE" ? "Candidate evidence is stale and cannot represent the current session." : "Exact candidate lineage is unavailable; no identities are inferred.";
  return { max, factory };
}

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
  const multiData = status?.sections.multi_asset_factory?.data as {market_session_state?:string;lane_states?:Record<string,string|{state?:string;freshness?:string;candidate_count?:number|null;research_eligible?:boolean;paper_eligible?:boolean;missing_evidence?:string;instrument_basis?:string}>}|undefined;
  const conveyorState = status?.sections.candidate_conveyor?.state??"UNAVAILABLE";
  const commentary = characterLines(multiData?.market_session_state??"UNKNOWN", conveyorState);
  return <section className="expansion-wing" aria-labelledby="expansion-wing-title" data-mode={FIXTURE_MODE ? "fixture" : "read-only-live"}>
    <header><div><span>READ-ONLY OPERATIONS</span><h2 id="expansion-wing-title">Expansion Wing</h2></div><div className="wing-badges">{FIXTURE_MODE ? <strong className="wing-fixture">FIXTURE / NON-LIVE</strong> : null}{snapshotAgeSeconds !== null ? <span>Snapshot age {snapshotAgeSeconds}s</span> : null}<strong className={`wing-state wing-state--${connection.toLowerCase()}`}>{connection}</strong></div></header>
    <p className="wing-boundary">Paper simulation only · no credentials · no raw logs · no ledger writes · no broker or live-capital authority</p>
    <section className="wing-conveyor" aria-label="Candidate Conveyor">
      <div><span>9E</span><b aria-hidden="true">→</b><span>PRIMARY REVIEW</span><b aria-hidden="true">→</b><span>CASE DRAFT</span></div>
      <strong className={`wing-state wing-state--${(status?.sections.candidate_conveyor?.state??"UNAVAILABLE").toLowerCase()}`}>{status?.sections.candidate_conveyor?.state??"UNAVAILABLE"}</strong>
      {Array.isArray((status?.sections.candidate_conveyor?.data as {candidates?: unknown[]}|undefined)?.candidates) ? <ul>{((status?.sections.candidate_conveyor?.data as {candidates: ConveyorRow[]}).candidates).slice(0,5).map((row)=><li key={row.candidate_id}><div><b>{row.instrument_id??row.ticker??"UNKNOWN"}</b><span>{row.asset_lane??"UNKNOWN LANE"} · {row.completeness??"UNKNOWN"} · {row.verification_state??"UNAVAILABLE"}</span><span>{row.promotion_state??"BLOCKED"}: {row.blocked_reason??"EVIDENCE_REQUIRED"}</span></div><code>{row.candidate_id}<br/>{row.source_cycle_id??"NO SOURCE CYCLE"}</code></li>)}</ul> : null}
    </section>
    <section className="wing-lanes" aria-label="Multi-asset research lanes">
      <h3>Multi-Asset Research Factory</h3>
      <p>Independent research lanes · proxies remain explicitly distinct from underlying instruments</p>
      <div>{MULTI_ASSET_LANES.map((lane)=>{const detail=multiData?.lane_states?.[lane];const state=typeof detail==="string"?detail:detail?.state??"UNAVAILABLE";return <article key={lane}><span>{lane.replaceAll("_"," ")}</span><strong className={`wing-state wing-state--${state.toLowerCase()}`}>{state}</strong>{typeof detail==="object"?<small>{detail.instrument_basis??"UNKNOWN BASIS"} · {detail.freshness??"UNKNOWN"}<br/>Research {detail.research_eligible?"eligible":"blocked"} · Paper {detail.paper_eligible?"eligible":"blocked"}<br/>{detail.missing_evidence??"No missing evidence reported"}</small>:null}</article>;})}</div>
    </section>
    <section className="wing-characters" aria-label="Structured factory commentary"><article><b>MAX</b><p>{commentary.max}</p></article><article><b>FACTORY</b><p>{commentary.factory}</p></article></section>
    <section className="wing-observatory" aria-label="Professional strategy and paper research status">{["professional_strategy_observatory","method_manager_scoreboard","paper_research_sleeves"].map((key)=><article key={key}><h3>{labels[key]}</h3><strong className={`wing-state wing-state--${(status?.sections[key]?.state??"UNAVAILABLE").toLowerCase()}`}>{status?.sections[key]?.state??"UNAVAILABLE"}</strong><pre>{status?.sections[key]?.data==null?"No sanitized evidence available.":JSON.stringify(status.sections[key].data,null,2)}</pre></article>)}</section>
    <div className="wing-truth-grid" aria-label="Expansion Wing truth states">{Object.entries(labels).map(([key,label]) => { const state=status?.sections[key]?.state??"UNAVAILABLE"; return <article key={key}><span>{label}</span><strong className={`wing-state wing-state--${state.toLowerCase()}`}>{state}</strong></article>; })}</div>
    <div className="wing-rooms" aria-label="Expansion Wing room registry">{ROOMS.map((room) => { const core=status?.room_states?.[room.title]?.state??status?.sections[room.section]?.state??"UNAVAILABLE"; const state=status?.room_states?.[room.title]?.presentation_status??core; return <button type="button" key={room.title} onClick={(event)=>{openerRef.current=event.currentTarget;setSelected(room);}} aria-label={`Open ${room.title}, ${state}`}><span className={`wing-state wing-state--${state.toLowerCase()}`} aria-hidden="true">{compactStatus[state]??state}</span><h3>{room.title}</h3><p>{room.description}</p></button>; })}</div>
    {selected ? <div className="wing-modal-backdrop" role="presentation" onMouseDown={closeDialog}><div ref={dialogRef} className="wing-modal" role="dialog" aria-modal="true" aria-labelledby="wing-dialog-title" onMouseDown={(event)=>event.stopPropagation()}><button type="button" className="wing-close" onClick={closeDialog} aria-label="Close room dialog">×</button><span className={`wing-state wing-state--${(selectedRoom?.presentation_status??selectedSection?.state??"UNAVAILABLE").toLowerCase()}`}>{selectedRoom?.presentation_status??selectedSection?.state??"UNAVAILABLE"}</span><h3 id="wing-dialog-title">{selected.title}</h3><p>{selected.description}</p><pre>{(selectedRoom?.data??selectedSection?.data)==null?"No sanitized evidence available.":JSON.stringify(selectedRoom?.data??selectedSection?.data,null,2)}</pre></div></div> : null}
  </section>;
}

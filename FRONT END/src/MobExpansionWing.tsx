/* eslint-disable react-refresh/only-export-components -- exported registries and narration are deterministic test seams */
import { useMemo, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { useExpansionWingSnapshot, type ExpansionSnapshot, type TruthState } from "./ExpansionWingSnapshotContext";
import "./MobExpansionWing.css";

type RecordValue = Record<string, unknown>;
type DepartmentKey = "overview" | "trading" | "conveyor" | "observatory" | "laboratory" | "committee" | "risk" | "portfolio" | "learning" | "evidence" | "control";

export const UNIFIED_DEPARTMENTS: ReadonlyArray<{ key: DepartmentKey; label: string; code: string }> = [
  { key: "overview", label: "Expansion Wing", code: "EW" },
  { key: "trading", label: "Multi-Asset Trading Floor", code: "10D" },
  { key: "conveyor", label: "Candidate Conveyor", code: "9E+" },
  { key: "observatory", label: "Professional Strategy Observatory", code: "PRO" },
  { key: "laboratory", label: "Research Laboratory", code: "LAB" },
  { key: "committee", label: "Committee Room", code: "IC" },
  { key: "risk", label: "Risk Inspection", code: "RK" },
  { key: "portfolio", label: "Paper Portfolio Office", code: "P" },
  { key: "learning", label: "Outcome Learning Theater", code: "9J" },
  { key: "evidence", label: "Evidence Warehouse", code: "E" },
  { key: "control", label: "Control Room", code: "CTRL" },
];

export const MULTI_ASSET_LANES = [
  ["us_equities", "U.S. Equities", "DIRECT"], ["equity_etfs", "Equity ETFs", "DIRECT"],
  ["treasury_rates", "Treasury Rates", "EXPLICIT PROXY"], ["bond_proxies", "Bond Proxies", "EXPLICIT PROXY"],
  ["commodity_proxies", "Commodity Proxies", "EXPLICIT PROXY"], ["fx_proxies", "FX Proxies", "EXPLICIT PROXY"],
  ["crypto_reference", "Crypto Reference", "REFERENCE ONLY"], ["listed_options", "Listed Options", "DIRECT"],
  ["intraday", "Intraday", "DIRECT"], ["relative_value", "Relative Value", "EXPLICIT PROXY"],
] as const;

export const CONVEYOR_STAGES = ["Scanner Discovery", "Immutable Candidate Lineage", "Evidence Assembly", "Historical Comparison", "Professional Observation", "Skeptic Review", "Committee Review", "Risk Inspection", "Governed Paper Proposal"] as const;

const record = (value: unknown): RecordValue => value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
const rows = (value: unknown): RecordValue[] => Array.isArray(value) ? value.filter((item): item is RecordValue => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
const text = (value: unknown, fallback = "UNAVAILABLE"): string => typeof value === "string" && value.trim() ? value.trim() : fallback;
const scalar = (value: unknown): string => value === null || value === undefined ? "NOT REPORTED" : typeof value === "boolean" ? value ? "YES" : "NO" : typeof value === "number" || typeof value === "string" ? String(value) : "BOUNDED DETAIL";
const section = (snapshot: ExpansionSnapshot | null, key: string) => snapshot?.sections?.[key];
const statusClass = (state: unknown) => text(state).toLowerCase().replaceAll("_", "-");

function Status({ state, label }: { state: unknown; label?: string }) {
  const value = text(state);
  return <span className={`mew-status is-${statusClass(value)}`} aria-label={`${label ?? "Status"}: ${value}`}><i aria-hidden="true" />{value.replaceAll("_", " ")}</span>;
}

function Panel({ id, eyebrow, title, state, children, className = "" }: { id: string; eyebrow: string; title: string; state: unknown; children: React.ReactNode; className?: string }) {
  return <section id={id} className={`mew-panel ${className}`} aria-labelledby={`${id}-title`}><header><div><span>{eyebrow}</span><h3 id={`${id}-title`}>{title}</h3></div><Status state={state} label={`${title} state`} /></header>{children}</section>;
}

export function characterDialogue(snapshot: ExpansionSnapshot | null) {
  const projection = record(section(snapshot, "projection_activation")?.data);
  const factory = record(section(snapshot, "multi_asset_factory")?.data);
  const books = record(section(snapshot, "books")?.data);
  const market = text(factory.market_session_state, "UNKNOWN");
  const candidates = rows(record(section(snapshot, "candidate_conveyor")?.data).candidates);
  const evidence = text(factory.projection_freshness, "UNAVAILABLE");
  const professional = section(snapshot, "professional_strategy_observatory")?.state ?? "UNAVAILABLE";
  return [
    { key: "max", name: "MAX", role: "Factory foreman", line: market === "MARKET_CLOSED_WEEKEND" ? `The projection machinery is alive. Market evidence is ${evidence}; we do not polish old timestamps.` : `Reader ${scalar(projection.reader_state)}. Market evidence ${evidence}. Every room proves its own work.` },
    { key: "policy", name: "Policy Analyst", role: "Policy and regulation", line: "No policy claim enters the floor without attributed, point-in-time evidence." },
    { key: "macro", name: "Macro Analyst", role: "Rates and regime", line: market === "MARKET_CLOSED_WEEKEND" ? "The market clock is closed. No current-session macro state is inferred." : "Rates, inflation and regime context remain evidence-bound." },
    { key: "fundamentals", name: "Sector / Market Analyst", role: "Company and industry", line: candidates.length ? "Lineage exists; company evidence still requires primary verification." : "No authenticated candidate identities are available. I am not inventing a watchlist." },
    { key: "market_structure", name: "Historical Analyst", role: "Comparable regimes", line: "A historical analogue is a hypothesis, never a causal verdict." },
    { key: "commodities", name: "Professional Research Liaison", role: "Attributed observations", line: professional === "AVAILABLE" || professional === "CURRENT" ? "Licensed observations are visible, separate from IIOS conclusions." : "Professional evidence is unavailable; no opinion has been supplied." },
    { key: "skeptic", name: "Skeptic / Red Team", role: "Falsification", line: candidates.length ? "Show the invalidation case before this crate moves." : "Lineage is unavailable. Conveyor stopped—correctly." },
    { key: "portfolio", name: "Risk Keeper", role: "Capital protection", line: "Research eligibility is false. Paper and execution authority remain locked." },
    { key: "max", name: "Portfolio Office", role: "Paper truth", line: `NAV ${books.nav == null ? "unavailable" : `$${Number(books.nav).toLocaleString()}`}; cash ${books.cash == null ? "unavailable" : `$${Number(books.cash).toLocaleString()}`}; positions ${books.positions == null ? "unavailable" : books.positions}.` },
  ] as const;
}

function CharacterBriefing({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  return <section className="mew-cast" aria-labelledby="mew-cast-title"><header><span>DETERMINISTIC SHIFT BRIEFING</span><h3 id="mew-cast-title">The crew reports what the evidence permits</h3></header><div>{characterDialogue(snapshot).map((item, index) => <article key={`${item.name}-${index}`}><CinematicCharacterPortrait characterKey={item.key} variant={item.key === "max" ? "boss" : "card"} active={false} reacting={false} showLabel={false} /><div><strong>{item.name}</strong><small>{item.role}</small><p>{item.line}</p></div></article>)}</div></section>;
}

function MetricGrid({ values }: { values: Array<[string, unknown]> }) {
  return <dl className="mew-metrics">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{scalar(value)}</dd></div>)}</dl>;
}

function Overview({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const activation = record(section(snapshot, "projection_activation")?.data);
  const market = record(section(snapshot, "market_session")?.data);
  const books = record(section(snapshot, "books")?.data);
  const authority = record(section(snapshot, "authority_lock")?.data);
  return <div className="mew-grid mew-grid--overview">
    <Panel id="expansion-status" eyebrow="EXPANSION WING" title="Projection Receiving Office" state={section(snapshot, "projection_activation")?.state}><MetricGrid values={[["Reader", activation.reader_state], ["Integrity", activation.integrity_state], ["Hash", activation.hash_validation], ["Artifact freshness", activation.freshness_state], ["Evidence current", activation.evidence_current], ["Publisher evidence", activation.publisher_state], ["Sequence", activation.sequence], ["Market session", market.state]]} /><p className="mew-notice">A current projection artifact does not make stale market evidence current. Publisher health remains unavailable unless independently authenticated.</p></Panel>
    <Panel id="paper-office-summary" eyebrow="CAPITAL TRUTH" title="Paper Portfolio Office" state={section(snapshot, "books")?.state}><div className="mew-money"><strong>{books.nav == null ? "NAV UNAVAILABLE" : `$${Number(books.nav).toLocaleString()} NAV`}</strong><strong>{books.cash == null ? "CASH UNAVAILABLE" : `$${Number(books.cash).toLocaleString()} CASH`}</strong></div><MetricGrid values={[["Positions", books.positions], ["Transactions", books.transactions], ["Orders", books.orders], ["Fills", books.fills]]} /></Panel>
    <Panel id="authority-locks" eyebrow="FAMILY RULES" title="Authority Lock Cabinet" state={section(snapshot, "authority_lock")?.state}><MetricGrid values={[["Provider", authority.provider], ["Credential", authority.credential], ["Paper order", authority.paper_order], ["Broker", authority.broker], ["Ledger write", authority.ledger_write], ["Live execution", authority.live_execution]]} /><p className="mew-lock">◆ RESEARCH MAY SPEAK. CAPITAL DOES NOT MOVE.</p></Panel>
  </div>;
}

function TradingFloor({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const factory = record(section(snapshot, "multi_asset_factory")?.data);
  const laneStates = record(factory.lane_states);
  return <Panel id="multi-asset-floor" eyebrow="TEN GOVERNED DESKS" title="Multi-Asset Trading Floor" state={section(snapshot, "multi_asset_factory")?.state} className="mew-wide"><div className="mew-lanes">{MULTI_ASSET_LANES.map(([key, label, basis]) => { const lane = record(laneStates[key]); return <article key={key}><div className="mew-lane-light" aria-hidden="true" /><header><h4>{label}</h4><Status state={lane.state} /></header><MetricGrid values={[["Freshness", lane.freshness], ["Basis", lane.instrument_basis ?? basis], ["Candidates", lane.candidate_count], ["Research eligible", lane.research_eligible], ["Paper eligible", lane.paper_eligible], ["Blocker", lane.missing_evidence]]} /></article>; })}</div></Panel>;
}

function Conveyor({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const source = section(snapshot, "candidate_conveyor");
  const candidates = rows(record(source?.data).candidates).slice(0, 5);
  return <Panel id="candidate-conveyor" eyebrow="NINE CONTROLLED STAGES" title="Candidate Conveyor" state={source?.state} className="mew-wide"><ol className="mew-conveyor">{CONVEYOR_STAGES.map((stage, index) => <li key={stage}><b>{index + 1}</b><span>{stage}</span></li>)}</ol><div className="mew-machine-stop"><strong>{candidates.length ? `${candidates.length} lineage-authenticated crate${candidates.length === 1 ? "" : "s"}` : "MACHINERY STOPPED · NO AUTHENTICATED IDENTITIES"}</strong><p>{candidates.length ? "No stage implies approval; every crate retains immutable lineage." : "MAX: Aggregate counts cannot grow nameplates. The belt waits for current immutable lineage."}</p></div>{candidates.map((candidate) => <article className="mew-candidate" key={text(candidate.candidate_id)}><strong>{text(candidate.instrument_id, "UNKNOWN INSTRUMENT")}</strong><span>{text(candidate.asset_lane)}</span><code>{text(candidate.candidate_id)}</code></article>)}</Panel>;
}

function ScalarRoom({ id, eyebrow, title, source, snapshot, copy }: { id: string; eyebrow: string; title: string; source: string; snapshot: ExpansionSnapshot | null; copy: string }) {
  const room = section(snapshot, source); const data = record(room?.data);
  const scalars = Object.entries(data).filter(([, value]) => value === null || ["string", "number", "boolean"].includes(typeof value)).slice(0, 12);
  return <Panel id={id} eyebrow={eyebrow} title={title} state={room?.state}><p>{copy}</p>{scalars.length ? <MetricGrid values={scalars.map(([key, value]) => [key.replaceAll("_", " "), value])} /> : <p className="mew-unavailable">No sanitized structured evidence is available.</p>}</Panel>;
}

function Feed({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const activation = record(section(snapshot, "projection_activation")?.data);
  const events = useMemo(() => {
    const values: Array<[string, string, unknown]> = [
      [`projection:${scalar(activation.reader_state)}:${scalar(activation.integrity_state)}:${scalar(activation.freshness_state)}`, "Projection accepted", activation.freshness_state],
      [`market:${scalar(record(section(snapshot, "market_session")?.data).state)}`, "Market session", record(section(snapshot, "market_session")?.data).state],
      [`lineage:${scalar(section(snapshot, "candidate_conveyor")?.state)}`, "Candidate lineage", section(snapshot, "candidate_conveyor")?.state],
      [`9h:${scalar(section(snapshot, "benchmark_9h")?.state)}`, "9H validation", section(snapshot, "benchmark_9h")?.state],
      [`9i:${scalar(section(snapshot, "shadow_9i")?.state)}`, "9I shadow", section(snapshot, "shadow_9i")?.state],
      [`9j:${scalar(section(snapshot, "outcomes_9j")?.state)}`, "9J outcomes", section(snapshot, "outcomes_9j")?.state],
      [`publisher:${scalar(activation.publisher_state)}`, "Publisher evidence", activation.publisher_state],
    ];
    return [...new Map(values.map((event) => [event[0], event])).values()];
  }, [snapshot, activation.freshness_state, activation.integrity_state, activation.publisher_state, activation.reader_state]);
  return <aside className="mew-feed" aria-labelledby="mew-feed-title"><header><span>MARKET INTELLIGENCE FEED</span><h3 id="mew-feed-title">Browser-safe semantic receipts</h3></header><ol>{events.map(([identity, label, state]) => <li key={identity}><Status state={state} label={label} /><strong>{label}</strong><small>{identity}</small></li>)}</ol></aside>;
}

function ControlRoom({ snapshot, connection, snapshotAgeSeconds }: { snapshot: ExpansionSnapshot | null; connection: TruthState; snapshotAgeSeconds: number | null }) {
  const activation = record(section(snapshot, "projection_activation")?.data);
  const factory = record(section(snapshot, "multi_asset_factory")?.data);
  const lanes = Object.values(record(factory.lane_states));
  const counts = lanes.reduce<Record<string, number>>((total, raw) => { const state = text(record(raw).state); total[state] = (total[state] ?? 0) + 1; return total; }, {});
  return <Panel id="expansion-control" eyebrow="COLLAPSED TECHNICAL OFFICE" title="Expansion Control Room" state={connection} className="mew-wide"><MetricGrid values={[["Build", "SUPERBATCH 18"], ["Polling", "15 SECONDS · ONE OWNER"], ["Snapshot age", snapshotAgeSeconds], ["Sequence", activation.sequence], ["Reader", activation.reader_state], ["Integrity", activation.integrity_state], ["Artifact freshness", activation.freshness_state], ["Market evidence", factory.projection_freshness], ["Session", factory.market_session_state], ["Candidate lineage", section(snapshot, "candidate_conveyor")?.state], ["Lane totals", Object.entries(counts).map(([key, value]) => `${key} ${value}`).join(" · ")]]} /><details><summary>Technical details</summary><pre>{JSON.stringify({ schema_version: snapshot?.schema_version, mode: snapshot?.mode, source_states: Object.fromEntries(Object.entries(snapshot?.sections ?? {}).map(([key, value]) => [key, value.state])), authority: snapshot?.authority }, null, 2)}</pre></details><details><summary>Engineering rollback reference</summary><p>Port 5177 remains a separate engineering reference. Normal factory navigation never leaves this application.</p></details></Panel>;
}

export default function MobExpansionWing() {
  const { snapshot, connection, fixtureMode, snapshotAgeSeconds } = useExpansionWingSnapshot();
  const [department, setDepartment] = useState<DepartmentKey>("overview");
  const content = department === "overview" ? <Overview snapshot={snapshot} /> : department === "trading" ? <TradingFloor snapshot={snapshot} /> : department === "conveyor" ? <Conveyor snapshot={snapshot} /> : department === "observatory" ? <ScalarRoom id="professional-observatory" eyebrow="ATTRIBUTED OBSERVATION ONLY" title="Professional Strategy Observatory" source="professional_strategy_observatory" snapshot={snapshot} copy="Professional evidence remains separate from IIOS conclusions and cannot promote a candidate." /> : department === "laboratory" ? <div className="mew-grid"><ScalarRoom id="research-lab" eyebrow="HYPOTHESES · NOT POSITIONS" title="Research Laboratory" source="paper_research_sleeves" snapshot={snapshot} copy="Modeled sleeves cannot spend operational paper cash or create orders." /><ScalarRoom id="pattern-lab" eyebrow="POINT-IN-TIME TESTING" title="Pattern Laboratory" source="outcomes_9j" snapshot={snapshot} copy="Correlation is not causality or proof of profitability." /></div> : department === "committee" ? <ScalarRoom id="committee-room" eyebrow="HUMAN-GATED DECISION" title="Committee Room" source="committee" snapshot={snapshot} copy="No evidence advances automatically and no decision grants execution authority." /> : department === "risk" ? <ScalarRoom id="risk-inspection" eyebrow="CAPITAL PROTECTION" title="Risk Inspection" source="risk" snapshot={snapshot} copy="Missing evidence, invalidation and authority locks remain binding." /> : department === "portfolio" ? <Overview snapshot={snapshot} /> : department === "learning" ? <div className="mew-grid"><ScalarRoom id="learning-theater" eyebrow="OUTCOMES · CALIBRATION" title="Outcome Learning Theater" source="outcomes_9j" snapshot={snapshot} copy="No new outcome means no fabricated lesson." /><ScalarRoom id="failure-museum" eyebrow="FAILED HYPOTHESES RETAINED" title="Failure Museum" source="benchmark_9h" snapshot={snapshot} copy="Failures remain evidence; they do not become recommendations." /></div> : department === "evidence" ? <div className="mew-grid"><ScalarRoom id="evidence-warehouse" eyebrow="PROVENANCE FIRST" title="Evidence Warehouse" source="knowledge_operations" snapshot={snapshot} copy="Browser output contains counts and fixed states, never source text or private paths." /><ScalarRoom id="interview-studio" eyebrow="CONSENT REQUIRED" title="Interview Studio" source="cases" snapshot={snapshot} copy="No transcript or claim enters review without consent and professional approval." /></div> : <ControlRoom snapshot={snapshot} connection={connection} snapshotAgeSeconds={snapshotAgeSeconds} />;
  return <main className="mew-shell" aria-labelledby="mew-title"><header className="mew-masthead"><div><span>INTELLIGENCE IIOS FACTORY · EAST WORKS</span><h1 id="mew-title">THE EXPANSION WING</h1><p>One factory. Ten governed desks. Evidence moves; authority does not.</p></div><div><Status state={connection} label="Projection connection" /><strong>{fixtureMode ? "FIXTURE / NON-LIVE" : "LIVE READ-ONLY"}</strong><small>{snapshotAgeSeconds == null ? "Snapshot age unavailable" : `Snapshot age ${snapshotAgeSeconds}s`}</small></div></header><nav className="mew-departments" aria-label="Expansion Wing departments">{UNIFIED_DEPARTMENTS.map((item) => <button key={item.key} type="button" aria-pressed={department === item.key} onClick={() => setDepartment(item.key)}><b>{item.code}</b><span>{item.label}</span></button>)}</nav><CharacterBriefing snapshot={snapshot} /><Feed snapshot={snapshot} />{content}<footer className="mew-footer">FAMILY RULES · SOURCE BEFORE STORY · STALE IS NOT INVALID · UNKNOWN IS NOT ZERO · NO BROKER · NO LIVE EXECUTION</footer></main>;
}

/* eslint-disable react-refresh/only-export-components -- exported registries and narration are deterministic test seams */
import { useEffect, useMemo, useRef, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { useExpansionWingSnapshot, type ExpansionSnapshot, type TruthState } from "./ExpansionWingSnapshotContext";
import "./MobExpansionWing.css";

type RecordValue = Record<string, unknown>;
type DepartmentKey = "overview" | "products" | "trading" | "conveyor" | "observatory" | "laboratory" | "committee" | "risk" | "portfolio" | "learning" | "evidence" | "control";

export const UNIFIED_DEPARTMENTS: ReadonlyArray<{ key: DepartmentKey; label: string; code: string }> = [
  { key: "overview", label: "Expansion Wing", code: "EW" },
  { key: "products", label: "Multi-Product Research Floor", code: "24D" },
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

export const MULTI_PRODUCT_ROOMS = [
  "Multi-Product Trading Floor", "Rates and Credit Vault", "Options Strategy Room",
  "Commodities and Currency Dock", "Digital Assets Night Desk", "Real Assets and Income Office",
  "Intraday Operations Desk", "Relative-Value Workshop", "Professional Strategy Observatory",
  "Parallel Paper Laboratory", "Cross-Asset Committee Chamber", "Multi-Product Risk Inspection",
] as const;

export const PRODUCT_DESKS = [
  ["Multi-Product Trading Floor", "U.S. Large-Cap Equities", "DIRECT"],
  ["Multi-Product Trading Floor", "U.S. Mid-Cap Equities", "DIRECT"],
  ["Multi-Product Trading Floor", "U.S. Small-Cap Equities", "DIRECT"],
  ["Multi-Product Trading Floor", "International Developed Equities", "DIRECT"],
  ["Multi-Product Trading Floor", "Emerging-Market Equities", "DIRECT"],
  ["Multi-Product Trading Floor", "Sector and Thematic ETFs", "DIRECT"],
  ["Multi-Product Trading Floor", "Broad-Market and Factor ETFs", "DIRECT"],
  ["Rates and Credit Vault", "U.S. Treasury Bills and Cash Equivalents", "DIRECT"],
  ["Rates and Credit Vault", "U.S. Treasury Notes and Bonds", "DIRECT"],
  ["Rates and Credit Vault", "Treasury ETFs and Duration Proxies", "PROXY"],
  ["Rates and Credit Vault", "Investment-Grade Corporate Bonds", "DIRECT"],
  ["Rates and Credit Vault", "High-Yield Corporate Bonds", "DIRECT"],
  ["Rates and Credit Vault", "Municipal Bonds and Municipal ETFs", "DIRECT OR PROXY"],
  ["Options Strategy Room", "Listed Equity and ETF Options", "DERIVATIVE"],
  ["Options Strategy Room", "Index Options", "DERIVATIVE"],
  ["Commodities and Currency Dock", "Commodity ETFs and ETC Proxies", "PROXY"],
  ["Commodities and Currency Dock", "Commodity Futures References", "REFERENCE"],
  ["Commodities and Currency Dock", "Foreign-Exchange Spot References", "REFERENCE"],
  ["Commodities and Currency Dock", "Currency ETFs and FX Proxies", "PROXY"],
  ["Digital Assets Night Desk", "Crypto Spot References", "REFERENCE"],
  ["Digital Assets Night Desk", "Crypto ETFs and Listed Proxies", "PROXY"],
  ["Real Assets and Income Office", "REITs and Listed Real-Estate Securities", "DIRECT"],
  ["Real Assets and Income Office", "Preferred Stock and Income Securities", "DIRECT"],
  ["Real Assets and Income Office", "Money-Market and Ultra-Short-Duration Products", "DIRECT OR PROXY"],
] as const;

export const METHOD_DESKS = [
  "Intraday Momentum", "Opening-Range/Breakout Research", "Mean Reversion", "Event-Driven",
  "Catalyst/News Reaction", "Trend Following", "Relative Value", "Pairs Trading",
  "Yield-Curve and Duration", "Credit Spread", "Volatility and Options Structure",
  "Income/Cash Management", "Tactical Asset Allocation", "Long-Horizon Fundamental",
  "Policy/Macro Regime", "Professional-Method Replication Research",
] as const;
export const SYNTHETIC_SLEEVE_LABEL = "Synthetic comparison basis — not deployable capital.";

export const TUESDAY_PILOTS = [
  { ticker: "MU", title: "U.S. Large-Cap Common Stock", product: "U.S. Large-Cap Equities", venue: "NASDAQ", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "SPY", title: "Broad-Market ETF", product: "Broad-Market and Factor ETFs", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "XLK", title: "Sector ETF", product: "Sector and Thematic ETFs", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "VNQ", title: "Listed REIT Proxy", product: "REITs and Listed Real-Estate Securities", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "TLT", title: "Treasury-Duration Proxy", product: "Treasury ETFs and Duration Proxies", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "GLD", title: "Commodity Proxy", product: "Commodity ETFs and ETC Proxies", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "UUP", title: "Currency Proxy", product: "Currency ETFs and FX Proxies", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "IBIT", title: "Listed Crypto Proxy", product: "Crypto ETFs and Listed Proxies", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "PFF", title: "Preferred/Income ETF Proxy", product: "Preferred Stock and Income Securities", blocker: "Waiting for current Tuesday evidence" },
  { ticker: "BIL", title: "Ultra-Short Listed Proxy", product: "Money-Market and Ultra-Short-Duration Products", blocker: "Waiting for current Tuesday evidence" },
] as const;

export const TUESDAY_PENDING_IDENTITY_ROOMS = new Set([
  "U.S. Mid-Cap Equities", "U.S. Small-Cap Equities",
  "International Developed Equities", "Emerging-Market Equities",
]);
export const TUESDAY_STRUCTURAL_LABELS = new Map<string, string>([
  ["U.S. Treasury Bills and Cash Equivalents", "Treasury Bills"],
  ["U.S. Treasury Notes and Bonds", "Treasury Notes and Bonds"],
  ["Investment-Grade Corporate Bonds", "Investment-Grade Credit"],
  ["High-Yield Corporate Bonds", "High-Yield Credit"],
  ["Municipal Bonds and Municipal ETFs", "Municipal Credit"],
  ["Listed Equity and ETF Options", "Equity/ETF Options"],
  ["Index Options", "Index Options"],
  ["Commodity Futures References", "Commodity Futures"],
  ["Foreign-Exchange Spot References", "FX Spot"],
  ["Crypto Spot References", "Crypto Spot"],
]);
export const TUESDAY_CREDIT_STAGES = [
  { stage: "A", title: "Core Release", ceiling: 100, state: "NOT RELEASED", gate: "Separate owner authorization" },
  { stage: "B", title: "Evidence Expansion", ceiling: 50, state: "LOCKED", gate: "Stage A review + new owner authorization" },
  { stage: "C", title: "Owner Reserve", ceiling: 50, state: "LOCKED", gate: "Named purpose, instruments, calls and expiry" },
] as const;

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
    { key: "market_structure", name: "Learning Theater", role: "Outcome calibration", line: "No resolved research outcome means no score, no lesson, and no profitability claim." },
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

function TuesdayCommandCenter({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const activation = record(section(snapshot, "projection_activation")?.data);
  const market = record(section(snapshot, "market_session")?.data);
  const books = record(section(snapshot, "books")?.data);
  const controller = record(section(snapshot, "tuesday_controller_status")?.data);
  const unattended = record(section(snapshot, "unattended_tuesday_status")?.data);
  const unattendedUnavailable = section(snapshot, "unattended_tuesday_status")?.state === "UNAVAILABLE" || unattended.provenance === "UNAVAILABLE";
  const providerReadiness = record(section(snapshot, "provider_stage_a_readiness")?.data);
  const unattendedPhase = text(unattended.phase, "UNATTENDED_POLICY_NOT_INSTALLED");
  const unattendedHeadings: Record<string, string> = {
    UNATTENDED_POLICY_NOT_INSTALLED: "POLICY NOT INSTALLED",
    TUESDAY_POLICY_INSTALLED_DISABLED: "POLICY INSTALLED — DISABLED",
    TUESDAY_WAITING_FOR_PREFLIGHT: "WAITING FOR PREFLIGHT",
    TUESDAY_PREFLIGHT_RUNNING: "PREFLIGHT RUNNING",
    TUESDAY_PREFLIGHT_FAILED_CLOSED: "PREFLIGHT FAILED CLOSED",
    TUESDAY_READY_FOR_OPEN: "READY FOR TUESDAY",
    TUESDAY_STAGE_A_RUNNING: "STAGE A RUNNING",
    TUESDAY_STAGE_A_PARTIAL: "PARTIAL SESSION",
    TUESDAY_STAGE_A_COMPLETED: "STAGE A COMPLETE",
    TUESDAY_STAGE_A_LOCKED: "STAGE A LOCKED",
    TUESDAY_SESSION_CLOSED: "SESSION CLOSED",
    TUESDAY_EMERGENCY_STOPPED: "EMERGENCY STOPPED",
  };
  const unattendedHeading = unattendedUnavailable ? "POLICY STATE FAILED CLOSED" : unattendedHeadings[unattendedPhase] ?? "FAILED CLOSED";
  const controllerInstalled = controller.installed === true;
  const controllerRunning = controller.running === true;
  const controllerActivated = controller.activated === true;
  const controllerState = text(controller.state, "NOT_INSTALLED");
  const controllerPhase = text(controller.phase, "NOT_INSTALLED");
  const controllerHumanGate = text(controller.human_gate, "INSTALLATION REQUIRED");
  const controllerNextAction = text(controller.next_action, "PREPARE DISABLED INSTALLATION");
  const controllerV2 = text(controller.controller_schema) === "iios-tuesday-controller-state-v2";
  const controllerProvenance = text(controller.controller_status_provenance, "UNAVAILABLE");
  const controllerAuthentic = controllerProvenance === "AUTHENTIC_OPERATIONAL_STATE";
  const controllerSynthetic = controllerProvenance === "SYNTHETIC_FIXTURE_NON_LIVE";
  const controllerProvenanceAvailable = controllerAuthentic || controllerSynthetic;
  const controllerCeiling = controllerV2 ? scalar(controller.daily_hard_ceiling) : 30;
  const authenticRehearsalRaw = text(controller.authentic_rehearsal_status, "UNAVAILABLE");
  const authenticRehearsal = new Set(["NOT_YET_RECORDED", "PASSED_CLOSED_HOLIDAY"]).has(authenticRehearsalRaw) ? authenticRehearsalRaw : "UNAVAILABLE";
  const authenticRehearsalDisplay = authenticRehearsal === "NOT_YET_RECORDED" ? "NOT YET RECORDED" : authenticRehearsal;
  const compatibilityRehearsal = text(controller.compatibility_rehearsal_status) === "MIGRATED_COMPATIBILITY_RECEIPT_NOT_OPERATIONAL_PROOF"
    ? "MIGRATED COMPATIBILITY RECEIPT — NOT OPERATIONAL PROOF" : "UNAVAILABLE";
  const productCurrent = 0;
  return <div className="mew-grid mew-tuesday-grid" data-controller-version={controllerV2 ? "v2" : "v1"}>
    <Panel id="tuesday-command" eyebrow="OPENING-DAY CONTROL" title="Tuesday Test Day Command Center" state="NOT_ACTIVATED" className="mew-wide">
      <section className="mew-whole-factory-plan" aria-labelledby="mew-whole-factory-title">
        <span>FUTURE OWNER-AUTHORIZED PLAN · OPERATIONAL RELEASE ZERO</span>
        <h2 id="mew-whole-factory-title">24 rooms · 16 methods · staged 200-credit hard ceiling</h2>
        <p>Ten listed pilots may become evidence-eligible; four equity rooms await authenticated identities; ten specialized rooms remain structural and fail closed.</p>
        <div className="mew-participation-summary"><strong>24 of 24 product rooms participate</strong><dl><div><dt>Live-evidence pilots</dt><dd>10</dd></div><div><dt>Identity/source-readiness rooms</dt><dd>4</dd></div><div><dt>Structural fail-closed rooms</dt><dd>10</dd></div><div><dt>Operational trading rooms</dt><dd>0</dd></div><div><dt>Initially released credits</dt><dd>0</dd></div><div><dt>Stage A draft</dt><dd>50 planned requests</dd></div></dl></div>
        <div className="mew-credit-stages" aria-label="Three separately authorized future credit stages">{TUESDAY_CREDIT_STAGES.map(item=><article key={item.stage}><b>STAGE {item.stage}</b><strong>{item.title}</strong><span>{item.ceiling} credit maximum</span><Status state={item.state}/><small>{item.gate}</small></article>)}</div>
        <dl><div><dt>{controllerV2 ? "Validated daily ceiling" : "Future daily ceiling"}</dt><dd>{controllerV2 ? controllerCeiling : 200}</dd></div><div><dt>Released now</dt><dd>0</dd></div><div><dt>Automatic release</dt><dd>Prohibited</dd></div><div><dt>Browser invocation</dt><dd>Prohibited</dd></div></dl>
        <p className="mew-scanner-contract"><strong>Scanner scope continues beyond the pilot list.</strong> Aggregate scanner counts cannot create candidates. Browser-triggered scanning and credit spending are prohibited.</p>
        <details><summary>Whole-factory commissioning contract</summary><p>10 LIVE EVIDENCE ELIGIBLE · 4 AWAITING SUPPORTED IDENTITY · 10 STRUCTURAL FAIL CLOSED · 384 METHOD/PRODUCT PAIRS BLOCKED · RESULTS NULL</p></details>
      </section>
      <section className="mew-tuesday-hero" aria-labelledby="mew-tuesday-hero-title"><span>TUESDAY PAPER TEST · NO REAL MONEY</span><h2 id="mew-tuesday-hero-title">10 pilots · 3 observations each · 30-credit maximum</h2><strong>Controller {controllerActivated ? "activation state rejected" : "disabled — awaiting authorization"}</strong><div className="mew-rehearsal-result"><div><span>MONDAY REHEARSAL · SEPTEMBER 7, 2026</span><strong>AUTHENTIC MONDAY REHEARSAL: {authenticRehearsalDisplay}</strong><small>{compatibilityRehearsal.replaceAll("_", " ")} · Provider requests 0 · Credits {scalar(controller.credits_today ?? 0)} · Candidates 0 · Operational activity 0</small></div><div><span>TUESDAY CONTROLLER</span><strong>{controllerInstalled ? "INSTALLED" : "NOT INSTALLED"} · {controllerRunning ? "PROCESS RUNNING" : "PROCESS NOT RUNNING"}</strong><small>{controllerActivated ? "ACTIVATION REJECTED" : `${controllerPhase.replaceAll("_", " ")} · ${controllerHumanGate.replaceAll("_", " ")}`}</small></div></div><div className="mew-observation-phases"><article><b>1</b><span>Opening Evidence</span><small>Not scheduled until authorization</small></article><article><b>2</b><span>Intraday Mark</span><small>One bounded observation</small></article><article><b>3</b><span>Closing Mark</span><small>Reconcile without promotion</small></article></div><dl><div><dt>Ten instruments</dt><dd>Three calls maximum each</dd></div><div><dt>Global credit ceiling</dt><dd>30</dd></div><div><dt>Requests / credits today</dt><dd>{scalar(controller.requests_today ?? 0)} / {scalar(controller.credits_today ?? 0)}</dd></div><div><dt>Auto-reload</dt><dd>Disabled</dd></div><div><dt>Next allowable action</dt><dd>{controllerNextAction.replaceAll("_", " ")}</dd></div><div><dt>Market / session</dt><dd>{scalar(market.state)}</dd></div><div><dt>Current evidence</dt><dd>Waiting for Tuesday</dd></div><div><dt>Candidate / Committee / Risk</dt><dd>No authenticated candidate</dd></div><div><dt>Corporate-action suspensions</dt><dd>None reported</dd></div><div><dt>Synthetic / post-close state</dt><dd>Not started / not ready</dd></div><div><dt>Browser invocation</dt><dd>Prohibited</dd></div><div><dt>Automatic retry</dt><dd>Prohibited</dd></div><div><dt>Operational trading</dt><dd>Disabled</dd></div></dl><div className="mew-governance-flow" aria-label="Governance flow">{["Evidence","Human Review","Committee","Risk","Synthetic Observation","Intraday Mark","Closing Mark","Post-Close Audit"].map((stage,index)=><span key={stage}>{stage}{index<7?<i aria-hidden="true">→</i>:null}</span>)}</div><aside className="mew-fail-closed"><strong>THE CONTROLLER STOPS BEFORE CREDENTIAL ACCESS WHEN:</strong><ul>{["Wrong session","Stale or future evidence","Wrong instrument","Missing candidate lineage","Human decision rejected","Committee rejection","Risk rejection","Budget exhausted","Corporate action unresolved","Unsafe authority"].map(reason=><li key={reason}>{reason}</li>)}</ul></aside><details><summary>Exact contract details</summary><p>{controllerState} · {controllerPhase} · CONTROLLER_ACTIVATED_{controllerActivated ? "TRUE_REJECTED" : "FALSE"} · AUTHORITY_LOCKED · AUTOMATIC_RETRY_PROHIBITED</p></details></section>
      <section className={`mew-controller-version is-${controllerProvenanceAvailable ? controllerAuthentic ? "authentic" : "synthetic" : "unavailable"}`} data-controller-version={controllerV2 ? "v2" : "v1"} aria-label="Controller status provenance">
        <header><span>{controllerAuthentic ? "AUTHENTIC CONTROLLER STATUS" : controllerSynthetic ? "SYNTHETIC_FIXTURE_NON_LIVE" : "CONTROLLER STATUS UNAVAILABLE"}</span><strong>{controllerAuthentic ? controllerV2 ? "OPERATIONAL V2 · DISABLED" : "OPERATIONAL V1 · DISABLED" : controllerSynthetic ? "FUTURE REVIEW — NOT OPERATIONAL" : "PROVENANCE NOT AUTHENTICATED"}</strong>{controllerAuthentic && controllerV2 ? <small>MIGRATION COMPLETED · CONTROLLER NOT ACTIVATED</small> : null}</header>
        <dl>
          <div><dt>Schema</dt><dd>{controllerV2 ? "iios-tuesday-controller-state-v2" : "iios-tuesday-controller-state-v1"}</dd></div>
          <div><dt>Provenance</dt><dd>{controllerProvenanceAvailable ? controllerProvenance : "UNAVAILABLE"}</dd></div>
          <div><dt>Installed</dt><dd>{controllerInstalled ? "Yes" : "No"}</dd></div>
          <div><dt>Running</dt><dd>{controllerRunning ? "Yes" : "No"}</dd></div>
          <div><dt>Activated</dt><dd>{controllerActivated ? "Invalid" : "No"}</dd></div>
          <div><dt>Daily ceiling</dt><dd>{controllerCeiling}</dd></div>
          <div><dt>Released credits</dt><dd>0</dd></div>
          <div><dt>Phase</dt><dd>{controllerPhase}</dd></div>
          <div><dt>Migration</dt><dd>{!controllerProvenanceAvailable ? "UNAVAILABLE" : controllerSynthetic ? "SIMULATED / REHEARSED — NOT OPERATIONAL" : controllerV2 ? "COMPLETED_AND_VALIDATED" : "NOT PERFORMED"}</dd></div>
          <div><dt>Authority</dt><dd>{controller.authority_locked === true ? "Authority locked" : "Failed closed"}</dd></div>
        </dl>
        {controllerV2 && controllerProvenanceAvailable ? <div className="mew-v2-stages" aria-label="V2 locked stages"><article><strong>Stage A</strong><span>Draft 50 · Maximum 100 · Locked / not released</span></article><article><strong>Stage B</strong><span>Maximum 50 · Locked</span></article><article><strong>Stage C</strong><span>Maximum 50 · Locked</span></article></div> : null}
      </section>
      <section className={`mew-unattended-status${unattendedUnavailable ? " is-failed-closed" : ""}`} aria-labelledby="mew-unattended-title" data-phase={unattendedPhase}>
        <header><span>UNATTENDED TUESDAY · READ-ONLY STATUS</span><h3 id="mew-unattended-title">{unattendedHeading}</h3><strong>NO TRADING AUTHORITY</strong></header>
        <p>The one-day September 8 policy is non-recurring. Browser activity cannot install it, release credits, invoke providers, or control the supervisor.</p>
        <dl>
          <div><dt>Provenance</dt><dd>{text(unattended.provenance, "UNAVAILABLE")}</dd></div><div><dt>Policy status</dt><dd>{text(unattended.policy_status, "FAILED CLOSED").replaceAll("_", " ")}</dd></div>
          <div><dt>Session</dt><dd>{scalar(unattended.session_date)}</dd></div><div><dt>Controller phase</dt><dd>{text(unattended.phase, "UNAVAILABLE").replaceAll("_", " ")}</dd></div><div><dt>Next scheduled gate</dt><dd>{text(unattended.next_gate, "OPERATOR REVIEW REQUIRED")}</dd></div>
          <div><dt>Preflight</dt><dd>{text(unattended.preflight_status, "NOT RUN").replaceAll("_", " ")}</dd></div><div><dt>Stage A</dt><dd>{text(unattended.stage_a_status, "LOCKED").replaceAll("_", " ")}</dd></div>
          <div><dt>Policy schema</dt><dd>{text(unattended.policy_schema, "UNAVAILABLE")}</dd></div><div><dt>Commit binding</dt><dd>{text(unattended.commit_binding, "UNAVAILABLE")}</dd></div>
          <div><dt>Authorized allowance</dt><dd>{scalar(unattended.stage_a_authorized_allowance)} credits</dd></div><div><dt>Stage A maximum</dt><dd>{scalar(unattended.stage_a_maximum)} credits</dd></div><div><dt>Released credits</dt><dd>{scalar(unattended.released_credits)}</dd></div>
          <div><dt>Requests planned / completed</dt><dd>{scalar(unattended.planned)} / {scalar(unattended.completed)}</dd></div><div><dt>Failed / ambiguous</dt><dd>{scalar(unattended.failed)} / {scalar(unattended.ambiguous)}</dd></div>
          <div><dt>Confirmed / ambiguous credits</dt><dd>{scalar(unattended.confirmed_credits)} / {scalar(unattended.ambiguous_credits)}</dd></div><div><dt>Market session</dt><dd>{text(unattended.market_session, "UNAVAILABLE").replaceAll("_", " ")}</dd></div>
          <div><dt>Tuesday room participation</dt><dd>{scalar(unattended.pilot_rooms)} pilots · {scalar(unattended.readiness_rooms)} readiness · {scalar(unattended.structural_rooms)} structural</dd></div><div><dt>Authority</dt><dd>{unattended.authority_locked === true ? "Authority locked" : "FAILED CLOSED"}</dd></div>
        </dl>
        {unattendedUnavailable ? <p className="mew-unattended-failure" role="alert">POLICY STATE FAILED CLOSED · OPERATOR REVIEW REQUIRED · NO TRADING ACTIVITY IMPLIED</p> : null}
        {unattended.failure_category ? <p className="mew-unattended-failure">PREFLIGHT FAILED CLOSED · {text(unattended.failure_category).replaceAll("_", " ")}</p> : null}
        <details><summary>Technical status</summary><p>{text(unattended.phase)} · GENERATION {scalar(unattended.generation_sequence)} · READ {scalar(unattended.last_coherent_read_timestamp)}</p></details>
      </section>
      <section className="mew-controller-status" aria-label="Tuesday commissioning status">
        <article><h3>Monday rehearsal</h3><p><strong>AUTHENTIC MONDAY REHEARSAL: {authenticRehearsalDisplay}</strong></p><p>{compatibilityRehearsal}</p><dl><div><dt>Date</dt><dd>September 7, 2026</dd></div><div><dt>Session</dt><dd>{authenticRehearsal === "PASSED_CLOSED_HOLIDAY" ? "Closed holiday · Passed" : "Closed holiday · Not yet recorded"}</dd></div><div><dt>Requests</dt><dd>0</dd></div><div><dt>Credits</dt><dd>0</dd></div><div><dt>Candidates</dt><dd>0</dd></div><div><dt>Operational activity</dt><dd>0</dd></div></dl></article>
        <article><h3>Tuesday controller</h3><dl><div><dt>Installed</dt><dd>{controllerInstalled ? "Yes" : "No"}</dd></div><div><dt>Running</dt><dd>{controllerRunning ? "Yes" : "No"}</dd></div><div><dt>Activated</dt><dd>{controllerActivated ? "Invalid" : "No"}</dd></div><div><dt>Current phase</dt><dd>{controllerPhase.replaceAll("_", " ")}</dd></div><div><dt>Human gate</dt><dd>{controllerHumanGate.replaceAll("_", " ")}</dd></div><div><dt>Restart recovery</dt><dd>{text(controller.restart_recovery).replaceAll("_", " ")}</dd></div><div><dt>Integrity</dt><dd>{scalar(controller.integrity)}</dd></div><div><dt>Last sanitized update</dt><dd>{scalar(controller.last_update)}</dd></div><div><dt>Authority</dt><dd>{controller.authority_locked === true ? "Locked" : "Failed closed"}</dd></div></dl></article>
      </section>
      <p className="mew-notice"><strong>Current human gate:</strong> {controllerHumanGate.replaceAll("_", " ")}.</p>
      <section className="mew-provider-readiness" aria-label="Stage A provider readiness">
        <header><span>NON-SPENDING READINESS</span><h3>Stage A Provider Boundary</h3><Status state={text(providerReadiness.provider_state, "FAILED_CLOSED") as TruthState} /></header>
        <MetricGrid values={[["Commissioning", providerReadiness.commissioning_state], ["Unattended supervisor", providerReadiness.unattended_service_state], ["One-day policy", providerReadiness.one_day_policy_state], ["Provider", providerReadiness.provider_identity], ["Cost contract", providerReadiness.cost_contract_state], ["Cost binding", providerReadiness.cost_contract_binding], ["Request plan identities", providerReadiness.planned_identity_count], ["Request plan", providerReadiness.request_plan_state], ["Supported and costed", providerReadiness.supported_costed_identity_count], ["Blocked identities", providerReadiness.unsupported_identity_count], ["Expected Stage A cost", providerReadiness.worst_case_stage_a_credits], ["Authorized allowance", providerReadiness.stage_a_authorized_allowance_credits], ["Stage A maximum", providerReadiness.stage_a_maximum], ["Daily hard ceiling", providerReadiness.daily_hard_ceiling], ["Credential", providerReadiness.credential_presence_state], ["Released credits", providerReadiness.stage_a_released_credits], ["Stage B / C", `${text(providerReadiness.stage_b_state)} / ${text(providerReadiness.stage_c_state)}`], ["Failure category", providerReadiness.failure_category], ["Trading authority", false]]} />
        <p><strong>Next gate: owner policy authorization.</strong> Readiness inspection cannot retrieve credentials, contact a provider, release credits, or grant trading authority.</p>
      </section>
      <MetricGrid values={[["Market date", market.projection_generated_at], ["Approved session", market.state], ["Projection container", activation.freshness_state], ["Underlying evidence", section(snapshot, "projection_freshness")?.state], ["Publisher observation", activation.publisher_state], ["Radar cycle", section(snapshot, "radar")?.state], ["Candidate lineage", section(snapshot, "candidate_conveyor")?.state], ["9H validation", section(snapshot, "benchmark_9h")?.state], ["9I consumption", section(snapshot, "shadow_9i")?.state], ["9J outcomes", section(snapshot, "outcomes_9j")?.state], ["Professional research", section(snapshot, "professional_strategy_observatory")?.state], ["Provider / credits", section(snapshot, "provider_credit_meter")?.state]]} />
      <p className="mew-notice">MAX: {productCurrent} of 24 product sources are operationally current. All 16 methods remain insufficient-sample. A current container never upgrades stale underlying evidence.</p>
      <div className="mew-session-gates" aria-label="Tuesday session gates">{["CLOSED HOLIDAY", "MARKET CLOSED", "PRE-MARKET", "REGULAR SESSION", "POST-MARKET", "POST-CLOSE", "FAILED CLOSED"].map((gate) => <article key={gate}><strong>{gate}</strong><Status state="NOT_ACTIVATED" /><small>Calendar and human checkpoint required</small></article>)}</div>
    </Panel>
    <Panel id="independent-sleeves" eyebrow="24 INDEPENDENT LEDGERS" title="Independent Sleeve Laboratory" state="AVAILABLE_EMPTY"><p className="mew-sleeve-label">{SYNTHETIC_SLEEVE_LABEL}</p><MetricGrid values={[["Product sleeves", 24], ["Basis each", "$10,000"], ["Operational NAV", books.nav], ["Operational cash", books.cash], ["Operational positions", books.positions], ["Operational orders", books.orders], ["Unresolved outcomes", "NOT REPORTED"]]} /><details><summary>View 24 normalized sleeve contracts</summary><ol className="mew-sleeve-registry">{PRODUCT_DESKS.map(([, name]) => <li key={name}><strong>{name}</strong><span>$10,000 independent basis</span><small>ENTRY · COSTS · INVALIDATION · EXIT · OUTCOME: NOT REPORTED</small></li>)}</ol></details></Panel>
    <Panel id="post-close-audit" eyebrow="RECONCILIATION GATE" title="Post-Close Audit" state="NOT_ACTIVATED"><p>9H completion, natural 9I consumption, authentic 9J outcomes, costs, excursions, calibration and sample size must reconcile before any Tuesday report.</p><MetricGrid values={[["9H", section(snapshot, "benchmark_9h")?.state], ["9I", section(snapshot, "shadow_9i")?.state], ["9J", section(snapshot, "outcomes_9j")?.state], ["Operational fund touched", false], ["Promotion", false], ["Execution", false]]} /></Panel>
    <ProductAccountDirectory snapshot={snapshot} />
  </div>;
}

function ProductAccountDirectory({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const books = record(section(snapshot, "books")?.data);
  const [selected, setSelected] = useState<string>(TUESDAY_PILOTS[0].ticker);
  const detailRef = useRef<HTMLElement>(null);
  const selectedPilot = TUESDAY_PILOTS.find((pilot) => pilot.ticker === selected);
  const selectedRow = PRODUCT_DESKS.find(([, name]) => name === selected) ?? PRODUCT_DESKS.find(([, name]) => name === selectedPilot?.product) ?? PRODUCT_DESKS[0];
  const futureProducts = PRODUCT_DESKS.filter(([, name]) => !TUESDAY_PILOTS.some((pilot) => pilot.product === name));
  const readinessProducts = futureProducts.filter(([, name]) => TUESDAY_PENDING_IDENTITY_ROOMS.has(name));
  const structuralProducts = futureProducts.filter(([, name]) => TUESDAY_STRUCTURAL_LABELS.has(name));
  useEffect(() => {
    const restore = () => { const match = window.location.hash.match(/^#expansion\/product\/([^/]+)$/); const value = match ? decodeURIComponent(match[1]) : ""; const pilot = TUESDAY_PILOTS.find((item) => item.ticker.toLowerCase() === value.toLowerCase()); const product = PRODUCT_DESKS.find(([, name]) => name.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-") === value.toLowerCase()); if (pilot) setSelected(pilot.ticker); else if (product) setSelected(product[1]); };
    restore(); window.addEventListener("hashchange", restore); return () => window.removeEventListener("hashchange", restore);
  }, []);
  const selectProduct = (value: string, hash: string) => { setSelected(value); window.history.pushState({ museumMode: "expansion", productId: hash }, "", `#expansion/product/${encodeURIComponent(hash)}`); requestAnimationFrame(() => { detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); detailRef.current?.focus({ preventScroll: true }); }); };
  return <Panel id="product-account-directory" eyebrow="24 SEPARATE RESEARCH ACCOUNTS" title="Product Account Directory" state="AVAILABLE_EMPTY" className="mew-wide">
    <p>Twenty-four product rooms participate in Tuesday testing across ten live-evidence pilots, four listed-equity source-readiness rooms, and ten specialized structural test rooms.</p>
    <MetricGrid values={[["Product rooms", 24], ["Independent synthetic accounts", 24], ["Starting basis each", "$10,000"], ["Operational paper fund", "$10,000 SEPARATE"], ["Paper-test-ready products", 0], ["Research-only products", 11], ["Incomplete products", 13]]} />
    <div className="mew-account-separation"><article><span>SYNTHETIC RESEARCH ACCOUNTS</span><strong>24 independent measuring accounts · $10,000 each</strong><small>Not pooled · not deployable · not operational capital</small></article><article><span>OPERATIONAL PAPER FUND</span><strong>NAV ${Number(books.nav ?? 10000).toLocaleString()} · Cash ${Number(books.cash ?? 10000).toLocaleString()}</strong><small>Positions {scalar(books.positions)} · Orders {scalar(books.orders)} · Fills {scalar(books.fills)} · untouched by product experiments</small></article></div>
    <section className="mew-mu-feature" aria-labelledby="mew-mu-feature-title"><header><div><span>MU · NASDAQ COMMON STOCK</span><h3 id="mew-mu-feature-title">Tuesday Pilot #1</h3></div><strong>Waiting for Tuesday</strong></header><div className="mew-mu-facts"><b>Synthetic measuring account: $10,000</b><span>Cash $10,000 · No position · Operational fund untouched</span><span>Entry — · Shares — · Stop — · Target — · Return —</span><span>No recommendation · Committee not submitted · Risk not submitted</span></div><ol className="mew-mu-flow"><li className="is-current">Evidence<small>Waiting for Tuesday evidence</small></li><li>Thesis</li><li>Candidate</li><li>Committee</li><li>Risk</li><li>Synthetic Observation</li></ol><details><summary>Exact contract details</summary><p>Historical adjustment: UNSPECIFIED · WAITING_FOR_CURRENT_TUESDAY_EVIDENCE · FORWARD_ONLY_UNADJUSTED_OBSERVATION · eligibility FALSE</p></details></section>
    <header className="mew-directory-heading"><span>ALL ROOMS PARTICIPATE · LIVE-EVIDENCE TRACK</span><h3>10 Live-Evidence Pilots</h3><p>Eligible for bounded Tuesday evidence collection only after Stage A owner authorization.</p></header>
    <div className="mew-pilot-directory" aria-label="Exactly ten Tuesday live-evidence pilot rooms">{TUESDAY_PILOTS.map((pilot, index) => <button type="button" key={pilot.ticker} aria-pressed={selected === pilot.ticker} onClick={() => selectProduct(pilot.ticker, pilot.ticker.toLowerCase())}><span className="mew-pilot-number">PILOT {index + 1}</span><b>{pilot.ticker}</b><strong>{pilot.title}</strong><span>Participates in Tuesday test: YES</span><span>Live evidence: PENDING AUTHORIZATION</span><span>Independent synthetic basis: $10,000</span><em>Synthetic observation: NOT YET AUTHORIZED</em><small>Operational trading: DISABLED</small><small>Positions / trades: 0 / 0</small><small>Next observation: Opening Evidence</small><small>Blocker: {pilot.blocker}</small></button>)}</div>
    <section ref={detailRef} tabIndex={-1} className="mew-account-detail" aria-live="polite" aria-labelledby="selected-product-title"><header><div><span>SELECTED {selectedPilot ? "TUESDAY PILOT" : "FUTURE PRODUCT ROOM"}</span><h3 id="selected-product-title">{selectedPilot ? `${selectedPilot.ticker} · ${selectedPilot.title}` : selectedRow[1]}</h3></div><Status state={selectedPilot ? "DELAYED_DATA" : "NOT_ACTIVATED"} /></header><MetricGrid values={[["Product", selectedRow[1]], ["Exposure class", selectedRow[2]], ["Starting basis", "$10,000"], ["Synthetic cash", "$10,000"], ["Position", "NONE"], ["Trades", 0], ["Next observation", selectedPilot ? "OPENING EVIDENCE" : "NOT SCHEDULED"], ["Research eligible", false], ["Paper eligible", false], ["Blocker", selectedPilot ? "WAITING FOR CURRENT TUESDAY EVIDENCE" : "SOURCE NOT CONNECTED"]]} /><button className="mew-back-to-pilots" type="button" onClick={() => { document.querySelector<HTMLElement>(".mew-pilot-directory")?.scrollIntoView({ behavior: "smooth", block: "start" }); document.querySelector<HTMLButtonElement>(".mew-pilot-directory button")?.focus({ preventScroll: true }); }}>Back to Tuesday pilots</button><details><summary>Exact contract details</summary><p>{selectedPilot ? "DELAYED_DATA · WAITING_FOR_CURRENT_TUESDAY_EVIDENCE · FORWARD_ONLY_UNADJUSTED_OBSERVATION" : "NOT_ACTIVATED · AUTHENTIC_PRODUCT_EVIDENCE_REQUIRED"}</p></details></section>
    <header className="mew-directory-heading mew-future-heading"><span>ALL ROOMS PARTICIPATE · READINESS TRACK</span><h3>4 Listed-Equity Source-Readiness Rooms</h3><p>These rooms participate Tuesday by testing identity, provider coverage, entitlement, timestamps, product classification and fail-closed behavior. They receive no live request unless an exact instrument and separate authorization are approved.</p></header>
    <div className="mew-future-directory mew-readiness-directory" aria-label="Exactly four listed-equity source-readiness rooms">{readinessProducts.map(([department, name, classification], index) => { const hash=name.toLowerCase().replaceAll(/[^a-z0-9]+/g,"-"); return <button type="button" key={name} aria-pressed={selected === name} onClick={() => selectProduct(name, hash)}><b>{String(index + 1).padStart(2, "0")} · {name}</b><strong>Participates in Tuesday test: YES</strong><span>Test mode: IDENTITY AND SOURCE READINESS</span><small>{department} · {classification}</small><em>Live evidence: AWAITING SUPPORTED IDENTITY</em><small>Not eligible for synthetic observation</small><small>Operational trading: DISABLED</small></button>; })}</div>
    <header className="mew-directory-heading mew-structural-heading"><span>ALL ROOMS PARTICIPATE · STRUCTURAL TRACK</span><h3>10 Specialized Structural Test Rooms</h3><p>These rooms participate Tuesday by validating schemas, source requirements, licensing gates, method eligibility, cost/liquidity requirements, synthetic-account separation and correct fail-closed behavior.</p></header>
    <div className="mew-future-directory mew-structural-directory" aria-label="Exactly ten specialized structural fail-closed rooms">{structuralProducts.map(([department, name, classification], index) => { const hash=name.toLowerCase().replaceAll(/[^a-z0-9]+/g,"-"); return <button type="button" key={name} aria-pressed={selected === name} onClick={() => selectProduct(name, hash)}><b>{String(index + 1).padStart(2, "0")} · {TUESDAY_STRUCTURAL_LABELS.get(name)}</b><strong>Participates in Tuesday test: YES</strong><span>Test mode: STRUCTURAL FAIL CLOSED</span><small>{department} · {classification}</small><em>Specialized source: NOT ACTIVATED · Live evidence: NO</em><small>Not eligible for synthetic observation</small><small>Operational trading: DISABLED</small></button>; })}</div>
  </Panel>;
}

function TradingFloor({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const factory = record(section(snapshot, "multi_asset_factory")?.data);
  const laneStates = record(factory.lane_states);
  return <Panel id="multi-asset-floor" eyebrow="TEN GOVERNED DESKS" title="Multi-Asset Trading Floor" state={section(snapshot, "multi_asset_factory")?.state} className="mew-wide"><div className="mew-lanes">{MULTI_ASSET_LANES.map(([key, label, basis]) => { const lane = record(laneStates[key]); return <article key={key}><div className="mew-lane-light" aria-hidden="true" /><header><h4>{label}</h4><Status state={lane.state} /></header><MetricGrid values={[["Freshness", lane.freshness], ["Basis", lane.instrument_basis ?? basis], ["Candidates", lane.candidate_count], ["Research eligible", lane.research_eligible], ["Paper eligible", lane.paper_eligible], ["Blocker", lane.missing_evidence]]} /></article>; })}</div></Panel>;
}

function MultiProductFloor({ fixtureMode }: { fixtureMode: boolean }) {
  const [selected, setSelected] = useState<(typeof PRODUCT_DESKS)[number][1]>(PRODUCT_DESKS[0][1]);
  const [department, name, classification] = PRODUCT_DESKS.find(([, productName]) => productName === selected) ?? PRODUCT_DESKS[0];
  const methods = METHOD_DESKS;
  return <Panel id="multi-product-floor" eyebrow="24 PRODUCTS · 16 METHODS" title="Tuesday Multi-Product Research Floor" state="NOT_ACTIVATED" className="mew-wide">
    <p className="mew-fixture-banner">{fixtureMode ? "FIXTURE / NON-LIVE / RESEARCH ONLY" : "REGISTRY ONLY · OPERATIONAL SOURCES NOT ACTIVATED"}</p>
    <p>Every desk has a product-specific evidence contract. Registration is not availability, a proxy is not its underlying, and a research sleeve is not an operational position.</p>
    <nav className="mew-product-room-nav mew-product-room-nav--24" aria-label="Twenty-four product rooms">{PRODUCT_DESKS.map(([, productName], index) => <button key={productName} type="button" aria-pressed={selected === productName} onClick={() => setSelected(productName)}><b>{String(index + 1).padStart(2, "0")}</b><span>{productName}</span></button>)}</nav>
    <section className="mew-product-room" aria-live="polite" aria-labelledby="mew-product-room-title"><header><div><span>{department} · SELECTED PRODUCT ROOM</span><h3 id="mew-product-room-title">{name}</h3></div><Status state="NOT_ACTIVATED" /></header>
      <div className="mew-product-account"><article><strong>{name}</strong><Status state="UNAVAILABLE" label={`${name} evidence`} /><p className="mew-sleeve-label">Synthetic comparison basis — not deployable capital.</p><MetricGrid values={[["Starting basis", "$10,000"], ["Synthetic NAV", "$10,000"], ["Synthetic cash", "$10,000"], ["Modeled positions", 0], ["Modeled trades", 0], ["Exposure", classification], ["Realized result", null], ["Unrealized result", null], ["Fees", null], ["Spread", null], ["Slippage", null], ["Drawdown", null], ["Favorable excursion", null], ["Adverse excursion", null], ["Sample size", 0], ["Calibration", null], ["Evidence", "UNAVAILABLE"], ["Data source", "NOT ACTIVATED"], ["Research eligibility", false], ["Paper-research eligibility", false], ["Blocker", "AUTHENTIC PRODUCT EVIDENCE REQUIRED"], ["Next observation", "SEPARATELY AUTHORIZED SOURCE WAVE"]]} /></article></div>
      <details><summary>Assigned method desks — 16 visible, no ranking without outcomes</summary><div className="mew-method-desks">{methods.map((methodName) => <article key={methodName}><strong>{methodName}</strong><span>POINT-IN-TIME · COSTS · OUT-OF-SAMPLE · HUMAN REVIEW</span><Status state="INSUFFICIENT_SAMPLE" /><dl><div><dt>Product eligibility</dt><dd>CONTRACT REVIEW REQUIRED</dd></div><div><dt>Required evidence</dt><dd>PROVENANCE · COST MODEL</dd></div><div><dt>Holding period</dt><dd>METHOD SPECIFIC</dd></div><div><dt>Costs</dt><dd>FEES · SPREAD · SLIPPAGE</dd></div><div><dt>Invalidation</dt><dd>REQUIRED · NOT REPORTED</dd></div><div><dt>Benchmark</dt><dd>SIMPLE PRODUCT BENCHMARK</dd></div><div><dt>Minimum sample</dt><dd>20</dd></div><div><dt>Drawdown / calibration</dt><dd>NOT REPORTED</dd></div><div><dt>Ranking eligibility</dt><dd>FALSE</dd></div></dl></article>)}</div></details>
    </section>
    <div className="mew-grid mew-product-briefs"><article><strong>Macro Analyst</strong><p>Yield-curve movement remains unavailable until synchronized Treasury evidence supplies price, yield convention, duration and effective time.</p></article><article><strong>Sector Analyst</strong><p>Equity and ETF effects remain hypotheses; proxy performance cannot become underlying performance.</p></article><article><strong>Options Desk</strong><p>Missing Greeks or unsynchronized quotes return RESEARCH ONLY UNPRICEABLE.</p></article><article><strong>Skeptic / Red Team</strong><p>A professional-only thesis cannot promote a candidate.</p></article><article><strong>Risk Keeper</strong><p>A bond without duration or callable terms cannot pass inspection.</p></article><article><strong>Portfolio Office</strong><p>Synthetic $10,000 sleeves compare methods without touching operational cash.</p></article></div>
  </Panel>;
}

function CaseRegistry({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const source = section(snapshot, "governed_cases");
  const data = record(source?.data); const counts = record(data.counts); const cases = rows(data.cases); const mu = cases.find((item) => text(item.ticker, "") === "MU");
  return <Panel id="authenticated-case-registry" eyebrow="IMMUTABLE IDENTITIES ONLY" title="Authenticated Case Registry" state={source?.state ?? "UNAVAILABLE"} className="mew-wide"><p>Cases appear only from the authoritative browser-safe case read model. Universe, screener, promotion and receipt counts never create identities.</p><MetricGrid values={[["Total governed cases", data.total], ["Active", counts.active], ["Awaiting evidence", counts.awaiting_evidence], ["Committee", counts.committee], ["Risk", counts.risk], ["Rejected", counts.rejected], ["Closed", counts.closed], ["With outcomes", counts.with_outcomes], ["Without browser details", counts.without_browser_details], ["Source age seconds", data.source_age_seconds], ["Freshness", data.freshness_state], ["MU reference case", data.mu_case_state]]} />{mu ? <article className="mew-case-record"><strong>MU — {text(data.mu_case_state)}</strong><Status state={mu.status} /><MetricGrid values={[["Immutable case", mu.case_id], ["Stage", mu.stage], ["Evidence", mu.evidence_completeness], ["9H", mu.validation_9h_state], ["9I", mu.shadow_9i_state], ["9J", mu.outcome_9j_state], ["Committee", mu.committee_state], ["Risk", mu.risk_state], ["Paper eligible", mu.paper_eligibility], ["Position", mu.position_state], ["Outcome", mu.outcome_availability]]} /></article> : <div className="mew-machine-stop"><strong>MU CASE NOT RETURNED</strong><p>No authenticated immutable MU record is present. MU was not recreated from universe membership, aggregate counts, or receipts.</p></div>}<details><summary>Case safety contract and bounded records</summary><p>Allowed fields are bounded identity, timestamps, stage, summaries, validation/outcome states, decisions, blockers and sanitized receipt categories. Private 9I, prompts, provider bodies, credentials, paths and raw evidence are prohibited.</p><pre>{JSON.stringify(cases.slice(0, 40), null, 2)}</pre></details></Panel>;
}

function Conveyor({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const source = section(snapshot, "candidate_conveyor");
  const candidates = rows(record(source?.data).candidates).slice(0, 5);
  return <Panel id="candidate-conveyor" eyebrow="NINE CONTROLLED STAGES" title="Candidate Conveyor" state={source?.state} className="mew-wide"><ol className="mew-conveyor">{CONVEYOR_STAGES.map((stage, index) => <li key={stage}><b>{index + 1}</b><span>{stage}</span></li>)}</ol><div className="mew-machine-stop"><strong>{candidates.length ? `${candidates.length} lineage-authenticated crate${candidates.length === 1 ? "" : "s"}` : "MACHINERY STOPPED · NO AUTHENTICATED IDENTITIES"}</strong><p>{candidates.length ? "No stage implies approval; every crate retains immutable lineage." : "MAX: Aggregate counts cannot grow nameplates. The belt waits for current immutable lineage."}</p></div>{candidates.map((candidate) => <article className="mew-candidate" key={text(candidate.candidate_id)}><strong>{text(candidate.instrument_id, "UNKNOWN INSTRUMENT")}</strong><span>{text(candidate.asset_lane)}</span><code>{text(candidate.candidate_id)}</code></article>)}</Panel>;
}

function ProfessionalObservatory({ snapshot }: { snapshot: ExpansionSnapshot | null }) {
  const source = section(snapshot, "professional_strategy_observatory");
  const rows = [["Koyfin human cockpit", "UNAVAILABLE", "LICENSE REQUIRED"], ["Market Vision", "UNVERIFIED", "RIGHTS REVIEW REQUIRED"], ["Jesse interview research", "UNAVAILABLE", "CONSENT + APPROVED TRANSCRIPT"], ["Public manager commentary", "UNAVAILABLE", "SOURCE REVIEW REQUIRED"], ["Public portfolio observations", "UNAVAILABLE", "DISCLOSURE DELAY + PRIMARY VERIFICATION"], ["Public filings and interviews", "UNAVAILABLE", "RIGHTS + POINT-IN-TIME REVIEW"]] as const;
  return <Panel id="professional-observatory" eyebrow="ATTRIBUTED HYPOTHESES ONLY" title="Professional Research Observatory" state={source?.state} className="mew-wide"><p>Rights, disclosure delay, conflicts, attribution, corroboration, outcome follow-up and method extraction remain explicit. No observation independently creates a candidate, promotion, sleeve, position, recommendation, score, or order.</p><div className="mew-professional-grid">{rows.map(([name, state, blocker]) => <article key={name}><strong>{name}</strong><Status state={state} /><MetricGrid values={[["Blocker", blocker], ["Attributed hypothesis", true], ["Independent promotion", false], ["Score", null]]}/></article>)}</div></Panel>;
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
  const content = department === "overview" ? <><TuesdayCommandCenter snapshot={snapshot} /><CaseRegistry snapshot={snapshot} /><Overview snapshot={snapshot} /></> : department === "products" ? <MultiProductFloor fixtureMode={fixtureMode} /> : department === "trading" ? <TradingFloor snapshot={snapshot} /> : department === "conveyor" ? <Conveyor snapshot={snapshot} /> : department === "observatory" ? <ProfessionalObservatory snapshot={snapshot} /> : department === "laboratory" ? <div className="mew-grid"><ScalarRoom id="research-lab" eyebrow="HYPOTHESES · NOT POSITIONS" title="Independent Sleeve Laboratory" source="paper_research_sleeves" snapshot={snapshot} copy={SYNTHETIC_SLEEVE_LABEL} /><ScalarRoom id="pattern-lab" eyebrow="POINT-IN-TIME TESTING" title="Pattern Laboratory" source="outcomes_9j" snapshot={snapshot} copy="Correlation is not causality or proof of profitability. Insufficient authentic outcomes remain INSUFFICIENT SAMPLE." /></div> : department === "committee" ? <ScalarRoom id="committee-room" eyebrow="HUMAN-GATED DECISION" title="Cross-Asset Committee Chamber" source="committee" snapshot={snapshot} copy="No evidence advances automatically and no decision grants execution authority." /> : department === "risk" ? <ScalarRoom id="risk-inspection" eyebrow="CAPITAL PROTECTION" title="Multi-Product Risk Inspection" source="risk" snapshot={snapshot} copy="Missing product evidence, invalidation and authority locks remain binding." /> : department === "portfolio" ? <Overview snapshot={snapshot} /> : department === "learning" ? <div className="mew-grid"><ScalarRoom id="learning-theater" eyebrow="OUTCOMES · CALIBRATION" title="Outcome Learning Theater" source="outcomes_9j" snapshot={snapshot} copy="No new outcome means no score, lesson, or profitability claim." /><ScalarRoom id="post-close-room" eyebrow="TUESDAY RECONCILIATION" title="Post-Close Audit" source="benchmark_9h" snapshot={snapshot} copy="9H, natural 9I, authentic 9J and every unresolved sleeve must reconcile without touching operational paper." /></div> : department === "evidence" ? <div className="mew-grid"><CaseRegistry snapshot={snapshot} /><ScalarRoom id="evidence-warehouse" eyebrow="PROVENANCE FIRST" title="Evidence Warehouse" source="knowledge_operations" snapshot={snapshot} copy="Browser output contains counts and fixed states, never source text or private paths." /><ScalarRoom id="interview-studio" eyebrow="CONSENT REQUIRED" title="Interview Studio" source="cases" snapshot={snapshot} copy="No transcript or claim enters review without consent and professional approval." /></div> : <ControlRoom snapshot={snapshot} connection={connection} snapshotAgeSeconds={snapshotAgeSeconds} />;
  return <main className="mew-shell" aria-labelledby="mew-title"><header className="mew-masthead"><div><span>INTELLIGENCE IIOS FACTORY · EAST WORKS</span><h1 id="mew-title">THE EXPANSION WING</h1><p>One factory. Twenty-four product desks. Sixteen governed methods. Evidence moves; authority does not.</p></div><div><Status state={connection} label="Projection connection" /><strong>{fixtureMode ? "FIXTURE / NON-LIVE / RESEARCH ONLY" : "LIVE READ-ONLY"}</strong><small>{snapshotAgeSeconds == null ? "Snapshot age unavailable" : `Snapshot age ${snapshotAgeSeconds}s`}</small></div></header><nav className="mew-departments" aria-label="Expansion Wing departments">{UNIFIED_DEPARTMENTS.map((item) => <button key={item.key} type="button" aria-pressed={department === item.key} onClick={() => setDepartment(item.key)}><b>{item.code}</b><span>{item.label}</span></button>)}</nav><CharacterBriefing snapshot={snapshot} /><Feed snapshot={snapshot} />{content}<footer className="mew-footer">FAMILY RULES · SOURCE BEFORE STORY · STALE IS NOT INVALID · UNKNOWN IS NOT ZERO · NO BROKER · NO LIVE EXECUTION</footer></main>;
}

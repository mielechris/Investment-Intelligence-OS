import { useEffect, useMemo, useState, type CSSProperties } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import CinematicRoomScene, { type CinematicStation } from "./CinematicRoomScene";
import {
  LIVING_CAST,
  agentNarrativeForEvent,
  maxNarrativeForStation,
  type LivingCastKey,
} from "./livingCast";
import "./LivingFactorySpatialFloor.css";

type JsonObject = Record<string, unknown>;

type ValidationLayer = {
  availability: string;
  age_seconds?: number | null;
  payload?: JsonObject | null;
};

type DeskRow = {
  key: string;
  name?: string;
  recent_completions?: number;
};

type CaseRow = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  stage?: string;
  active_room?: string;
  latest_event?: string | null;
  agent_count?: number;
  committee?: string;
  risk?: string;
  paper_execution?: string;
};

type LivingSnapshot = {
  generated_at: string;
  validation: {
    layers: {
      factory_telemetry: ValidationLayer;
      outcome_learning: ValidationLayer;
    };
  };
  factory: {
    availability: string;
    payload?: {
      factory?: { desks?: DeskRow[] };
      cases?: CaseRow[];
    } | null;
  };
  safety: {
    backend_write_permission: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
};

type StationKey = "radar" | "research" | "agents" | "committee" | "risk" | "paper" | "monitoring" | "learning";
type PacketSource = "active_case" | "lineage";

type Packet = {
  key: string;
  ticker: string;
  label: string;
  caseId: string | null;
  stage: number;
  source: PacketSource;
};

const STATIONS = [
  { key: "radar" as const, code: "9E", title: "Radar Intake", subtitle: "519-name governed universe + candidate detection" },
  { key: "research" as const, code: "R", title: "Research Annex", subtitle: "Grok · Gemini · evidence resolution" },
  { key: "agents" as const, code: "8A", title: "Specialist Bullpen", subtitle: "Eight governed analyst desks" },
  { key: "committee" as const, code: "IC", title: "Committee Chamber", subtitle: "Final governed synthesis" },
  { key: "risk" as const, code: "RK", title: "Risk Inspection", subtitle: "Deterministic capital gate" },
  { key: "paper" as const, code: "P", title: "Paper Execution Bay", subtitle: "Paper-only execution" },
  { key: "monitoring" as const, code: "M", title: "Monitoring Office", subtitle: "Thesis + portfolio surveillance" },
  { key: "learning" as const, code: "9J", title: "Outcome Learning", subtitle: "Exact lineage + judgment memory" },
];

const AGENTS = [
  LIVING_CAST.policy,
  LIVING_CAST.macro,
  LIVING_CAST.fundamentals,
  LIVING_CAST.market_structure,
  LIVING_CAST.commodities,
  LIVING_CAST.geo_weather,
  LIVING_CAST.skeptic,
  LIVING_CAST.portfolio,
] as const;

const AGENT_ALIAS = new Map<string, LivingCastKey>([
  ["policy", "policy"], ["policy analyst", "policy"],
  ["macro", "macro"], ["macro & rates", "macro"], ["macro & rates analyst", "macro"],
  ["fundamentals", "fundamentals"], ["fundamentals analyst", "fundamentals"],
  ["market_structure", "market_structure"], ["market structure", "market_structure"], ["market structure analyst", "market_structure"],
  ["commodities", "commodities"], ["commodities & supply chain analyst", "commodities"],
  ["geo_weather", "geo_weather"], ["geo + weather", "geo_weather"], ["geopolitics & weather analyst", "geo_weather"],
  ["skeptic", "skeptic"], ["red team", "skeptic"], ["skeptic / red team", "skeptic"],
  ["portfolio", "portfolio"], ["portfolio context", "portfolio"], ["portfolio context analyst", "portfolio"],
]);

function record(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function rows(value: unknown): JsonObject[] {
  return Array.isArray(value)
    ? value.filter((item): item is JsonObject => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function text(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function money(value: unknown): string {
  const numeric = numberValue(value);
  return numeric === null ? "—" : numeric.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function timeLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "WAITING";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "WAITING";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function ageLabel(value?: number | null): string {
  if (value === undefined || value === null) return "warm-up";
  if (value < 60) return `${value}s`;
  if (value < 3600) return `${Math.floor(value / 60)}m`;
  return `${Math.floor(value / 3600)}h`;
}

function normalized(value: unknown): string {
  return text(value, "").trim().toUpperCase();
}

function resolved(value: unknown): boolean {
  const state = normalized(value);
  return Boolean(state) && !["WAITING", "UNKNOWN", "NONE", "NO_STATE", "NOT_STARTED", "PENDING", "NOT_EXECUTED"].includes(state);
}

function stationForEvent(eventType: string): StationKey | null {
  const type = eventType.toUpperCase();
  if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) return "learning";
  if (type.includes("MONITOR") || type.includes("PORTFOLIO") || type.includes("THESIS")) return "monitoring";
  if (type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) return "paper";
  if (type.includes("RISK")) return "risk";
  if (type.includes("COMMITTEE") || type.includes("DECISION")) return "committee";
  if (type.includes("AGENT")) return "agents";
  if (type.includes("RESEARCH") || type.includes("EVIDENCE") || type.includes("INGEST")) return "research";
  if (type.includes("RADAR") || type.includes("CANDIDATE") || type.includes("OPPORTUNITY") || type.includes("PROMOT")) return "radar";
  return null;
}

function normalizeAgentKey(value: unknown): LivingCastKey | null {
  if (typeof value !== "string") return null;
  const normalizedValue = value.trim().toLowerCase().replaceAll("-", "_");
  return AGENT_ALIAS.get(normalizedValue) ?? null;
}

function agentKeysFromEvent(event: JsonObject | null): Set<LivingCastKey> {
  const found = new Set<LivingCastKey>();
  if (!event) return found;
  const payload = record(event.payload);
  const scalarCandidates = [
    payload.agent_key,
    payload.agent,
    payload.agent_name,
    payload.specialist,
    payload.speaker_key,
    event.entity_id,
  ];
  scalarCandidates.forEach((candidate) => {
    const key = normalizeAgentKey(candidate);
    if (key && key !== "max") found.add(key);
  });
  [payload.agent_keys, payload.agents, payload.specialists].forEach((candidate) => {
    if (!Array.isArray(candidate)) return;
    candidate.forEach((item) => {
      const key = normalizeAgentKey(item);
      if (key && key !== "max") found.add(key);
    });
  });
  return found;
}

function stageFromCase(row: CaseRow): number {
  const state = `${row.stage ?? ""} ${row.active_room ?? ""} ${row.latest_event ?? ""}`.toUpperCase();
  if (state.includes("LEARN") || state.includes("OUTCOME") || state.includes("JUDGMENT")) return 7;
  if (state.includes("MONITOR") || state.includes("PORTFOLIO") || state.includes("THESIS")) return 6;
  if (resolved(row.paper_execution) || state.includes("PAPER") || state.includes("EXECUTION")) return 5;
  if (resolved(row.risk) || state.includes("RISK")) return 4;
  if (resolved(row.committee) || state.includes("COMMITTEE")) return 3;
  if ((row.agent_count ?? 0) > 0 || state.includes("AGENT")) return 2;
  if (state.includes("RESEARCH") || state.includes("EVIDENCE")) return 1;
  return 0;
}

function stageFromPromotion(promotion: JsonObject): number {
  const paper = record(promotion.paper_execution);
  const risk = record(promotion.risk);
  const committee = record(promotion.committee);
  const agents = record(promotion.agents);
  if (resolved(paper.execution)) return 5;
  if (resolved(risk.decision)) return 4;
  if (resolved(committee.disposition)) return 3;
  if ((numberValue(agents.completed_count) ?? 0) > 0) return 2;
  return 1;
}

async function sameOriginJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store", signal });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `IIOS sidecar request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export default function LivingFactorySpatialFloor() {
  const [snapshot, setSnapshot] = useState<LivingSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [beat, setBeat] = useState(0);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await sameOriginJson<LivingSnapshot>("/living/overview", controller.signal);
        if (disposed) return;
        setSnapshot(next);
        setError(null);
        setBeat((value) => value + 1);
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "Living factory sidecar unavailable");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, []);

  const model = useMemo(() => {
    if (!snapshot) return null;
    const telemetryLayer = snapshot.validation.layers.factory_telemetry;
    const telemetry = record(telemetryLayer.payload);
    const radar = record(telemetry.radar);
    const fund = record(telemetry.paper_fund);
    const events = rows(telemetry.recent_meaningful_events);
    const promotions = rows(telemetry.recent_promotions).slice(0, 12);
    const cases = snapshot.factory.payload?.cases ?? [];
    const activeCaseIds = new Set(cases.map((row) => row.case_id));
    const desks = snapshot.factory.payload?.factory?.desks ?? [];
    const deskByKey = new Map(desks.map((desk) => [desk.key, desk]));

    const stationEventCounts: Record<StationKey, number> = { radar: 0, research: 0, agents: 0, committee: 0, risk: 0, paper: 0, monitoring: 0, learning: 0 };
    for (const event of events) {
      const station = stationForEvent(text(event.event_type, ""));
      if (station) stationEventCounts[station] += 1;
    }

    const packets: Packet[] = [];
    const activeSeen = new Set<string>();
    promotions.forEach((promotion, index) => {
      const caseId = text(promotion.case_id, "").trim() || null;
      const ticker = text(promotion.ticker, "NO TICKER").toUpperCase();
      const source: PacketSource = caseId && activeCaseIds.has(caseId) ? "active_case" : "lineage";
      packets.push({
        key: `${source}:${caseId ?? ticker}:${index}`,
        ticker,
        label: text(promotion.topic, ticker),
        caseId,
        stage: stageFromPromotion(promotion),
        source,
      });
      if (source === "active_case" && caseId) activeSeen.add(caseId);
    });
    for (const row of cases) {
      if (activeSeen.has(row.case_id)) continue;
      packets.push({ key: `active:${row.case_id}`, ticker: text(row.ticker, "CASE").toUpperCase(), label: row.topic ?? row.case_id, caseId: row.case_id, stage: stageFromCase(row), source: "active_case" });
    }

    const outcomePayload = record(snapshot.validation.layers.outcome_learning.payload);
    const outcomeCount = numberValue(outcomePayload.outcome_count) ?? rows(outcomePayload.recent_outcomes).length;
    const latestEvent = events[0] ?? null;
    const latestEventType = latestEvent ? text(latestEvent.event_type, "UNKNOWN_EVENT") : "NO_PERSISTED_EVENT";
    const latestStation = stationForEvent(latestEventType);
    const latestAgentKeys = agentKeysFromEvent(latestEvent);

    const lineageByStation: Record<StationKey, boolean> = {
      radar: (numberValue(radar.screener_hit_count) ?? 0) > 0,
      research: packets.some((packet) => packet.stage >= 1),
      agents: packets.some((packet) => packet.stage >= 2),
      committee: packets.some((packet) => packet.stage >= 3),
      risk: packets.some((packet) => packet.stage >= 4),
      paper: packets.some((packet) => packet.stage >= 5),
      monitoring: false,
      learning: outcomeCount > 0,
    };

    const activeByStation: Record<StationKey, boolean> = {
      radar: false,
      research: cases.some((row) => stageFromCase(row) >= 1),
      agents: desks.some((desk) => (desk.recent_completions ?? 0) > 0) || cases.some((row) => (row.agent_count ?? 0) > 0),
      committee: cases.some((row) => resolved(row.committee)),
      risk: cases.some((row) => resolved(row.risk)),
      paper: cases.some((row) => resolved(row.paper_execution)) || (numberValue(fund.position_count) ?? 0) > 0,
      monitoring: cases.some((row) => stageFromCase(row) >= 6),
      learning: outcomeCount > 0,
    };

    const lineageAgentKeys = new Set<string>();
    for (const promotion of promotions) {
      const keys = record(promotion.agents).agent_keys;
      if (Array.isArray(keys)) keys.forEach((key) => lineageAgentKeys.add(String(key)));
    }

    return {
      telemetryLayer,
      radar,
      fund,
      events,
      latestEvent,
      latestEventType,
      latestStation,
      latestAgentKeys,
      stationEventCounts,
      packets: packets.slice(0, 10),
      cases,
      deskByKey,
      lineageAgentKeys,
      activeByStation,
      lineageByStation,
      outcomeCount,
    };
  }, [snapshot]);

  if (!snapshot || !model) {
    return <section className="spatial-shell spatial-loading"><div><span>9L-V2.5 · LIVING CAST SUPERBATCH</span><h1>{error ? "SIDECAR WARM-UP" : "OPENING FACTORY"}</h1><p>{error ?? "Connecting to persisted IIOS state…"}</p></div></section>;
  }

  const universe = text(model.radar.governed_universe_count, "0");
  const hits = text(model.radar.screener_hit_count, "0");
  const nav = money(model.fund.nav);
  const positions = text(model.fund.position_count, "0");
  const latestPayload = model.latestEvent ? record(model.latestEvent.payload) : {};
  const latestTicker = text(latestPayload.ticker, "").toUpperCase();
  const latestCase = model.latestEvent ? text(model.latestEvent.case_id, "") : "";
  const latestStationCode = model.latestStation ? STATIONS.find((item) => item.key === model.latestStation)?.code ?? "SYS" : "SYS";
  const maxNarrative = maxNarrativeForStation(model.latestStation, model.latestEventType);

  const roomState = (key: StationKey) => {
    if (model.stationEventCounts[key] > 0) return "RECENT EVENT";
    if (model.activeByStation[key]) return "ACTIVE STATE";
    if (model.lineageByStation[key]) return "PERSISTED LINEAGE";
    return "WAITING";
  };

  return (
    <section className="spatial-shell v25-shell">
      <div className="spatial-grid-glow" aria-hidden="true" />
      <header className="spatial-hero">
        <div><span>9L-V2.5 · LIVING CAST SUPERBATCH · PERSISTED STATE ONLY</span><h1>THE INVESTMENT FACTORY</h1><p>Full recurring cast avatars, living workstations and narrative reactions now sit on top of the same governed IIOS state. Character motion is presentation only; substantive activity still requires persisted evidence.</p></div>
        <div className="spatial-heartbeat"><i className={beat % 2 ? "is-beat" : ""} /><span>FACTORY HEARTBEAT</span><strong>{model.telemetryLayer.availability.replaceAll("_", " ")}</strong><em>9G age {ageLabel(model.telemetryLayer.age_seconds)}</em></div>
      </header>

      <div className="spatial-truth"><span>LIVE EXECUTION · {snapshot.safety.live_execution ? "TRUE" : "FALSE"}</span><span>WRITE PERMISSION · {snapshot.safety.backend_write_permission ? "TRUE" : "NONE"}</span><span>TRADE PERMISSION · {snapshot.safety.trade_execution_permission ? "TRUE" : "FALSE"}</span><span>NARRATIVE ≠ RAW MODEL OUTPUT</span></div>

      <section className="spatial-metrics">
        <article><span>Market Universe</span><strong>{universe}</strong><em>persisted 9G</em></article>
        <article><span>9E Radar Hits</span><strong>{hits}</strong><em>current snapshot</em></article>
        <article><span>Recent Events</span><strong>{model.events.length}</strong><em>full 9G window</em></article>
        <article><span>Governed Cases</span><strong>{model.cases.length}</strong><em>backend objects</em></article>
        <article><span>Paper NAV</span><strong>{nav}</strong><em>{positions} positions</em></article>
        <article><span>9J Outcomes</span><strong>{model.outcomeCount}</strong><em>exact lineage</em></article>
      </section>

      <section className="spatial-now">
        <div className="spatial-now-pulse"><i /></div><span>NOW HAPPENING</span><strong>{model.latestEventType.replaceAll("_", " ")}</strong><em>{latestStationCode} · {[latestTicker, latestCase].filter(Boolean).join(" · ") || "persisted system event"}</em><time>{model.latestEvent ? timeLabel(model.latestEvent.created_at) : "WAITING"}</time>
      </section>

      <section className="spatial-factory" aria-label="Spatial Investment Factory">
        <div className="spatial-corridors" aria-hidden="true"><i /><i /><i /><i /></div>
        {STATIONS.filter((station) => station.key !== "agents").map((station) => (
          <article key={station.key} className={`spatial-room room-${station.key} ${model.stationEventCounts[station.key] ? "is-event" : ""} ${model.activeByStation[station.key] ? "is-active" : ""} ${model.lineageByStation[station.key] ? "has-lineage" : ""}`}>
            <header><span>{station.code}</span><i /></header>
            <CinematicRoomScene
              station={station.key as CinematicStation}
              active={Boolean(model.stationEventCounts[station.key] || model.activeByStation[station.key])}
              eventCount={model.stationEventCounts[station.key]}
            />
            <strong>{station.title}</strong>
            <p>{station.subtitle}</p>
            <div className="spatial-room-meter"><i style={{ width: `${Math.min(100, model.stationEventCounts[station.key] * 16)}%` }} /></div>
            <footer>{model.stationEventCounts[station.key] ? `${model.stationEventCounts[station.key]} EVENT${model.stationEventCounts[station.key] === 1 ? "" : "S"} · ` : ""}{roomState(station.key)}</footer>
          </article>
        ))}

        <aside className="spatial-max-platform v25-max-platform">
          <CinematicCharacterPortrait characterKey="max" active={Boolean(model.latestEvent)} reacting={Boolean(model.latestEvent)} variant="boss" />
          <div className="v25-max-copy">
            <em>MAX · FACTORY FOREMAN · COMMAND OVERLOOK</em>
            <h2>MAX</h2>
            <p>{model.events.length ? `${model.events.length} persisted meaningful events in the current 9G window. Latest: ${model.latestEventType.replaceAll("_", " ")}.` : "Factory floor in governed idle mode."}</p>
            <small>Presentation only · no trade or backend authority</small>
          </div>
          {model.latestEvent ? (
            <div className="spatial-max-narrative">
              <span>NARRATIVE</span>
              <strong>{maxNarrative}</strong>
              <em>Basis · persisted {model.latestEventType.replaceAll("_", " ")} · {latestStationCode}</em>
            </div>
          ) : null}
        </aside>

        <article className={`spatial-bullpen room-agents ${model.stationEventCounts.agents ? "is-event" : ""} ${model.activeByStation.agents ? "is-active" : ""} ${model.lineageByStation.agents ? "has-lineage" : ""}`}>
          <header className="spatial-bullpen-heading"><div><span>8A</span><strong>SPECIALIST BULLPEN</strong></div><em>{roomState("agents")}</em></header>
          <div className="spatial-agent-desks v25-agent-desks">
            {AGENTS.map((agent, index) => {
              const desk = model.deskByKey.get(agent.key);
              const completions = desk?.recent_completions ?? 0;
              const lineageObserved = model.lineageAgentKeys.has(agent.key);
              const reacting = model.latestStation === "agents" && model.latestAgentKeys.has(agent.key);
              const working = completions > 0;
              const status = reacting
                ? `PERSISTED AGENT EVENT · ${model.latestEventType.replaceAll("_", " ")}`
                : working
                  ? `${completions} backend completion(s)`
                  : lineageObserved
                    ? "PERSISTED LINEAGE OBSERVED"
                    : "WAITING";
              return (
                <article
                  key={agent.key}
                  data-cast-key={agent.key}
                  className={`spatial-desk v25-desk ${working ? "is-on" : ""} ${lineageObserved ? "has-lineage" : ""} ${reacting ? "is-reacting" : ""}`}
                  style={{ "--desk-delay": `${index * 0.08}s` } as CSSProperties}
                >
                  <CinematicCharacterPortrait characterKey={agent.key} active={working || reacting} reacting={reacting} variant="desk" />
                  <div className="spatial-desk-copy v25-desk-copy">
                    <em>{agent.title}</em>
                    <strong>{agent.displayName}</strong>
                    <span className="v25-governed-role">{agent.governedRole}</span>
                    <small>{status}</small>
                    <div className="v25-workstation-props">{agent.workstation}</div>
                    <div className="v25-persona"><span>NARRATIVE PERSONA</span>{agent.personaLine}</div>
                  </div>
                  {reacting ? (
                    <div className="spatial-desk-reaction">
                      <span>NARRATIVE</span>
                      <strong>{agentNarrativeForEvent(agent.key, model.latestEventType)}</strong>
                      <em>Basis · exact persisted agent-stage event</em>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </article>

        <div className="spatial-packets" aria-label="Persisted case and lineage packets">
          {model.packets.map((packet, index) => {
            const station = STATIONS[packet.stage] ?? STATIONS[0];
            return <div key={packet.key} className={`spatial-packet packet-${station.key} ${packet.source === "active_case" ? "is-active-case" : "is-lineage"}`} style={{ "--packet-delay": `${index * 0.1}s` } as CSSProperties} title={packet.source === "active_case" ? `${packet.label} · current governed case` : `${packet.label} · persisted lineage`}><span>{packet.source === "active_case" ? "ACTIVE" : "LINEAGE"}</span><strong>{packet.ticker}</strong><em>{station.code}</em></div>;
          })}
        </div>
      </section>

      <section className="spatial-bottom">
        <div className="spatial-legend"><span><i className="active" /> ACTIVE CASE</span><span><i className="lineage" /> PERSISTED LINEAGE</span><span><i className="event" /> RECENT EVENT</span></div>
        <aside className="spatial-radio"><header><div><span>FACTORY RADIO</span><strong>Latest persisted events</strong></div><i /></header><div>{model.events.slice(0, 8).map((event, index) => { const eventType = text(event.event_type, "UNKNOWN_EVENT"); const station = stationForEvent(eventType); const payload = record(event.payload); return <article key={`${eventType}:${index}`}><time>{timeLabel(event.created_at)}</time><em>{station ? STATIONS.find((item) => item.key === station)?.code : "SYS"}</em><strong>{eventType.replaceAll("_", " ")}</strong><span>{[text(payload.ticker, ""), text(event.case_id, "")].filter(Boolean).join(" · ") || "persisted system event"}</span></article>; })}</div><footer>Showing {Math.min(8, model.events.length)} of {model.events.length} · poll 5s</footer></aside>
      </section>

      {error ? <div className="spatial-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}

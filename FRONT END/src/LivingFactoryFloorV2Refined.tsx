import { useEffect, useMemo, useState, type CSSProperties } from "react";
import "./LivingFactoryFloorV2.css";
import "./LivingFactoryFloorV2Refined.css";

type JsonObject = Record<string, unknown>;

type ValidationLayer = {
  availability: string;
  age_seconds?: number | null;
  payload?: JsonObject | null;
};

type DeskRow = {
  key: string;
  name?: string;
  room?: string;
  status?: string;
  recent_completions?: number;
};

type CaseRow = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  stage?: string;
  active_room?: string;
  latest_event?: string | null;
  latest_event_at?: string | null;
  agent_count?: number;
  committee?: string;
  risk?: string;
  paper_execution?: string;
};

type FactoryOverview = {
  factory?: { desks?: DeskRow[] };
  cases?: CaseRow[];
};

type LivingSnapshot = {
  generated_at: string;
  validation: {
    layers: {
      factory_telemetry: ValidationLayer;
      market_validation: ValidationLayer;
      shadow_strategy: ValidationLayer;
      outcome_learning: ValidationLayer;
    };
  };
  factory: {
    availability: string;
    payload?: FactoryOverview | null;
  };
  safety: {
    direct_ledger_access: boolean;
    backend_write_permission: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
};

type StationKey =
  | "radar"
  | "research"
  | "agents"
  | "committee"
  | "risk"
  | "paper"
  | "monitoring"
  | "learning";

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
  { key: "radar" as const, code: "9E", title: "Radar Intake", subtitle: "Market universe + candidate detection" },
  { key: "research" as const, code: "R", title: "Research Annex", subtitle: "Evidence + 24/7 research intake" },
  { key: "agents" as const, code: "8A", title: "Specialist Desks", subtitle: "Eight governed analyst roles" },
  { key: "committee" as const, code: "IC", title: "Committee Room", subtitle: "Investment committee disposition" },
  { key: "risk" as const, code: "RK", title: "Risk Inspection", subtitle: "Deterministic capital gate" },
  { key: "paper" as const, code: "P", title: "Paper Execution Bay", subtitle: "Paper-only governed execution" },
  { key: "monitoring" as const, code: "M", title: "Monitoring Office", subtitle: "Thesis + portfolio surveillance" },
  { key: "learning" as const, code: "9J", title: "Outcome Learning", subtitle: "Exact lineage + judgment memory" },
];

const AGENTS = [
  { key: "policy", name: "Policy Analyst", title: "Regulatory Bloodhound", monogram: "PA" },
  { key: "macro", name: "Macro & Rates", title: "Regime Obsessive", monogram: "MR" },
  { key: "fundamentals", name: "Fundamentals", title: "Numbers Before Vibes", monogram: "FA" },
  { key: "market_structure", name: "Market Structure", title: "Tape Reader", monogram: "MS" },
  { key: "commodities", name: "Commodities", title: "Physical-World Realist", monogram: "CS" },
  { key: "geo_weather", name: "Geo + Weather", title: "Scenario Disciplinarian", monogram: "GW" },
  { key: "skeptic", name: "Skeptic / Red Team", title: "Professional Buzzkill", monogram: "RT" },
  { key: "portfolio", name: "Portfolio Context", title: "Risk-Adjusted Adult", monogram: "PC" },
] as const;

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
  return numeric === null
    ? "—"
    : numeric.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
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
  return Boolean(state) && ![
    "WAITING",
    "UNKNOWN",
    "NONE",
    "NO_STATE",
    "NOT_STARTED",
    "PENDING",
    "NOT_EXECUTED",
  ].includes(state);
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

export default function LivingFactoryFloorV2Refined() {
  const [snapshot, setSnapshot] = useState<LivingSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshBeat, setRefreshBeat] = useState(0);

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
        setRefreshBeat((value) => value + 1);
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
    const allEvents = rows(telemetry.recent_meaningful_events);
    const eventRows = allEvents.slice(0, 10);
    const promotions = rows(telemetry.recent_promotions).slice(0, 12);
    const cases = snapshot.factory.payload?.cases ?? [];
    const activeCaseIds = new Set(cases.map((row) => row.case_id));
    const desks = snapshot.factory.payload?.factory?.desks ?? [];
    const deskByKey = new Map(desks.map((desk) => [desk.key, desk]));

    const stationEventCounts: Record<StationKey, number> = {
      radar: 0,
      research: 0,
      agents: 0,
      committee: 0,
      risk: 0,
      paper: 0,
      monitoring: 0,
      learning: 0,
    };
    const recentStationKeys = new Set<StationKey>();
    for (const event of allEvents) {
      const key = stationForEvent(text(event.event_type, ""));
      if (!key) continue;
      recentStationKeys.add(key);
      stationEventCounts[key] += 1;
    }

    const latestEvent = allEvents[0] ?? null;
    const latestEventType = latestEvent ? text(latestEvent.event_type, "UNKNOWN_EVENT") : "NO_PERSISTED_EVENT";
    const latestEventPayload = latestEvent ? record(latestEvent.payload) : {};
    const latestStation = stationForEvent(latestEventType);

    const outcomePayload = record(snapshot.validation.layers.outcome_learning.payload);
    const outcomeCount = numberValue(outcomePayload.outcome_count) ?? rows(outcomePayload.recent_outcomes).length;
    const agentCompletions = desks.reduce((sum, desk) => sum + (desk.recent_completions ?? 0), 0);

    const packets: Packet[] = [];
    const seenActiveCases = new Set<string>();

    promotions.forEach((promotion, index) => {
      const caseId = text(promotion.case_id, "").trim() || null;
      const ticker = text(promotion.ticker, "NO TICKER").toUpperCase();
      const candidateId = text(promotion.source_candidate_id, ticker);
      const active = Boolean(caseId && activeCaseIds.has(caseId));
      const source: PacketSource = active ? "active_case" : "lineage";
      const stamp = text(promotion.promoted_at ?? promotion.created_at, String(index));
      packets.push({
        key: `${source}:${caseId ?? candidateId}:${stamp}:${index}`,
        ticker,
        label: text(promotion.topic, ticker),
        caseId,
        stage: stageFromPromotion(promotion),
        source,
      });
      if (active && caseId) seenActiveCases.add(caseId);
    });

    for (const row of cases) {
      if (seenActiveCases.has(row.case_id)) continue;
      packets.push({
        key: `active:${row.case_id}`,
        ticker: text(row.ticker, "CASE").toUpperCase(),
        label: row.topic ?? row.case_id,
        caseId: row.case_id,
        stage: stageFromCase(row),
        source: "active_case",
      });
    }

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
      agents: agentCompletions > 0 || cases.some((row) => (row.agent_count ?? 0) > 0),
      committee: cases.some((row) => resolved(row.committee)),
      risk: cases.some((row) => resolved(row.risk)),
      paper: cases.some((row) => resolved(row.paper_execution)) || (numberValue(fund.position_count) ?? 0) > 0,
      monitoring: cases.some((row) => stageFromCase(row) >= 6),
      learning: outcomeCount > 0,
    };

    const activeAgentKeys = new Set<string>();
    for (const promotion of promotions) {
      const keys = record(promotion.agents).agent_keys;
      if (!Array.isArray(keys)) continue;
      for (const key of keys) activeAgentKeys.add(String(key));
    }

    return {
      telemetryLayer,
      radar,
      fund,
      eventRows,
      eventCount: allEvents.length,
      latestEvent,
      latestEventType,
      latestEventPayload,
      latestStation,
      stationEventCounts,
      cases,
      deskByKey,
      recentStationKeys,
      lineageByStation,
      activeByStation,
      packets: packets.slice(0, 10),
      activeAgentKeys,
      outcomeCount,
    };
  }, [snapshot]);

  if (!snapshot || !model) {
    return (
      <section className="lv2-shell lv2-shell--loading">
        <div className="lv2-loading-card">
          <span>FACTORY FLOOR V2 · READ-ONLY EXPERIENCE</span>
          <h1>{error ? "SIDECAR WARM-UP" : "OPENING THE FACTORY FLOOR"}</h1>
          <p>{error ?? "Connecting to persisted IIOS state…"}</p>
        </div>
      </section>
    );
  }

  const hitCount = text(model.radar.screener_hit_count, "0");
  const universe = text(model.radar.governed_universe_count, "0");
  const positionCount = text(model.fund.position_count, "0");
  const nav = money(model.fund.nav);
  const latestTicker = text(model.latestEventPayload.ticker, "").toUpperCase();
  const latestCaseId = model.latestEvent ? text(model.latestEvent.case_id, "") : "";
  const latestStationCode = model.latestStation
    ? STATIONS.find((station) => station.key === model.latestStation)?.code ?? "SYS"
    : "SYS";

  return (
    <section className="lv2-shell lv2r-shell">
      <div className="lv2-ambient-grid" aria-hidden="true" />
      <div className="lv2-scanline" aria-hidden="true" />

      <header className="lv2-hero lv2r-hero">
        <div>
          <span>9L-V2 · VISUAL REFINEMENT · PERSISTED STATE ONLY</span>
          <h1>WELCOME TO THE INVESTMENT FACTORY</h1>
          <p>
            Real IIOS state drives rooms, workers, packet lineage and event lighting. Cosmetic motion can breathe; substantive activity still requires persisted evidence.
          </p>
        </div>
        <div className="lv2-master-status">
          <div className={`lv2-heartbeat ${refreshBeat % 2 ? "is-beat" : ""}`} aria-hidden="true" />
          <div>
            <span>FACTORY HEARTBEAT</span>
            <strong>{model.telemetryLayer.availability.replaceAll("_", " ")}</strong>
            <em>9G age {ageLabel(model.telemetryLayer.age_seconds)} · refreshed {timeLabel(snapshot.generated_at)}</em>
          </div>
        </div>
      </header>

      <div className="lv2-truth-rail">
        <span>LIVE EXECUTION · {snapshot.safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>WRITE PERMISSION · {snapshot.safety.backend_write_permission ? "TRUE" : "NONE"}</span>
        <span>TRADE PERMISSION · {snapshot.safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>AMBIENT MOTION ≠ MARKET EVENT</span>
      </div>

      <section className={`lv2r-now ${model.latestEvent ? "has-event" : ""}`} aria-label="Latest persisted factory event">
        <div className="lv2r-now-pulse" aria-hidden="true"><i /></div>
        <div className="lv2r-now-label"><span>NOW HAPPENING</span><strong>{latestStationCode}</strong></div>
        <div className="lv2r-now-event">
          <strong>{model.latestEventType.replaceAll("_", " ")}</strong>
          <span>{[latestTicker, latestCaseId].filter(Boolean).join(" · ") || "Persisted system event"}</span>
        </div>
        <time>{model.latestEvent ? timeLabel(model.latestEvent.created_at) : "WAITING"}</time>
      </section>

      <section className="lv2-metrics" aria-label="Factory summary">
        <article><span>Market Universe</span><strong>{universe}</strong><em>persisted 9G</em></article>
        <article><span>9E Radar Hits</span><strong>{hitCount}</strong><em>current persisted snapshot</em></article>
        <article><span>Recent Events</span><strong>{model.eventCount}</strong><em>full meaningful 9G window</em></article>
        <article><span>Governed Cases</span><strong>{model.cases.length}</strong><em>current backend case objects</em></article>
        <article><span>Paper NAV</span><strong>{nav}</strong><em>{positionCount} positions</em></article>
        <article><span>9J Outcomes</span><strong>{model.outcomeCount}</strong><em>exact learning lineage</em></article>
      </section>

      <section className="lv2-floor-scene lv2r-floor-scene">
        <div className="lv2-scene-heading">
          <div><span>PRODUCTION LINE</span><h2>Persisted intelligence moves room to room</h2></div>
          <div className="lv2r-legends">
            <span><i className="lv2r-legend-active" /> active case</span>
            <span><i className="lv2r-legend-lineage" /> persisted lineage</span>
          </div>
        </div>

        <div className="lv2-station-grid">
          {STATIONS.map((station, index) => {
            const recentEvent = model.recentStationKeys.has(station.key);
            const activeState = model.activeByStation[station.key];
            const lineageState = model.lineageByStation[station.key];
            const eventCount = model.stationEventCounts[station.key];
            const state = recentEvent ? "RECENT EVENT" : activeState ? "ACTIVE STATE" : lineageState ? "PERSISTED LINEAGE" : "WAITING";
            return (
              <article
                className={`lv2-station ${recentEvent ? "is-event" : ""} ${activeState ? "has-state" : ""} ${lineageState && !activeState ? "has-lineage" : ""}`}
                key={station.key}
                style={{ "--station-delay": `${index * 0.12}s` } as CSSProperties}
              >
                <header><span>{station.code}</span><i className="lv2-station-light" aria-hidden="true" /></header>
                <strong>{station.title}</strong>
                <p>{station.subtitle}</p>
                <div className="lv2r-station-meter" aria-hidden="true"><i style={{ width: `${Math.min(100, eventCount * 18)}%` }} /></div>
                <footer>{eventCount ? `${eventCount} EVENT${eventCount === 1 ? "" : "S"} · ` : ""}{state}</footer>
              </article>
            );
          })}
        </div>

        <div className="lv2-conveyor" aria-label="Case and lineage packet conveyor">
          <div className="lv2-conveyor-track" aria-hidden="true"><div className="lv2-conveyor-motion" /></div>
          <div className="lv2-stage-labels">{STATIONS.map((station) => <span key={station.key}>{station.code}</span>)}</div>
          <div className="lv2-packet-grid">
            {model.packets.map((packet, index) => (
              <button
                className={`lv2-packet ${packet.source === "active_case" ? "is-active-case" : "is-lineage"}`}
                key={packet.key}
                type="button"
                title={packet.source === "active_case"
                  ? `${packet.label} · current governed case ${packet.caseId ?? ""}`
                  : `${packet.label} · persisted promotion lineage${packet.caseId ? ` · historical case id ${packet.caseId}` : ""}`}
                style={{ gridColumn: packet.stage + 1, "--packet-delay": `${index * 0.08}s` } as CSSProperties}
              >
                <span>{packet.source === "active_case" ? "ACTIVE CASE" : "LINEAGE"}</span>
                <strong>{packet.ticker}</strong>
                <em>{STATIONS[packet.stage]?.code ?? "9E"}</em>
              </button>
            ))}
            {!model.packets.length ? (
              <div className="lv2-empty-conveyor"><strong>CONVEYOR IDLE</strong><span>No persisted promotion or governed case is available to move.</span></div>
            ) : null}
          </div>
        </div>
      </section>

      <section className="lv2-people-and-tape">
        <div className="lv2-character-floor">
          <div className="lv2-character-heading">
            <div><span>FACTORY CREW</span><h2>MAX + eight specialist desks</h2></div>
            <span className="lv2-no-fiction">NARRATIVE ≠ RAW MODEL OUTPUT</span>
          </div>

          <div className="lv2-max-row lv2r-max-row">
            <div className="lv2-max-figure" aria-hidden="true">
              <div className="lv2-max-ears"><i /><i /></div><div className="lv2-max-head">M</div><div className="lv2-max-body">MAX</div>
            </div>
            <div className="lv2-max-copy">
              <span>FACTORY FOREMAN</span><strong>MAX</strong>
              <p>{model.eventCount
                ? `${model.eventCount} persisted meaningful event(s) are in the current 9G window. Latest: ${model.latestEventType.replaceAll("_", " ")}.`
                : "No persisted meaningful event is visible in the current 9G window. The floor remains in governed idle mode."}</p>
              <em>Presentation layer only. MAX cannot create trades, decisions or backend state.</em>
            </div>
          </div>

          <div className="lv2-agent-grid">
            {AGENTS.map((agent, index) => {
              const desk = model.deskByKey.get(agent.key);
              const completions = desk?.recent_completions ?? 0;
              const lineageObserved = model.activeAgentKeys.has(agent.key);
              const active = completions > 0 || lineageObserved;
              return (
                <article className={`lv2-agent ${active ? "is-active" : ""}`} key={agent.key} style={{ "--agent-delay": `${index * 0.09}s` } as CSSProperties}>
                  <div className="lv2-agent-avatar"><span>{agent.monogram}</span><i aria-hidden="true" /></div>
                  <div className="lv2r-agent-copy">
                    <span>{agent.title}</span><strong>{agent.name}</strong>
                    <div className={`lv2r-agent-screen ${active ? "is-on" : ""}`} aria-hidden="true"><i /><i /><i /></div>
                    <em>{active
                      ? `${completions} backend completion(s) · lineage ${lineageObserved ? "observed" : "not in recent promotions"}`
                      : "WAITING · no persisted completion in current window"}</em>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <aside className="lv2-event-tape">
          <header><div><span>FACTORY RADIO</span><h2>Latest 10 persisted events</h2></div><i className="lv2-radio-light" aria-hidden="true" /></header>
          <div className="lv2-event-list">
            {model.eventRows.map((event, index) => {
              const payload = record(event.payload);
              const eventType = text(event.event_type, "UNKNOWN_EVENT");
              const station = stationForEvent(eventType);
              const ticker = text(payload.ticker, "").toUpperCase();
              const caseId = text(event.case_id, "");
              return (
                <article key={`${eventType}:${text(event.created_at, String(index))}:${index}`}>
                  <div><span>{timeLabel(event.created_at)}</span><em>{station ? STATIONS.find((item) => item.key === station)?.code : "SYS"}</em></div>
                  <strong>{eventType.replaceAll("_", " ")}</strong>
                  <p>{[ticker, caseId].filter(Boolean).join(" · ") || "Persisted system event"}</p>
                </article>
              );
            })}
            {!model.eventRows.length ? <div className="lv2-event-empty"><strong>RADIO QUIET</strong><p>No persisted 9G meaningful event is available.</p></div> : null}
          </div>
          <footer><span>Showing {model.eventRows.length} of {model.eventCount}</span><span>9G age · {ageLabel(model.telemetryLayer.age_seconds)}</span></footer>
        </aside>
      </section>

      {error ? <div className="lv2-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}

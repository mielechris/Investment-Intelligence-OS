import { useEffect, useMemo, useState } from "react";
import LivingCharacterAvatar from "./LivingCharacterAvatar";
import {
  LIVING_CAST,
  maxNarrativeForStation,
  type LivingCastKey,
} from "./livingCast";
import "./CinematicFactoryCommandDeck.css";

type JsonObject = Record<string, unknown>;
type DeckView = "floor" | "control";
type StationKey =
  | "radar"
  | "research"
  | "agents"
  | "committee"
  | "risk"
  | "paper"
  | "monitoring"
  | "learning";

type ValidationLayer = {
  availability?: string;
  age_seconds?: number | null;
  payload?: JsonObject | null;
};

type LivingOverview = {
  generated_at?: string;
  validation?: {
    layers?: {
      factory_telemetry?: ValidationLayer;
      outcome_learning?: ValidationLayer;
      market_validation?: ValidationLayer;
      shadow_strategy?: ValidationLayer;
    };
  };
  factory?: {
    availability?: string;
    payload?: JsonObject | null;
  };
  safety?: {
    direct_ledger_access?: boolean;
    backend_access?: string;
    backend_write_permission?: boolean;
    trade_execution_permission?: boolean;
    live_execution?: boolean;
  };
};

type Props = {
  view: DeckView;
};

const CAST_ORDER: Exclude<LivingCastKey, "max">[] = [
  "policy",
  "macro",
  "fundamentals",
  "market_structure",
  "commodities",
  "geo_weather",
  "skeptic",
  "portfolio",
];

const STATION_CODES: Record<StationKey, string> = {
  radar: "9E",
  research: "R",
  agents: "8A",
  committee: "IC",
  risk: "RK",
  paper: "P",
  monitoring: "M",
  learning: "9J",
};

function record(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function rows(value: unknown): JsonObject[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is JsonObject =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
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

function boolLabel(value: unknown, yes: string, no: string): string {
  return value === true ? yes : no;
}

function money(value: unknown): string {
  const numeric = numberValue(value);
  return numeric === null
    ? "—"
    : numeric.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      });
}

function timeLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function ageLabel(value: unknown): string {
  const seconds = numberValue(value);
  if (seconds === null) return "WARM-UP";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function readable(value: unknown, fallback = "WAITING"): string {
  return text(value, fallback).replaceAll("_", " ").toUpperCase();
}

function meaningful(value: unknown): boolean {
  const normalized = readable(value, "");
  return Boolean(normalized) &&
    ![
      "WAITING",
      "UNKNOWN",
      "NONE",
      "NO STATE",
      "NOT STARTED",
      "PENDING",
      "NOT EXECUTED",
    ].includes(normalized);
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

function eventIdentity(event: JsonObject): string {
  const payload = record(event.payload);
  return [
    text(payload.ticker, ""),
    text(event.case_id, ""),
    text(event.entity_id, ""),
  ]
    .filter(Boolean)
    .join(" · ");
}

function eventTone(eventType: string): "good" | "bad" | "neutral" {
  const normalized = eventType.toUpperCase();
  if (
    normalized.includes("FAIL") ||
    normalized.includes("REJECT") ||
    normalized.includes("BLOCK") ||
    normalized.includes("ERROR") ||
    normalized.includes("KILL")
  ) {
    return "bad";
  }
  if (
    normalized.includes("COMPLETE") ||
    normalized.includes("PROMOT") ||
    normalized.includes("AVAILABLE") ||
    normalized.includes("APPROV")
  ) {
    return "good";
  }
  return "neutral";
}

async function sameOriginJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `IIOS sidecar request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export default function CinematicFactoryCommandDeck({ view }: Props) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pulse, setPulse] = useState(0);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;

    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await sameOriginJson<LivingOverview>(
          "/living/overview",
          controller.signal,
        );
        if (disposed) return;
        setSnapshot(next);
        setError(null);
        setPulse((value) => value + 1);
      } catch (reason) {
        if (
          disposed ||
          (reason instanceof DOMException && reason.name === "AbortError")
        ) {
          return;
        }
        setError(
          reason instanceof Error
            ? reason.message
            : "Cinematic command deck sidecar unavailable",
        );
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
    const telemetryLayer = snapshot?.validation?.layers?.factory_telemetry ?? {};
    const telemetry = record(telemetryLayer.payload);
    const radar = record(telemetry.radar);
    const fund = record(telemetry.paper_fund);
    const events = rows(telemetry.recent_meaningful_events);
    const promotions = rows(telemetry.recent_promotions);
    const factoryPayload = record(snapshot?.factory?.payload);
    const factory = record(factoryPayload.factory);
    const desks = rows(factory.desks);
    const cases = rows(factoryPayload.cases);
    const outcomePayload = record(
      snapshot?.validation?.layers?.outcome_learning?.payload,
    );
    const outcomeCount =
      numberValue(outcomePayload.outcome_count) ??
      rows(outcomePayload.recent_outcomes).length;

    const stationCounts: Record<StationKey, number> = {
      radar: 0,
      research: 0,
      agents: 0,
      committee: 0,
      risk: 0,
      paper: 0,
      monitoring: 0,
      learning: 0,
    };
    for (const event of events) {
      const station = stationForEvent(text(event.event_type, ""));
      if (station) stationCounts[station] += 1;
    }

    const activeAgentKeys = new Set<string>();
    const lineageAgentKeys = new Set<string>();
    for (const desk of desks) {
      const key = text(desk.key, "");
      if (key && (numberValue(desk.recent_completions) ?? 0) > 0) {
        activeAgentKeys.add(key);
      }
    }
    for (const promotion of promotions) {
      const keys = record(promotion.agents).agent_keys;
      if (Array.isArray(keys)) {
        keys.forEach((key) => lineageAgentKeys.add(String(key)));
      }
    }

    const receiptTickers = Array.from(
      new Set(
        promotions
          .map((promotion) => text(promotion.ticker, "").toUpperCase())
          .filter(Boolean),
      ),
    ).slice(0, 6);

    const failedEvents = events
      .filter((event) => eventTone(text(event.event_type, "")) === "bad")
      .slice(0, 4);

    const committeeLineage = promotions.filter((promotion) =>
      meaningful(record(promotion.committee).disposition),
    ).length;
    const riskLineage = promotions.filter((promotion) =>
      meaningful(record(promotion.risk).decision),
    ).length;
    const paperLineage = promotions.filter((promotion) =>
      meaningful(record(promotion.paper_execution).execution),
    ).length;

    const latestEvent = events[0] ?? null;
    const latestType = latestEvent
      ? text(latestEvent.event_type, "UNKNOWN_EVENT")
      : "NO_PERSISTED_EVENT";
    const latestStation = stationForEvent(latestType);

    return {
      telemetryLayer,
      radar,
      fund,
      events,
      promotions,
      cases,
      outcomeCount,
      stationCounts,
      activeAgentKeys,
      lineageAgentKeys,
      receiptTickers,
      failedEvents,
      committeeLineage,
      riskLineage,
      paperLineage,
      latestEvent,
      latestType,
      latestStation,
    };
  }, [snapshot]);

  const safety = snapshot?.safety ?? {};
  const universe = text(model.radar.governed_universe_count, "—");
  const hits = text(model.radar.screener_hit_count, "—");
  const positions = text(model.fund.position_count, "0");
  const nav = money(model.fund.nav);
  const latestCode = model.latestStation
    ? STATION_CODES[model.latestStation]
    : "SYS";
  const latestNarrative = maxNarrativeForStation(
    model.latestStation,
    model.latestType,
  );
  const heartbeat = readable(model.telemetryLayer.availability, "WARMING");

  return (
    <section className={`cfd-shell cfd-shell--${view}`} aria-label="IIOS cinematic command deck">
      <i className="cfd-corner cfd-corner--tl" aria-hidden="true" />
      <i className="cfd-corner cfd-corner--tr" aria-hidden="true" />
      <i className="cfd-corner cfd-corner--bl" aria-hidden="true" />
      <i className="cfd-corner cfd-corner--br" aria-hidden="true" />

      <div className="cfd-top-grid">
        <aside className="cfd-panel cfd-feed">
          <header>
            <div>
              <span>MARKET INTELLIGENCE FEED</span>
              <strong>Persisted event wire</strong>
            </div>
            <em>{heartbeat === "AVAILABLE" ? "LIVE 24/7" : heartbeat}</em>
          </header>
          <div className="cfd-feed-list">
            {model.events.slice(0, 7).map((event, index) => {
              const eventType = text(event.event_type, "UNKNOWN_EVENT");
              const station = stationForEvent(eventType);
              const tone = eventTone(eventType);
              return (
                <article key={`${eventType}:${index}`} className={`is-${tone}`}>
                  <span>{station ? STATION_CODES[station] : "SYS"}</span>
                  <div>
                    <strong>{readable(eventType)}</strong>
                    <small>{eventIdentity(event) || "persisted system event"}</small>
                  </div>
                  <time>{timeLabel(event.created_at)}</time>
                </article>
              );
            })}
            {!model.events.length ? (
              <div className="cfd-empty">No persisted events exposed in the current window.</div>
            ) : null}
          </div>
        </aside>

        <section className="cfd-center-stage">
          <header className="cfd-brand-lockup">
            <div className="cfd-brand-mark">IIOS</div>
            <div>
              <h1>INTELLIGENCE FACTORY</h1>
              <p>BUILT ON EVIDENCE. RUN ON DISCIPLINE.</p>
              <em>QUESTIONABLY SUPERVISED.</em>
            </div>
          </header>

          <div className="cfd-kpi-grid">
            <article><span>MARKET UNIVERSE</span><strong>{universe}</strong><em>governed names</em></article>
            <article><span>RADAR HITS</span><strong>{hits}</strong><em>current 9E snapshot</em></article>
            <article><span>EVENT WINDOW</span><strong>{model.events.length}</strong><em>persisted 9G events</em></article>
            <article><span>GOVERNED CASES</span><strong>{model.cases.length}</strong><em>backend objects</em></article>
            <article><span>PAPER NAV</span><strong>{nav}</strong><em>{positions} positions</em></article>
            <article><span>OUTCOMES</span><strong>{model.outcomeCount}</strong><em>exact 9J lineage</em></article>
          </div>

          <div className="cfd-now-wire">
            <span>{latestCode}</span>
            <div>
              <small>NOW ON THE FLOOR</small>
              <strong>{readable(model.latestType)}</strong>
            </div>
            <em>{model.latestEvent ? eventIdentity(model.latestEvent) || "persisted system event" : "waiting for persisted event"}</em>
            <time>{model.latestEvent ? timeLabel(model.latestEvent.created_at) : "—"}</time>
          </div>
        </section>

        <aside className="cfd-panel cfd-boss-office">
          <div className="cfd-boss-portrait">
            <LivingCharacterAvatar
              characterKey="max"
              active={model.events.length > 0}
              reacting={model.latestEvent !== null}
            />
          </div>
          <div className="cfd-boss-copy">
            <span>THE BOSS</span>
            <strong>MAX</strong>
            <em>Chief Bullshit Officer · Factory Foreman</em>
            <blockquote>“I don’t predict. I prepare. Then I make somebody explain the downside.”</blockquote>
            <small>NARRATIVE · {latestNarrative}</small>
          </div>
        </aside>
      </div>

      <div className="cfd-middle-grid">
        <aside className="cfd-panel cfd-status-board">
          <header><span>FACTORY STATUS</span><em>{error ? "DEGRADED" : heartbeat}</em></header>
          <dl>
            <div><dt>SYSTEM STATUS</dt><dd className={error ? "is-bad" : "is-good"}>{error ? "SIDECAR WARNING" : heartbeat}</dd></div>
            <div><dt>LIVE CAPITAL</dt><dd className="is-good">{boolLabel(safety.live_execution, "ENABLED", "DISABLED")}</dd></div>
            <div><dt>WRITE AUTHORITY</dt><dd className="is-good">{boolLabel(safety.backend_write_permission, "ENABLED", "NONE")}</dd></div>
            <div><dt>TRADE AUTHORITY</dt><dd className="is-good">{boolLabel(safety.trade_execution_permission, "ENABLED", "FALSE")}</dd></div>
            <div><dt>DIRECT LEDGER</dt><dd>{boolLabel(safety.direct_ledger_access, "YES", "NONE")}</dd></div>
            <div><dt>BACKEND ACCESS</dt><dd>{readable(safety.backend_access, "READ ONLY")}</dd></div>
            <div><dt>HEARTBEAT AGE</dt><dd>{ageLabel(model.telemetryLayer.age_seconds)}</dd></div>
            <div><dt>PAPER ACCOUNT</dt><dd className="is-gold">{nav}</dd></div>
          </dl>
        </aside>

        <section className="cfd-panel cfd-cast-roster">
          <header>
            <div><span>THE EIGHT AGENTS</span><strong>Everyone has a role. Ego is not one.</strong></div>
            <em>{model.activeAgentKeys.size ? `${model.activeAgentKeys.size} ACTIVE` : "GOVERNED IDLE"}</em>
          </header>
          <div className="cfd-cast-grid">
            {CAST_ORDER.map((key, index) => {
              const member = LIVING_CAST[key];
              const active = model.activeAgentKeys.has(key);
              const lineage = model.lineageAgentKeys.has(key);
              return (
                <article
                  key={key}
                  className={`${active ? "is-active" : ""} ${lineage ? "has-lineage" : ""} ${key === "skeptic" ? "is-red-room" : ""}`}
                >
                  <div className="cfd-cast-number">{index + 1}</div>
                  <div className="cfd-cast-avatar">
                    <LivingCharacterAvatar
                      characterKey={key}
                      active={active}
                      reacting={active && model.latestStation === "agents"}
                    />
                  </div>
                  <div className="cfd-cast-copy">
                    <strong>{member.displayName}</strong>
                    <em>{member.governedRole}</em>
                    <small>{member.personaLine}</small>
                  </div>
                  <footer>{active ? "ACTIVE EVIDENCE" : lineage ? "LINEAGE OBSERVED" : "WAITING"}</footer>
                </article>
              );
            })}
          </div>
        </section>

        <aside className="cfd-right-rail">
          <section className="cfd-panel cfd-family-rules">
            <header><span>FAMILY RULES</span></header>
            <ol>
              <li>Protect capital.</li>
              <li>Respect the process.</li>
              <li>Trust no single model.</li>
              <li>Question everything.</li>
              <li>MAX is not a fiduciary.</li>
            </ol>
          </section>

          <section className="cfd-panel cfd-graveyard">
            <header><span>THE GRAVEYARD</span><em>Bad ideas. R.I.P.</em></header>
            <div>
              {model.failedEvents.map((event, index) => (
                <article key={`${text(event.event_type, "FAILED")}:${index}`}>
                  <strong>{text(record(event.payload).ticker, "CASE")}</strong>
                  <small>{readable(event.event_type, "REJECTED")}</small>
                </article>
              ))}
              {!model.failedEvents.length ? (
                <p>No failed or rejected events exposed in this window.</p>
              ) : null}
            </div>
          </section>
        </aside>
      </div>

      <section className="cfd-prop-grid" aria-label="Cinematic factory evidence modules">
        <article className="cfd-prop cfd-prop--detector">
          <span>BULLSHIT DETECTOR</span>
          <strong>0%</strong>
          <em>Synthetic activity tolerated</em>
          <p>Real state drives the floor. Ambient motion does not.</p>
        </article>

        <article className="cfd-prop">
          <span>PREDICTION RECEIPTS</span>
          <strong>{model.receiptTickers.length || "—"}</strong>
          <em>Recent persisted promotions</em>
          <p>{model.receiptTickers.join(" · ") || "No promotion receipts exposed."}</p>
        </article>

        <article className="cfd-prop">
          <span>THE COMMISSION</span>
          <strong>{model.committeeLineage}</strong>
          <em>Committee lineage records</em>
          <p>We argue. The evidence decides who gets embarrassed.</p>
        </article>

        <article className="cfd-prop">
          <span>RISK INSPECTION</span>
          <strong>{model.riskLineage}</strong>
          <em>Persisted risk decisions</em>
          <p>Position size · liquidity · correlation · tail risk.</p>
        </article>

        <article className="cfd-prop">
          <span>PAPER EXECUTION</span>
          <strong>{model.paperLineage}</strong>
          <em>Persisted paper handoffs</em>
          <p>Fake money. Real discipline. No live authority.</p>
        </article>

        <article className="cfd-prop">
          <span>THE CONFESSIONAL</span>
          <strong>{model.failedEvents.length}</strong>
          <em>Failures in current event window</em>
          <p>Admit it. Fix it. Log the lineage. Move on.</p>
        </article>

        <article className="cfd-prop cfd-prop--plan">
          <span>THE PLAN</span>
          <strong>{view === "floor" ? "OPERATE" : "INSPECT"}</strong>
          <em>{view === "floor" ? "Watch real intelligence move" : "Trace every decision surface"}</em>
          <p>Evidence → specialists → committee → risk → paper → monitoring → learning.</p>
        </article>
      </section>

      <footer className="cfd-floor-ribbon">
        <span><i className="is-good" /> DATA INTAKE <strong>{model.stationCounts.radar ? "RECENT" : "IDLE"}</strong></span>
        <span><i className={model.activeAgentKeys.size ? "is-good" : ""} /> AGENT QUEUE <strong>{model.activeAgentKeys.size ? "ACTIVE" : "WAITING"}</strong></span>
        <span><i className={model.committeeLineage ? "is-good" : ""} /> COMMITTEE <strong>{model.committeeLineage ? "LINEAGE" : "WAITING"}</strong></span>
        <span><i className={model.riskLineage ? "is-good" : ""} /> RISK GATE <strong>{model.riskLineage ? "ENGAGED" : "WAITING"}</strong></span>
        <span><i className="is-gold" /> EXECUTION <strong>PAPER ONLY</strong></span>
        <span><i /> MODE <strong>{view === "floor" ? "FACTORY FLOOR" : "CONTROL ROOM"}</strong></span>
      </footer>
    </section>
  );
}

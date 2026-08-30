import { useEffect, useMemo, useState } from "react";
import "./FactoryWatch.css";

type JsonObject = Record<string, unknown>;

type Layer = {
  availability?: string;
  age_seconds?: number | null;
  payload?: JsonObject | null;
};

type Overview = {
  generated_at?: string;
  validation?: {
    layers?: {
      factory_telemetry?: Layer;
      market_validation?: Layer;
      shadow_strategy?: Layer;
      outcome_learning?: Layer;
    };
  };
  factory?: {
    availability?: string;
    payload?: {
      factory?: { desks?: Array<{ key?: string; name?: string; recent_completions?: number }> };
      cases?: Array<{ case_id?: string; ticker?: string; stage?: string; active_room?: string }>;
    } | null;
  };
  safety?: {
    backend_access?: string;
    backend_write_permission?: boolean;
    trade_execution_permission?: boolean;
    live_execution?: boolean;
  };
};

type SidecarHealth = JsonObject;

type AgentStatus = {
  key: string;
  label: string;
  completions: number;
};

const AGENTS: Array<[string, string]> = [
  ["policy", "Frankie Fine Print"],
  ["macro", "Benny Basis Points"],
  ["fundamentals", "Vinny EBITDA"],
  ["market_structure", "Mikey Tape"],
  ["commodities", "Tony Tanker"],
  ["geo_weather", "Stormy Sal"],
  ["skeptic", "Johnny No"],
  ["portfolio", "Paulie Positions"],
];

function record(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function rows(value: unknown): JsonObject[] {
  return Array.isArray(value)
    ? value.filter((item): item is JsonObject => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function readable(value: unknown, fallback = "WAITING"): string {
  return text(value, fallback).replaceAll("_", " ").toUpperCase();
}

function age(value?: number | null): string {
  if (value === undefined || value === null) return "WARM-UP";
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.floor(value / 60)}m`;
  return `${Math.floor(value / 3600)}h`;
}

function money(value: unknown): string {
  const numeric = numberValue(value);
  return numeric === null
    ? "—"
    : numeric.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function time(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function regularSessionClock(now = new Date()): { open: boolean; label: string; detail: string } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const weekday = map.weekday ?? "";
  const hour = Number(map.hour ?? 0);
  const minute = Number(map.minute ?? 0);
  const minutes = hour * 60 + minute;
  const weekdayOpen = !["Sat", "Sun"].includes(weekday);
  const open = weekdayOpen && minutes >= 9 * 60 + 30 && minutes < 16 * 60;
  return {
    open,
    label: open ? "REGULAR SESSION CLOCK · OPEN" : "OFF-HOURS WATCH · MARKET CLOCK CLOSED",
    detail: open
      ? "Factory Watch is observing live regular-session state."
      : "Market trading may be closed, but IIOS heartbeat, research, validation, learning, and persisted state remain watchable.",
  };
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store", signal });
  if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export default function FactoryWatch() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [health, setHealth] = useState<SidecarHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const [clock, setClock] = useState(() => regularSessionClock());

  useEffect(() => {
    document.title = "IIOS Factory Watch";
    const clockTimer = window.setInterval(() => setClock(regularSessionClock()), 30_000);
    return () => window.clearInterval(clockTimer);
  }, []);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;

    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const [nextOverview, nextHealth] = await Promise.all([
          getJson<Overview>("/living/overview", controller.signal),
          getJson<SidecarHealth>("/health", controller.signal).catch(() => ({})),
        ]);
        if (disposed) return;
        setOverview(nextOverview);
        setHealth(nextHealth);
        setError(null);
        setRefreshedAt(new Date());
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "Factory Watch refresh failed");
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
    const layers = overview?.validation?.layers ?? {};
    const telemetryLayer = layers.factory_telemetry ?? {};
    const telemetry = record(telemetryLayer.payload);
    const radar = record(telemetry.radar);
    const fund = record(telemetry.paper_fund);
    const events = rows(telemetry.recent_meaningful_events);
    const latestEvent = events[0] ?? null;
    const marketValidation = record(layers.market_validation?.payload);
    const shadow = record(layers.shadow_strategy?.payload);
    const outcomes = record(layers.outcome_learning?.payload);
    const factoryPayload = overview?.factory?.payload;
    const desks = factoryPayload?.factory?.desks ?? [];
    const cases = factoryPayload?.cases ?? [];
    const deskMap = new Map(desks.map((desk) => [desk.key ?? "", desk]));
    const agents: AgentStatus[] = AGENTS.map(([key, label]) => ({
      key,
      label,
      completions: deskMap.get(key)?.recent_completions ?? 0,
    }));

    const detect = numberValue(marketValidation.detect_rate_pct)
      ?? numberValue(marketValidation.detection_rate_pct)
      ?? numberValue(marketValidation.detect_pct);
    const miss = numberValue(marketValidation.miss_rate_pct)
      ?? numberValue(marketValidation.miss_pct);
    const shadowSessions = numberValue(shadow.session_count)
      ?? numberValue(shadow.sessions)
      ?? rows(shadow.sessions).length;
    const outcomeCount = numberValue(outcomes.outcome_count) ?? rows(outcomes.recent_outcomes).length;

    return {
      layers,
      telemetryLayer,
      radar,
      fund,
      events,
      latestEvent,
      cases,
      agents,
      detect,
      miss,
      shadowSessions,
      outcomeCount,
    };
  }, [overview]);

  const factoryAvailable = readable(overview?.factory?.availability, "WARMING");
  const telemetryAvailable = readable(model.telemetryLayer.availability, "WARMING");
  const alive = !error && (factoryAvailable === "AVAILABLE" || telemetryAvailable === "AVAILABLE");
  const latestPayload = model.latestEvent ? record(model.latestEvent.payload) : {};
  const latestTicker = text(latestPayload.ticker, "");
  const latestCase = model.latestEvent ? text(model.latestEvent.case_id, "") : "";
  const safety = overview?.safety ?? {};
  const healthState = readable(record(health).status, health ? "CONNECTED" : "WARMING");

  return (
    <main className="fw-shell">
      <header className="fw-header">
        <div>
          <span>IIOS · ALWAYS-ON OBSERVATION</span>
          <h1>FACTORY WATCH</h1>
          <p>Stable read-only status surface. Keep this open while the cinematic factory is being rebuilt.</p>
        </div>
        <div className={`fw-heartbeat ${alive ? "is-live" : "is-warning"}`}>
          <i />
          <div><span>FACTORY HEARTBEAT</span><strong>{alive ? "LIVE" : "CHECK"}</strong><em>9G age {age(model.telemetryLayer.age_seconds)}</em></div>
        </div>
      </header>

      <section className={`fw-market-clock ${clock.open ? "is-open" : "is-closed"}`}>
        <div><i /><strong>{clock.label}</strong></div>
        <p>{clock.detail}</p>
        <em>Regular-session clock is a presentation aid; persisted IIOS state remains authoritative.</em>
      </section>

      <section className="fw-safety">
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE PERMISSION · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>WRITE PERMISSION · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
        <span>BACKEND · {readable(safety.backend_access, "READ ONLY")}</span>
      </section>

      <section className="fw-metrics">
        <article><span>MARKET UNIVERSE</span><strong>{text(model.radar.governed_universe_count)}</strong><em>persisted 9G</em></article>
        <article><span>9E RADAR HITS</span><strong>{text(model.radar.screener_hit_count)}</strong><em>latest persisted snapshot</em></article>
        <article><span>EVENT WINDOW</span><strong>{model.events.length}</strong><em>meaningful persisted events</em></article>
        <article><span>GOVERNED CASES</span><strong>{model.cases.length}</strong><em>backend case objects</em></article>
        <article><span>PAPER NAV</span><strong>{money(model.fund.nav)}</strong><em>{text(model.fund.position_count, "0")} positions</em></article>
        <article><span>SIDECAR</span><strong>{healthState}</strong><em>read-only 5176</em></article>
      </section>

      <section className="fw-grid">
        <article className="fw-panel fw-now">
          <header><span>NOW / LAST ON THE FACTORY</span><em>{model.latestEvent ? time(model.latestEvent.created_at) : "WAITING"}</em></header>
          <strong>{model.latestEvent ? readable(model.latestEvent.event_type, "PERSISTED EVENT") : "NO CURRENT PERSISTED EVENT"}</strong>
          <p>{[latestTicker, latestCase].filter(Boolean).join(" · ") || "Waiting for the next persisted factory event."}</p>
          <small>When markets are closed, this remains the most recent persisted event rather than simulated movement.</small>
        </article>

        <article className="fw-panel">
          <header><span>VALIDATION & LEARNING</span><em>9H · 9I · 9J</em></header>
          <div className="fw-layer-grid">
            <div><span>9H INDEPENDENT GRADING</span><strong>{readable(model.layers.market_validation?.availability, "WAITING")}</strong><small>{model.detect === null ? "Detect —" : `Detect ${model.detect.toFixed(1)}%`} · {model.miss === null ? "Miss —" : `Miss ${model.miss.toFixed(1)}%`}</small></div>
            <div><span>9I SHADOW STRATEGY</span><strong>{readable(model.layers.shadow_strategy?.availability, "WAITING")}</strong><small>{model.shadowSessions} session(s)</small></div>
            <div><span>9J OUTCOME LEARNING</span><strong>{readable(model.layers.outcome_learning?.availability, "WAITING")}</strong><small>{model.outcomeCount} outcome(s)</small></div>
          </div>
        </article>

        <article className="fw-panel fw-agents">
          <header><span>EIGHT SPECIALISTS</span><em>persisted completions only</em></header>
          <div className="fw-agent-grid">
            {model.agents.map((agent) => (
              <div key={agent.key} className={agent.completions > 0 ? "is-active" : ""}>
                <i />
                <strong>{agent.label}</strong>
                <span>{agent.completions > 0 ? `${agent.completions} recent completion(s)` : "governed idle"}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="fw-panel fw-events">
          <header><span>RECENT PERSISTED EVENTS</span><em>poll 5s</em></header>
          <div>
            {model.events.slice(0, 10).map((event, index) => {
              const payload = record(event.payload);
              return (
                <div key={`${text(event.event_type, "event")}:${index}`}>
                  <time>{time(event.created_at)}</time>
                  <strong>{readable(event.event_type, "EVENT")}</strong>
                  <span>{[text(payload.ticker, ""), text(event.case_id, "")].filter(Boolean).join(" · ") || "system event"}</span>
                </div>
              );
            })}
            {!model.events.length ? <p>No persisted events in the current window.</p> : null}
          </div>
        </article>
      </section>

      <footer className="fw-footer">
        <span>{error ? `LATEST REFRESH WARNING · ${error}` : "READ-ONLY FACTORY WATCH · NO CAPITAL AUTHORITY"}</span>
        <em>{refreshedAt ? `refreshed ${refreshedAt.toLocaleTimeString()}` : "connecting…"}</em>
      </footer>
    </main>
  );
}

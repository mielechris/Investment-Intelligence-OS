import { useEffect, useMemo, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import {
  LIVING_CAST,
  agentNarrativeForEvent,
  maxNarrativeForStation,
  type LivingCastKey,
} from "./livingCast";
import { telemetryUrl } from "./telemetryEndpoint";
import "./LivingCharacterDirectorV7.css";

type JsonObject = Record<string, unknown>;
type DirectorView = "floor" | "control";
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
      market_validation?: ValidationLayer;
      shadow_strategy?: ValidationLayer;
      outcome_learning?: ValidationLayer;
    };
  };
  safety?: {
    backend_access?: string;
    backend_write_permission?: boolean;
    trade_execution_permission?: boolean;
    live_execution?: boolean;
  };
};

type Props = {
  view: DirectorView;
};

type DirectorEvent = {
  event_type?: string | null;
  case_id?: string | null;
  entity_id?: string | null;
  created_at?: string | null;
  payload?: JsonObject | null;
};

type Promotion = {
  case_id?: string | null;
  ticker?: string | null;
  agents?: {
    agent_keys?: string[] | null;
  } | null;
};

type Speaker = {
  key: LivingCastKey;
  narrative: string;
  persistedParticipant: boolean;
};

const ROUTE: Array<{ key: StationKey; code: string; label: string }> = [
  { key: "radar", code: "9E", label: "RADAR" },
  { key: "research", code: "R", label: "RESEARCH" },
  { key: "agents", code: "8A", label: "BULLPEN" },
  { key: "committee", code: "IC", label: "COMMISSION" },
  { key: "risk", code: "RK", label: "RISK" },
  { key: "paper", code: "P", label: "PAPER" },
  { key: "monitoring", code: "M", label: "MONITORING" },
  { key: "learning", code: "9J", label: "LEARNING" },
];

const STATION_CAST: Record<StationKey, LivingCastKey[]> = {
  radar: ["market_structure", "skeptic"],
  research: ["policy", "macro", "fundamentals"],
  agents: ["policy", "macro", "fundamentals"],
  committee: ["fundamentals", "skeptic", "portfolio"],
  risk: ["portfolio", "skeptic"],
  paper: ["portfolio"],
  monitoring: ["market_structure", "portfolio"],
  learning: ["fundamentals", "skeptic", "portfolio"],
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

function eventLabel(value: unknown): string {
  return text(value, "UNKNOWN EVENT").replaceAll("_", " ").toUpperCase();
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

function parseTime(value: unknown): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function ageSeconds(value: unknown, now: number): number | null {
  const parsed = parseTime(value);
  if (parsed === null) return null;
  return Math.max(0, Math.floor((now - parsed) / 1000));
}

function ageLabel(seconds: number | null): string {
  if (seconds === null) return "AGE UNKNOWN";
  if (seconds < 60) return `${seconds}s AGO`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m AGO`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h AGO`;
  return `${Math.floor(seconds / 86_400)}d AGO`;
}

function timeLabel(value: unknown): string {
  const parsed = parseTime(value);
  if (parsed === null) return "TIME UNKNOWN";
  return new Date(parsed).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function stripSpeakerPrefix(value: string): string {
  const colon = value.indexOf(":");
  return colon >= 0 ? value.slice(colon + 1).trim() : value;
}

function isLivingCastKey(value: string): value is LivingCastKey {
  return Object.prototype.hasOwnProperty.call(LIVING_CAST, value);
}

function promotionForEvent(event: DirectorEvent, promotions: Promotion[]): Promotion | null {
  const caseId = text(event.case_id, "");
  if (!caseId) return null;
  return promotions.find((promotion) => text(promotion.case_id, "") === caseId) ?? null;
}

function tickerForEvent(event: DirectorEvent, promotion: Promotion | null): string {
  const payload = record(event.payload);
  return text(payload.ticker, text(promotion?.ticker, "NO TICKER")).toUpperCase();
}

function persistedAgentKeys(promotion: Promotion | null): LivingCastKey[] {
  const raw = promotion?.agents?.agent_keys;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((value) => String(value))
    .filter((value): value is LivingCastKey => isLivingCastKey(value) && value !== "max");
}

function speakersForEvent(
  station: StationKey | null,
  eventType: string,
  promotion: Promotion | null,
): Speaker[] {
  const persisted = persistedAgentKeys(promotion);
  const fallback = station ? STATION_CAST[station] : [];
  const selected = persisted.length ? persisted.slice(0, 3) : fallback.slice(0, 3);
  const deduped = Array.from(new Set(selected));

  return [
    {
      key: "max",
      narrative: maxNarrativeForStation(station, eventType),
      persistedParticipant: false,
    },
    ...deduped.map((key) => ({
      key,
      narrative: stripSpeakerPrefix(agentNarrativeForEvent(key, eventType)),
      persistedParticipant: persisted.includes(key),
    })),
  ];
}

async function loadOverview(signal: AbortSignal): Promise<LivingOverview> {
  const response = await fetch(telemetryUrl("/living/overview"), {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(`V7 director source unavailable: HTTP ${response.status}`);
  }
  return response.json() as Promise<LivingOverview>;
}

export default function LivingCharacterDirectorV7({ view }: Props) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;

    const refresh = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await loadOverview(controller.signal);
        if (disposed) return;
        setSnapshot(next);
        setError(null);
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "V7 director source unavailable");
      }
    };

    void refresh();
    const refreshTimer = window.setInterval(() => void refresh(), 5_000);
    const clockTimer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(refreshTimer);
      window.clearInterval(clockTimer);
    };
  }, []);

  const model = useMemo(() => {
    const telemetry = record(snapshot?.validation?.layers?.factory_telemetry?.payload);
    const events = rows(telemetry.recent_meaningful_events) as DirectorEvent[];
    const promotions = rows(telemetry.recent_promotions) as Promotion[];
    const latestEvent = events[0] ?? null;
    const eventType = latestEvent ? text(latestEvent.event_type, "UNKNOWN_EVENT") : "";
    const station = eventType ? stationForEvent(eventType) : null;
    const promotion = latestEvent ? promotionForEvent(latestEvent, promotions) : null;
    const ticker = latestEvent ? tickerForEvent(latestEvent, promotion) : "—";
    const age = latestEvent ? ageSeconds(latestEvent.created_at, now) : null;
    const isLive = age !== null && age <= 120;
    const speakers = latestEvent
      ? speakersForEvent(station, eventType, promotion)
      : [];

    return {
      latestEvent,
      eventType,
      station,
      promotion,
      ticker,
      age,
      isLive,
      speakers,
      eventCount: events.length,
    };
  }, [snapshot, now]);

  const safety = snapshot?.safety ?? {};
  const sceneState = !snapshot
    ? "CONNECTING"
    : error
      ? "SOURCE WARNING"
      : !model.latestEvent
        ? "CAST QUIET"
        : model.isLive
          ? "LIVE PERSISTED SCENE"
          : "LAST PERSISTED SCENE";

  return (
    <section
      className={`lcd7-shell lcd7-shell--${view} ${model.isLive ? "is-live" : "is-history"}`}
      aria-label="V7 persisted-event living character director"
    >
      <header className="lcd7-header">
        <div>
          <span>V7 · LIVING CHARACTER DIRECTOR</span>
          <h2>THE CAST REACTS TO THE FACTORY — NEVER THE OTHER WAY AROUND.</h2>
          <p>
            Character motion and dialogue are presentation-only reactions to persisted IIOS events.
            No event creates no scene. Old events stay historical instead of pretending to be live.
          </p>
        </div>
        <div className={`lcd7-state ${model.isLive ? "is-live" : ""}`}>
          <i aria-hidden="true" />
          <strong>{sceneState}</strong>
          <span>{model.latestEvent ? ageLabel(model.age) : "WAITING FOR PERSISTED EVENT"}</span>
        </div>
      </header>

      <div className="lcd7-truth-rail">
        <span>EVENT SOURCE · 9G PERSISTED TELEMETRY</span>
        <span>NARRATIVE · PRESENTATION ONLY</span>
        <span>RAW MODEL OUTPUT · NOT CLAIMED</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>WRITE AUTHORITY · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
      </div>

      <div className="lcd7-route" aria-label="Factory scene route">
        {ROUTE.map((node) => {
          const active = node.key === model.station;
          return (
            <div key={node.key} className={`lcd7-route-node ${active ? "is-active" : ""}`}>
              <span>{node.code}</span>
              <strong>{node.label}</strong>
              <i aria-hidden="true" />
            </div>
          );
        })}
      </div>

      {model.latestEvent ? (
        <div className="lcd7-scene">
          <aside className="lcd7-event-card">
            <span>{model.isLive ? "NOW DIRECTING" : "LAST SCENE ON FILE"}</span>
            <strong>{eventLabel(model.eventType)}</strong>
            <div className="lcd7-event-meta">
              <p><b>TICKER</b><span>{model.ticker}</span></p>
              <p><b>CASE</b><span>{text(model.latestEvent.case_id, "NO CASE")}</span></p>
              <p><b>ENTITY</b><span>{text(model.latestEvent.entity_id, "NO ENTITY")}</span></p>
              <p><b>TIME</b><span>{timeLabel(model.latestEvent.created_at)}</span></p>
              <p><b>AGE</b><span>{ageLabel(model.age)}</span></p>
              <p><b>EVENT WINDOW</b><span>{model.eventCount} persisted</span></p>
            </div>
            <footer>
              CURRENT ROOM · {model.station ? ROUTE.find((node) => node.key === model.station)?.label : "UNMAPPED SYSTEM EVENT"}
            </footer>
          </aside>

          <div className="lcd7-stage">
            <div className="lcd7-stage-head">
              <span>ON STAGE</span>
              <strong>{model.speakers.length} CHARACTER REACTION{model.speakers.length === 1 ? "" : "S"}</strong>
              <em>{model.isLive ? "RECENT EVENT-BOUND MOTION" : "HISTORICAL · MOTION QUIET"}</em>
            </div>

            <div className="lcd7-cast">
              {model.speakers.map((speaker, index) => {
                const member = LIVING_CAST[speaker.key];
                return (
                  <article
                    key={`${speaker.key}:${model.eventType}:${index}`}
                    className={`lcd7-character ${speaker.key === "skeptic" ? "is-red" : ""}`}
                  >
                    <div className="lcd7-portrait">
                      <CinematicCharacterPortrait
                        characterKey={speaker.key}
                        active={model.isLive}
                        reacting={model.isLive}
                        variant={speaker.key === "max" ? "boss" : "scene"}
                      />
                    </div>
                    <div className="lcd7-dialogue">
                      <header>
                        <strong>{member.displayName}</strong>
                        <span>{member.governedRole}</span>
                      </header>
                      <blockquote>“{speaker.narrative}”</blockquote>
                      <footer>
                        {speaker.persistedParticipant
                          ? "PERSISTED AGENT LINEAGE OBSERVED · NARRATIVE WORDING"
                          : "NARRATIVE CAST REACTION · NOT LITERAL AGENT SPEECH"}
                      </footer>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className="lcd7-empty">
          <CinematicCharacterPortrait characterKey="max" variant="boss" />
          <div>
            <span>NO PERSISTED EVENT → NO CHARACTER SCENE</span>
            <strong>THE FLOOR IS QUIET.</strong>
            <p>MAX and the crew remain visually present, but nobody gets dialogue until IIOS persists something worth reacting to.</p>
          </div>
        </div>
      )}

      {error ? <div className="lcd7-warning">LATEST DIRECTOR REFRESH WARNING · {error}</div> : null}
    </section>
  );
}

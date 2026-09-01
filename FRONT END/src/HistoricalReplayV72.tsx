import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";
import { mobReactionLine, mobReplayBannerLine } from "./mobVoice";
import { telemetryUrl } from "./telemetryEndpoint";
import "./HistoricalReplayV72.css";

type JsonObject = Record<string, unknown>;
type View = "floor" | "control";
type StationKey = "radar" | "research" | "agents" | "committee" | "risk" | "paper" | "monitoring" | "learning";
type RoomKey = "pit" | "war" | "bullpen" | "commission" | "risk" | "paper" | "monitoring" | "learning" | "max";

type ValidationLayer = {
  availability?: string;
  age_seconds?: number | null;
  payload?: JsonObject | null;
};

type LivingOverview = {
  validation?: {
    layers?: {
      factory_telemetry?: ValidationLayer;
    };
  };
  safety?: {
    backend_write_permission?: boolean;
    trade_execution_permission?: boolean;
    live_execution?: boolean;
  };
};

type FactoryEvent = {
  event_type?: string | null;
  case_id?: string | null;
  entity_id?: string | null;
  created_at?: string | null;
  payload?: JsonObject | null;
};

type Promotion = {
  case_id?: string | null;
  ticker?: string | null;
  agents?: { agent_keys?: string[] | null } | null;
  committee?: { disposition?: string | null; confidence?: number | null } | null;
  risk?: { decision?: string | null } | null;
  paper_execution?: { execution?: string | null } | null;
};

type TravelerStyle = CSSProperties & {
  "--start-x": string;
  "--end-x": string;
  "--travel-delay": string;
};

const ROOMS: Array<{ key: RoomKey; code: string; label: string }> = [
  { key: "pit", code: "PIT", label: "Intelligence Pit" },
  { key: "war", code: "WAR", label: "Macro War Room" },
  { key: "bullpen", code: "8A", label: "Specialist Bullpen" },
  { key: "commission", code: "IC", label: "The Commission" },
  { key: "risk", code: "RK", label: "Risk Inspection" },
  { key: "paper", code: "P", label: "Paper Bay" },
  { key: "monitoring", code: "M", label: "Monitoring" },
  { key: "learning", code: "9J", label: "The Confessional" },
  { key: "max", code: "MAX", label: "MAX's Office" },
];

const STATION_ROOM: Record<StationKey, RoomKey> = {
  radar: "pit",
  research: "war",
  agents: "bullpen",
  committee: "commission",
  risk: "risk",
  paper: "paper",
  monitoring: "monitoring",
  learning: "learning",
};

const HOME_ROOM: Record<LivingCastKey, RoomKey> = {
  max: "max",
  policy: "war",
  macro: "war",
  fundamentals: "bullpen",
  market_structure: "pit",
  commodities: "pit",
  geo_weather: "war",
  skeptic: "commission",
  portfolio: "risk",
};

const FALLBACK_CAST: Record<StationKey, LivingCastKey[]> = {
  radar: ["market_structure", "skeptic"],
  research: ["policy", "macro", "geo_weather"],
  agents: ["policy", "macro", "fundamentals"],
  committee: ["fundamentals", "skeptic", "portfolio"],
  risk: ["portfolio", "skeptic"],
  paper: ["portfolio"],
  monitoring: ["market_structure", "portfolio"],
  learning: ["fundamentals", "skeptic", "portfolio"],
};

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

function readable(value: unknown, fallback = "UNREPORTED"): string {
  return text(value, fallback).replaceAll("_", " ").toUpperCase();
}

function parseTime(value: unknown): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function ageLabel(value: unknown): string {
  const parsed = parseTime(value);
  if (parsed === null) return "AGE UNKNOWN";
  const seconds = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
  if (seconds < 60) return `${seconds}s AGO`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m AGO`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h AGO`;
  return `${Math.floor(seconds / 86_400)}d AGO`;
}

function timeLabel(value: unknown): string {
  const parsed = parseTime(value);
  if (parsed === null) return "TIME UNKNOWN";
  return new Date(parsed).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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

function isCastKey(value: string): value is LivingCastKey {
  return Object.prototype.hasOwnProperty.call(LIVING_CAST, value);
}

function persistedCast(promotion: Promotion | null): LivingCastKey[] {
  const raw = promotion?.agents?.agent_keys;
  if (!Array.isArray(raw)) return [];
  return raw.map(String).filter((key): key is LivingCastKey => isCastKey(key) && key !== "max");
}

function promotionFor(event: FactoryEvent | null, promotions: Promotion[]): Promotion | null {
  if (!event) return null;
  const caseId = text(event.case_id, "");
  if (!caseId) return null;
  return promotions.find((item) => text(item.case_id, "") === caseId) ?? null;
}

function tickerFor(event: FactoryEvent | null, promotion: Promotion | null): string {
  if (!event) return "—";
  return text(record(event.payload).ticker, text(promotion?.ticker, "NO TICKER")).toUpperCase();
}

function roomX(room: RoomKey): string {
  const index = Math.max(0, ROOMS.findIndex((item) => item.key === room));
  return `${((index + 0.5) / ROOMS.length) * 100}%`;
}

function castFor(station: StationKey | null, promotion: Promotion | null): LivingCastKey[] {
  const observed = persistedCast(promotion);
  const base = observed.length ? observed.slice(0, 4) : station ? FALLBACK_CAST[station] : [];
  return Array.from(new Set<LivingCastKey>(["max", ...base]));
}

async function loadOverview(signal: AbortSignal): Promise<LivingOverview> {
  const response = await fetch(telemetryUrl("/living/overview"), { headers: { Accept: "application/json" }, cache: "no-store", signal });
  if (!response.ok) throw new Error(`V7.2 replay source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingOverview>;
}

export default function HistoricalReplayV72({ view }: { view: View }) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [runId, setRunId] = useState(0);
  const stopTimer = useRef<number | null>(null);

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
        setError(reason instanceof Error ? reason.message : "V7.2 replay source unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
      if (stopTimer.current !== null) window.clearTimeout(stopTimer.current);
    };
  }, []);

  const model = useMemo(() => {
    const telemetry = record(snapshot?.validation?.layers?.factory_telemetry?.payload);
    const events = (rows(telemetry.recent_meaningful_events) as FactoryEvent[]).slice(0, 12);
    const promotions = rows(telemetry.recent_promotions) as Promotion[];
    const safeIndex = events.length ? Math.min(selectedIndex, events.length - 1) : 0;
    const event = events[safeIndex] ?? null;
    const eventType = event ? text(event.event_type, "UNKNOWN_EVENT") : "";
    const station = eventType ? stationForEvent(eventType) : null;
    const room = station ? STATION_ROOM[station] : null;
    const promotion = promotionFor(event, promotions);
    const ticker = tickerFor(event, promotion);
    const cast = castFor(station, promotion);
    const context = {
      eventType,
      ticker,
      disposition: readable(promotion?.committee?.disposition),
      confidence: typeof promotion?.committee?.confidence === "number" ? `${Math.round(promotion.committee.confidence * (promotion.committee.confidence <= 1 ? 100 : 1))}%` : "UNREPORTED",
      riskDecision: readable(promotion?.risk?.decision),
      paperState: readable(promotion?.paper_execution?.execution),
    };
    return { events, safeIndex, event, eventType, station, room, promotion, ticker, cast, context };
  }, [snapshot, selectedIndex]);

  useEffect(() => {
    if (selectedIndex !== model.safeIndex) setSelectedIndex(model.safeIndex);
  }, [model.safeIndex, selectedIndex]);

  const runReplay = () => {
    if (!model.event) return;
    if (stopTimer.current !== null) window.clearTimeout(stopTimer.current);
    setPlaying(false);
    window.requestAnimationFrame(() => {
      setRunId((value) => value + 1);
      setPlaying(true);
      stopTimer.current = window.setTimeout(() => setPlaying(false), 5200);
    });
  };

  const previous = () => {
    if (!model.events.length) return;
    setPlaying(false);
    setSelectedIndex((value) => (value + 1) % model.events.length);
  };

  const next = () => {
    if (!model.events.length) return;
    setPlaying(false);
    setSelectedIndex((value) => (value - 1 + model.events.length) % model.events.length);
  };

  const safety = snapshot?.safety ?? {};
  const targetRoom = model.room ?? "max";

  return (
    <section className={`hr72-shell hr72-shell--${view} ${playing ? "is-playing" : "is-paused"}`} aria-label="V7.2 historical character replay theater">
      <header className="hr72-header">
        <div>
          <span>V7.2 · THE BACK ROOM SCREENING THEATER</span>
          <h2>REAL RECEIPTS. FAKE REENACTMENT. FILTHY MOUTHS.</h2>
          <p>
            Pick a real persisted IIOS event and rehearse the character movement, room choreography and mob-noir dialogue.
            Replay motion is presentation only and is never presented as current market activity.
          </p>
        </div>
        <div className="hr72-stamp">
          <strong>HISTORICAL REPLAY</strong>
          <span>NOT LIVE · NOT MODEL OUTPUT</span>
        </div>
      </header>

      <div className="hr72-truth">
        <span>EVENT · REAL PERSISTED 9G RECORD</span>
        <span>REENACTMENT · PRESENTATION ONLY</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>WRITE AUTHORITY · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
      </div>

      <div className="hr72-controls">
        <button type="button" onClick={previous} disabled={!model.events.length}>← OLDER RECEIPT</button>
        <div>
          <span>RECEIPT {model.events.length ? model.safeIndex + 1 : 0} OF {model.events.length}</span>
          <strong>{model.event ? readable(model.eventType, "UNKNOWN EVENT") : "NO PERSISTED EVENTS"}</strong>
          <small>{model.event ? `${model.ticker} · ${timeLabel(model.event.created_at)} · ${ageLabel(model.event.created_at)}` : "WAITING FOR 9G"}</small>
        </div>
        <button type="button" onClick={runReplay} disabled={!model.event}>{playing ? "ROLLING..." : "▶ RUN THE FUCKIN' REHEARSAL"}</button>
        <button type="button" onClick={next} disabled={!model.events.length}>NEWER RECEIPT →</button>
      </div>

      {model.event ? (
        <>
          <div className="hr72-warning">
            <strong>REHEARSAL / HISTORICAL REPLAY</strong>
            <span>{mobReplayBannerLine(model.ticker, model.eventType)}</span>
          </div>

          <div className="hr72-building" key={runId}>
            <div className="hr72-rooms">
              {ROOMS.map((room) => (
                <article key={room.key} className={`${room.key === targetRoom ? "is-target" : ""}`}>
                  <span>{room.code}</span>
                  <strong>{room.label}</strong>
                  {room.key === targetRoom ? <em>SCENE ROOM</em> : null}
                </article>
              ))}
            </div>
            <div className="hr72-corridor" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /></div>

            <div className="hr72-travelers">
              {model.cast.map((key, index) => {
                const style: TravelerStyle = {
                  "--start-x": roomX(HOME_ROOM[key]),
                  "--end-x": roomX(targetRoom),
                  "--travel-delay": `${index * 180}ms`,
                };
                return (
                  <div className={`hr72-traveler ${key === "skeptic" ? "is-red" : ""}`} key={`${runId}:${key}`} style={style}>
                    <div className="hr72-traveler-avatar">
                      <CinematicCharacterPortrait characterKey={key} active={playing} reacting={playing} variant={key === "max" ? "boss" : "card"} showLabel={false} />
                    </div>
                    <strong>{LIVING_CAST[key].displayName}</strong>
                    <span>{ROOMS.find((room) => room.key === HOME_ROOM[key])?.code} → {ROOMS.find((room) => room.key === targetRoom)?.code}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="hr72-scene">
            <aside>
              <span>THE RECEIPT</span>
              <strong>{readable(model.eventType, "UNKNOWN EVENT")}</strong>
              <dl>
                <div><dt>TICKER</dt><dd>{model.ticker}</dd></div>
                <div><dt>CASE</dt><dd>{text(model.event.case_id, "NO CASE")}</dd></div>
                <div><dt>ENTITY</dt><dd>{text(model.event.entity_id, "NO ENTITY")}</dd></div>
                <div><dt>ROOM</dt><dd>{ROOMS.find((room) => room.key === targetRoom)?.label}</dd></div>
                <div><dt>AGE</dt><dd>{ageLabel(model.event.created_at)}</dd></div>
              </dl>
            </aside>

            <section className="hr72-dialogue">
              <header><span>THE FAMILY REENACTS THE RECEIPT</span><strong>MOB-NOIR NARRATIVE · NOT LITERAL AGENT SPEECH</strong></header>
              <div>
                {model.cast.map((key) => (
                  <article key={`${model.eventType}:${key}`} className={key === "skeptic" ? "is-red" : ""}>
                    <div className="hr72-dialogue-avatar">
                      <CinematicCharacterPortrait characterKey={key} active={playing} reacting={playing} variant={key === "max" ? "boss" : "scene"} showLabel={false} />
                    </div>
                    <div>
                      <header><strong>{LIVING_CAST[key].displayName}</strong><span>{LIVING_CAST[key].title}</span></header>
                      <blockquote>“{mobReactionLine(key, model.context)}”</blockquote>
                      <small>PRESENTATION-ONLY CHARACTER VOICE · EVENT IDENTITY REMAINS PERSISTED</small>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : (
        <div className="hr72-empty">NO PERSISTED RECEIPTS AVAILABLE · REPLAY CANNOT INVENT ONE</div>
      )}

      {error ? <div className="hr72-error">READ-ONLY SOURCE WARNING · {error}</div> : null}
    </section>
  );
}

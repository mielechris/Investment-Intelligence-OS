import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";
import { mobReactionLine } from "./mobVoice";
import "./LiveFactoryEpisodeV74.css";

type JsonObject = Record<string, unknown>;
type View = "floor" | "control";
type RoomKey = "pit" | "war" | "bullpen" | "commission" | "risk" | "paper" | "monitoring" | "learning";
type SceneOrigin = "AUTO_NEW_PERSISTED_EVENT" | "HISTORICAL_RECENT_WINDOW_RECAP";
type Phase = "idle" | "rolling" | "hold";

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

type Scene = {
  id: string;
  origin: SceneOrigin;
  event: FactoryEvent;
  eventType: string;
  ticker: string;
  caseId: string;
  entityId: string;
  room: RoomKey;
  cast: LivingCastKey[];
  promotion: Promotion | null;
  createdAtMs: number | null;
};

type CharacterStyle = CSSProperties & {
  "--delay": string;
};

const STORAGE_KEY = "iios.v74.seen-event-ids";
const MAX_SEEN = 250;
const AUTO_BACKFILL_LIMIT_MS = 15 * 60 * 1000;
const RECENT_RECAP_LIMIT = 8;

const ROOM_LABEL: Record<RoomKey, string> = {
  pit: "Intelligence Pit",
  war: "Macro War Room",
  bullpen: "Specialist Bullpen",
  commission: "The Commission",
  risk: "Risk Inspection",
  paper: "Paper Bay",
  monitoring: "Monitoring Office",
  learning: "The Confessional",
};

const ROOM_CODE: Record<RoomKey, string> = {
  pit: "PIT",
  war: "WAR",
  bullpen: "8A",
  commission: "IC",
  risk: "RK",
  paper: "P",
  monitoring: "M",
  learning: "9J",
};

const ROOM_CAST: Record<RoomKey, LivingCastKey[]> = {
  pit: ["max", "market_structure", "commodities", "skeptic"],
  war: ["max", "policy", "macro", "geo_weather"],
  bullpen: ["max", "fundamentals", "policy", "macro", "skeptic"],
  commission: ["max", "fundamentals", "skeptic", "portfolio"],
  risk: ["max", "portfolio", "skeptic", "fundamentals"],
  paper: ["max", "portfolio", "market_structure"],
  monitoring: ["max", "market_structure", "portfolio", "skeptic"],
  learning: ["max", "fundamentals", "skeptic", "portfolio"],
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

function ageLabel(ms: number | null): string {
  if (ms === null) return "AGE UNKNOWN";
  const seconds = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (seconds < 60) return `${seconds}s AGO`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m AGO`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h AGO`;
  return `${Math.floor(seconds / 86_400)}d AGO`;
}

function clockLabel(ms: number | null): string {
  if (ms === null) return "TIME UNKNOWN";
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function roomForEvent(eventType: string): RoomKey {
  const type = eventType.toUpperCase();
  if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) return "learning";
  if (type.includes("MONITOR") || type.includes("PORTFOLIO") || type.includes("THESIS")) return "monitoring";
  if (type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) return "paper";
  if (type.includes("RISK")) return "risk";
  if (type.includes("COMMITTEE") || type.includes("DECISION")) return "commission";
  if (type.includes("AGENT")) return "bullpen";
  if (type.includes("RESEARCH") || type.includes("EVIDENCE") || type.includes("INGEST")) return "war";
  return "pit";
}

function eventId(event: FactoryEvent): string {
  return [
    text(event.event_type, "UNKNOWN"),
    text(event.case_id, "NO_CASE"),
    text(event.entity_id, "NO_ENTITY"),
    text(event.created_at, "NO_TIME"),
  ].join("|");
}

function promotionFor(event: FactoryEvent, promotions: Promotion[]): Promotion | null {
  const caseId = text(event.case_id, "");
  if (!caseId) return null;
  return promotions.find((item) => text(item.case_id, "") === caseId) ?? null;
}

function tickerFor(event: FactoryEvent, promotion: Promotion | null): string {
  return text(record(event.payload).ticker, text(promotion?.ticker, "NO TICKER")).toUpperCase();
}

function isCastKey(value: string): value is LivingCastKey {
  return Object.prototype.hasOwnProperty.call(LIVING_CAST, value);
}

function persistedCast(promotion: Promotion | null): LivingCastKey[] {
  const raw = promotion?.agents?.agent_keys;
  if (!Array.isArray(raw)) return [];
  return raw.map(String).filter((key): key is LivingCastKey => isCastKey(key) && key !== "max");
}

function castFor(room: RoomKey, promotion: Promotion | null): LivingCastKey[] {
  const observed = persistedCast(promotion);
  return Array.from(new Set<LivingCastKey>([...ROOM_CAST[room], ...observed])).slice(0, 5);
}

function buildScene(event: FactoryEvent, promotions: Promotion[], origin: SceneOrigin): Scene {
  const eventType = text(event.event_type, "UNKNOWN_EVENT");
  const room = roomForEvent(eventType);
  const promotion = promotionFor(event, promotions);
  return {
    id: eventId(event),
    origin,
    event,
    eventType,
    ticker: tickerFor(event, promotion),
    caseId: text(event.case_id, "NO CASE"),
    entityId: text(event.entity_id, "NO ENTITY"),
    room,
    cast: castFor(room, promotion),
    promotion,
    createdAtMs: parseTime(event.created_at),
  };
}

function sceneContext(scene: Scene) {
  const confidence = scene.promotion?.committee?.confidence;
  return {
    eventType: scene.eventType,
    ticker: scene.ticker,
    disposition: readable(scene.promotion?.committee?.disposition),
    confidence: typeof confidence === "number" ? `${Math.round(confidence * (confidence <= 1 ? 100 : 1))}%` : "UNREPORTED",
    riskDecision: readable(scene.promotion?.risk?.decision),
    paperState: readable(scene.promotion?.paper_execution?.execution),
  };
}

function introLine(scene: Scene, continuity: Scene | null): string {
  if (continuity) {
    return `${scene.ticker} is back in ${ROOM_LABEL[scene.room]}. Last receipt in this window was ${readable(continuity.eventType)}. Nobody gets amnesia just because the screen changed.`;
  }
  return `${scene.ticker} just hit ${ROOM_LABEL[scene.room]}. New persisted receipt, same family rule: read the fuckin' evidence before anybody falls in love.`;
}

function speakerLine(scene: Scene, key: LivingCastKey, continuity: Scene | null): string {
  if (key === "max") return introLine(scene, continuity);
  return mobReactionLine(key, sceneContext(scene));
}

function safeLoadSeen(): Set<string> {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
  } catch {
    return new Set<string>();
  }
}

function persistSeen(ids: Set<string>) {
  try {
    const values = Array.from(ids).slice(-MAX_SEEN);
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(values));
  } catch {
    // Presentation-only memory failure must never affect IIOS state.
  }
}

async function loadOverview(signal: AbortSignal): Promise<LivingOverview> {
  const response = await fetch("/living/overview", {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`V7.4 episode source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingOverview>;
}

export default function LiveFactoryEpisodeV74({ view }: { view: View }) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queue, setQueue] = useState<Scene[]>([]);
  const [active, setActive] = useState<Scene | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [beatIndex, setBeatIndex] = useState(0);
  const [playedIds, setPlayedIds] = useState<string[]>([]);
  const initialized = useRef(false);
  const seenIds = useRef<Set<string>>(new Set());
  const phaseTimer = useRef<number | null>(null);

  useEffect(() => {
    seenIds.current = safeLoadSeen();
  }, []);

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

        const telemetry = record(next.validation?.layers?.factory_telemetry?.payload);
        const events = rows(telemetry.recent_meaningful_events) as FactoryEvent[];
        const promotions = rows(telemetry.recent_promotions) as Promotion[];

        if (!initialized.current) {
          for (const event of events) seenIds.current.add(eventId(event));
          persistSeen(seenIds.current);
          initialized.current = true;
          return;
        }

        const newlyPersisted: Scene[] = [];
        for (const event of [...events].reverse()) {
          const id = eventId(event);
          if (seenIds.current.has(id)) continue;
          seenIds.current.add(id);
          const scene = buildScene(event, promotions, "AUTO_NEW_PERSISTED_EVENT");
          const age = scene.createdAtMs === null ? Number.POSITIVE_INFINITY : Math.max(0, Date.now() - scene.createdAtMs);
          if (age <= AUTO_BACKFILL_LIMIT_MS) newlyPersisted.push(scene);
        }
        persistSeen(seenIds.current);
        if (newlyPersisted.length) {
          setQueue((existing) => {
            const known = new Set(existing.map((scene) => scene.id));
            return [...existing, ...newlyPersisted.filter((scene) => !known.has(scene.id))];
          });
        }
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "V7.4 episode source unavailable");
      }
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), 5_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, []);

  const model = useMemo(() => {
    const telemetry = record(snapshot?.validation?.layers?.factory_telemetry?.payload);
    const events = (rows(telemetry.recent_meaningful_events) as FactoryEvent[]).slice(0, 24);
    const promotions = rows(telemetry.recent_promotions) as Promotion[];
    const scenes = events.map((event) => buildScene(event, promotions, "HISTORICAL_RECENT_WINDOW_RECAP"));
    const validation = snapshot?.validation?.layers ?? {};
    const paper = record(telemetry.paper_fund);
    return {
      scenes,
      paper,
      marketValidation: validation.market_validation,
      shadowStrategy: validation.shadow_strategy,
      outcomeLearning: validation.outcome_learning,
    };
  }, [snapshot]);

  useEffect(() => {
    if (active || phase !== "idle" || !queue.length) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    setActive(next);
    setBeatIndex(0);
    setPhase("rolling");
  }, [active, phase, queue]);

  const continuity = useMemo(() => {
    if (!active) return null;
    const related = model.scenes
      .filter((scene) => scene.id !== active.id)
      .filter((scene) => scene.caseId === active.caseId || (scene.ticker !== "NO TICKER" && scene.ticker === active.ticker))
      .filter((scene) => {
        if (active.createdAtMs === null || scene.createdAtMs === null) return false;
        return scene.createdAtMs < active.createdAtMs;
      })
      .sort((a, b) => (b.createdAtMs ?? 0) - (a.createdAtMs ?? 0));
    return related[0] ?? null;
  }, [active, model.scenes]);

  useEffect(() => {
    if (!active || phase !== "rolling") return;
    if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current);
    const duration = active.cast[beatIndex] === "skeptic" ? 1500 : 2300;
    phaseTimer.current = window.setTimeout(() => {
      if (beatIndex + 1 < active.cast.length) {
        setBeatIndex((value) => value + 1);
      } else {
        setPhase("hold");
      }
    }, duration);
    return () => {
      if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current);
    };
  }, [active, beatIndex, phase]);

  useEffect(() => {
    if (!active || phase !== "hold") return;
    if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current);
    phaseTimer.current = window.setTimeout(() => {
      setPlayedIds((existing) => [...existing.filter((id) => id !== active.id), active.id].slice(-40));
      setActive(null);
      setBeatIndex(0);
      setPhase("idle");
    }, 2800);
    return () => {
      if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current);
    };
  }, [active, phase]);

  useEffect(() => () => {
    if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current);
  }, []);

  const playRecentRecap = () => {
    const recap = [...model.scenes]
      .sort((a, b) => (a.createdAtMs ?? 0) - (b.createdAtMs ?? 0))
      .slice(-RECENT_RECAP_LIMIT)
      .map((scene) => ({ ...scene, origin: "HISTORICAL_RECENT_WINDOW_RECAP" as const }));
    setActive(null);
    setPhase("idle");
    setBeatIndex(0);
    setQueue(recap);
  };

  const clearPresentationQueue = () => {
    setQueue([]);
    setActive(null);
    setPhase("idle");
    setBeatIndex(0);
  };

  const currentSpeaker = active ? active.cast[Math.min(beatIndex, active.cast.length - 1)] ?? null : null;
  const safety = snapshot?.safety ?? {};
  const validationStatus = readable(model.marketValidation?.availability, "WAITING");
  const shadowStatus = readable(record(model.shadowStrategy?.payload).status, readable(model.shadowStrategy?.availability, "WAITING"));
  const learningStatus = readable(record(model.outcomeLearning?.payload).status, readable(model.outcomeLearning?.availability, "WAITING"));

  return (
    <section className={`v74-shell v74-shell--${view} is-${phase}`} aria-label="V7.4 live factory episode engine">
      <header className="v74-header">
        <div>
          <span>V7.4 · LIVE FACTORY EPISODE ENGINE</span>
          <h2>NEW RECEIPT HITS THE FLOOR. THE FAMILY PICKS UP THE FUCKIN' STORY.</h2>
          <p>
            The browser watches persisted IIOS events, deduplicates them, queues only newly persisted near-current receipts for automatic scenes, and keeps stale/backfilled history out of the live queue. Historical recap is explicit and user-triggered.
          </p>
        </div>
        <div className="v74-stamp">
          <strong>AUTO DIRECTOR</strong>
          <span>READ ONLY · EVENT BOUND</span>
        </div>
      </header>

      <div className="v74-truth">
        <span>SOURCE · PERSISTED 9G RECENT EVENT WINDOW</span>
        <span>AUTO SCENE · NEW EVENT ID ONLY</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>WRITE AUTHORITY · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
      </div>

      <div className="v74-command-row">
        <div>
          <span>AUTO QUEUE</span>
          <strong>{queue.length}</strong>
          <small>new persisted receipts waiting</small>
        </div>
        <div>
          <span>RECENT WINDOW</span>
          <strong>{model.scenes.length}</strong>
          <small>history visible to this browser source</small>
        </div>
        <div>
          <span>PLAYED THIS BROWSER SESSION</span>
          <strong>{playedIds.length}</strong>
          <small>presentation memory only</small>
        </div>
        <button type="button" onClick={playRecentRecap} disabled={!model.scenes.length || phase === "rolling"}>
          ▶ PLAY RECENT WINDOW AS HISTORICAL RECAP
        </button>
        <button type="button" onClick={clearPresentationQueue} disabled={!queue.length && !active}>
          CLEAR PRESENTATION QUEUE
        </button>
      </div>

      <div className="v74-room-rail" aria-label="automatic room camera rail">
        {(Object.keys(ROOM_LABEL) as RoomKey[]).map((room) => (
          <article key={room} className={active?.room === room ? "is-camera" : ""}>
            <span>{ROOM_CODE[room]}</span>
            <strong>{ROOM_LABEL[room]}</strong>
            {active?.room === room ? <em>AUTO CAMERA</em> : null}
          </article>
        ))}
      </div>

      {active ? (
        <div className={`v74-stage is-${active.room} is-${active.origin === "HISTORICAL_RECENT_WINDOW_RECAP" ? "recap" : "auto"}`}>
          <aside className="v74-scene-receipt">
            <span>{active.origin === "AUTO_NEW_PERSISTED_EVENT" ? "NEW PERSISTED EVENT" : "HISTORICAL RECENT-WINDOW RECAP"}</span>
            <strong>{readable(active.eventType)}</strong>
            <dl>
              <div><dt>TICKER</dt><dd>{active.ticker}</dd></div>
              <div><dt>CASE</dt><dd>{active.caseId}</dd></div>
              <div><dt>ENTITY</dt><dd>{active.entityId}</dd></div>
              <div><dt>ROOM</dt><dd>{ROOM_LABEL[active.room]}</dd></div>
              <div><dt>AGE</dt><dd>{ageLabel(active.createdAtMs)}</dd></div>
            </dl>
            <footer>
              {active.origin === "AUTO_NEW_PERSISTED_EVENT"
                ? "AUTO-DIRECTED BECAUSE A NEW EVENT ID APPEARED AFTER THIS BROWSER SESSION STARTED."
                : "USER-TRIGGERED HISTORICAL RECAP · NOT CURRENT ACTIVITY."}
            </footer>
          </aside>

          <section className="v74-camera">
            <header>
              <div><span>AUTO CAMERA · {ROOM_CODE[active.room]}</span><strong>{ROOM_LABEL[active.room]}</strong></div>
              <em>{phase === "rolling" ? `BEAT ${beatIndex + 1} / ${active.cast.length}` : "SCENE HOLD"}</em>
            </header>

            <div className="v74-cast">
              {active.cast.map((key, index) => {
                const speaking = key === currentSpeaker && phase === "rolling";
                const style: CharacterStyle = { "--delay": `${index * 90}ms` };
                return (
                  <article key={`${active.id}:${key}`} className={`${speaking ? "is-speaking" : "is-reacting"} ${key === "skeptic" ? "is-red" : ""}`} style={style}>
                    <div className="v74-avatar">
                      <CinematicCharacterPortrait characterKey={key} active={speaking} reacting={speaking} variant={key === "max" ? "boss" : "scene"} showLabel={false} />
                    </div>
                    <strong>{LIVING_CAST[key].displayName}</strong>
                    <span>{LIVING_CAST[key].title}</span>
                    {speaking ? <blockquote>“{speakerLine(active, key, continuity)}”</blockquote> : null}
                  </article>
                );
              })}
            </div>

            <div className="v74-continuity">
              <span>STORY CONTINUITY · PERSISTED WINDOW ONLY</span>
              <strong>{continuity ? `${continuity.ticker} · ${readable(continuity.eventType)} · ${ageLabel(continuity.createdAtMs)}` : "NO EARLIER RELATED RECEIPT IN THE CURRENT WINDOW"}</strong>
            </div>
          </section>
        </div>
      ) : (
        <div className="v74-idle">
          <strong>AUTO DIRECTOR ARMED · NO NEW RECEIPT WAITING</strong>
          <span>Existing history is not replayed automatically on page load. Use the historical recap button if you want to watch the current persisted window.</span>
        </div>
      )}

      <div className="v74-lower-grid">
        <section className="v74-timeline">
          <header><span>EPISODE TIMELINE</span><strong>RECENT PERSISTED WINDOW · NOT CLAIMED AS FULL-DAY HISTORY</strong></header>
          <div>
            {[...model.scenes]
              .sort((a, b) => (b.createdAtMs ?? 0) - (a.createdAtMs ?? 0))
              .slice(0, 14)
              .map((scene) => (
                <article key={scene.id}>
                  <time>{clockLabel(scene.createdAtMs)}</time>
                  <strong>{scene.ticker}</strong>
                  <span>{readable(scene.eventType)}</span>
                  <em>{ROOM_CODE[scene.room]}</em>
                </article>
              ))}
            {!model.scenes.length ? <p>NO PERSISTED EVENT WINDOW AVAILABLE.</p> : null}
          </div>
        </section>

        <section className="v74-close">
          <header><span>END-OF-DAY HANDOFF</span><strong>EXISTING 9O DAILY EPISODE REMAINS AUTHORITATIVE FOR SESSION CLOSE</strong></header>
          <div className="v74-close-grid">
            <article><span>9H VALIDATION</span><strong>{validationStatus}</strong></article>
            <article><span>9I SHADOW</span><strong>{shadowStatus}</strong></article>
            <article><span>9J LEARNING</span><strong>{learningStatus}</strong></article>
            <article><span>PAPER NAV</span><strong>{typeof model.paper.nav === "number" ? `$${model.paper.nav.toLocaleString()}` : "UNREPORTED"}</strong></article>
          </div>
          <p>
            V7.4 directs newly persisted intraday scenes. Batch 9O remains the persisted session-close episode source for best calls, saves, misses, learning and tomorrow focus. V7.4 does not replace or fabricate that close.
          </p>
        </section>
      </div>

      <footer className="v74-integrity">
        <strong>EPISODE INTEGRITY</strong>
        <span>NO DUPLICATE EVENT IDS</span>
        <span>STALE INITIAL HISTORY DOES NOT AUTO-PLAY</span>
        <span>HISTORICAL RECAP IS EXPLICIT</span>
        <span>NO BACKEND WRITE METHODS</span>
        <span>LIVE CAPITAL FALSE</span>
      </footer>

      {error ? <div className="v74-error">READ-ONLY SOURCE WARNING · {error}</div> : null}
    </section>
  );
}

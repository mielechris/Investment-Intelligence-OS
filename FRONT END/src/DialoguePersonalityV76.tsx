import { useEffect, useMemo, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";
import {
  V76_PERSONALITY_BIBLE,
  v76ReactionLine,
  v76RelationshipSummary,
  v76SceneClose,
  v76SceneIntro,
  type V76DialogueContext,
  type V76RoomKey,
} from "./dialogueEngineV76";
import "./DialoguePersonalityV76.css";

type JsonObject = Record<string, unknown>;
type View = "floor" | "control";

type ValidationLayer = {
  availability?: string;
  age_seconds?: number | null;
  payload?: JsonObject | null;
};

type LivingOverview = {
  validation?: { layers?: { factory_telemetry?: ValidationLayer } };
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
  committee?: { disposition?: string | null; confidence?: number | null } | null;
  risk?: { decision?: string | null } | null;
  paper_execution?: { execution?: string | null } | null;
};

type ScriptBeat = {
  key: LivingCastKey;
  line: string;
};

const CAST_ORDER: LivingCastKey[] = [
  "max",
  "policy",
  "macro",
  "fundamentals",
  "market_structure",
  "commodities",
  "geo_weather",
  "skeptic",
  "portfolio",
];

const ROOM_CAST: Record<V76RoomKey, LivingCastKey[]> = {
  pit: ["max", "market_structure", "commodities", "skeptic"],
  war: ["max", "policy", "macro", "geo_weather"],
  bullpen: ["max", "fundamentals", "policy", "macro", "skeptic"],
  commission: ["max", "fundamentals", "skeptic", "portfolio"],
  risk: ["max", "portfolio", "skeptic", "fundamentals"],
  paper: ["max", "portfolio", "market_structure"],
  monitoring: ["max", "market_structure", "portfolio", "skeptic"],
  learning: ["max", "fundamentals", "skeptic", "portfolio"],
  max: ["max", "skeptic", "portfolio"],
  unknown: ["max", "policy", "skeptic"],
};

const ROOM_LABEL: Record<V76RoomKey, string> = {
  pit: "Intelligence Pit",
  war: "Macro War Room",
  bullpen: "Specialist Bullpen",
  commission: "The Commission",
  risk: "Risk Inspection",
  paper: "Paper Bay",
  monitoring: "Monitoring Office",
  learning: "The Confessional",
  max: "MAX's Office",
  unknown: "Back Room",
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

function roomForEvent(eventType: string): V76RoomKey {
  const type = eventType.toUpperCase();
  if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) return "learning";
  if (type.includes("MONITOR") || type.includes("PORTFOLIO") || type.includes("THESIS")) return "monitoring";
  if (type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) return "paper";
  if (type.includes("RISK")) return "risk";
  if (type.includes("COMMITTEE") || type.includes("DECISION")) return "commission";
  if (type.includes("AGENT")) return "bullpen";
  if (type.includes("RESEARCH") || type.includes("EVIDENCE") || type.includes("INGEST")) return "war";
  if (type.includes("RADAR") || type.includes("PROMOT") || type.includes("CANDIDATE") || type.includes("OPPORTUNITY")) return "pit";
  return "unknown";
}

function eventId(event: FactoryEvent): string {
  return [
    text(event.event_type, "UNKNOWN"),
    text(event.case_id, "NO_CASE"),
    text(event.entity_id, "NO_ENTITY"),
    text(event.created_at, "NO_TIME"),
  ].join("|");
}

function promotionFor(event: FactoryEvent | null, promotions: Promotion[]): Promotion | null {
  if (!event) return null;
  const caseId = text(event.case_id, "");
  if (!caseId) return null;
  return promotions.find((item) => text(item.case_id, "") === caseId) ?? null;
}

function tickerFor(event: FactoryEvent | null, promotion: Promotion | null): string {
  if (!event) return "NO TICKER";
  return text(record(event.payload).ticker, text(promotion?.ticker, "NO TICKER")).toUpperCase();
}

async function loadOverview(signal: AbortSignal): Promise<LivingOverview> {
  const response = await fetch("/living/overview", {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`V7.6 dialogue source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingOverview>;
}

export default function DialoguePersonalityV76({ view }: { view: View }) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [selectedCharacter, setSelectedCharacter] = useState<LivingCastKey>("max");
  const [take, setTake] = useState(0);

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
        setError(reason instanceof Error ? reason.message : "V7.6 dialogue source unavailable");
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
    const events = (rows(telemetry.recent_meaningful_events) as FactoryEvent[]).slice(0, 18);
    const promotions = rows(telemetry.recent_promotions) as Promotion[];
    const safeIndex = events.length ? Math.min(selectedIndex, events.length - 1) : 0;
    const event = events[safeIndex] ?? null;
    const eventType = event ? text(event.event_type, "UNKNOWN_EVENT") : "NO_PERSISTED_EVENT";
    const room = roomForEvent(eventType);
    const promotion = promotionFor(event, promotions);
    const ticker = tickerFor(event, promotion);
    const confidence = promotion?.committee?.confidence;
    const priorEvent = events
      .slice(safeIndex + 1)
      .find((item) => {
        const sameCase = text(item.case_id, "") && text(item.case_id, "") === text(event?.case_id, "");
        const priorTicker = text(record(item.payload).ticker, "").toUpperCase();
        return sameCase || (ticker !== "NO TICKER" && priorTicker === ticker);
      }) ?? null;
    const baseContext: V76DialogueContext = {
      eventType,
      ticker,
      room,
      disposition: readable(promotion?.committee?.disposition),
      confidence: typeof confidence === "number" ? `${Math.round(confidence * (confidence <= 1 ? 100 : 1))}%` : "UNREPORTED",
      riskDecision: readable(promotion?.risk?.decision),
      paperState: readable(promotion?.paper_execution?.execution),
      continuityEventType: priorEvent ? text(priorEvent.event_type, "") : undefined,
      seed: event ? `${eventId(event)}|take:${take}` : `NO_EVENT|take:${take}`,
      cast: ROOM_CAST[room],
    };

    const script: ScriptBeat[] = [];
    if (event) {
      script.push({ key: "max", line: v76SceneIntro(baseContext) });
      let previous: LivingCastKey = "max";
      for (const key of ROOM_CAST[room].filter((item) => item !== "max")) {
        const context: V76DialogueContext = {
          ...baseContext,
          previousSpeaker: previous,
          seed: `${baseContext.seed}|speaker:${key}`,
        };
        script.push({ key, line: v76ReactionLine(key, context) });
        previous = key;
      }
      script.push({
        key: "max",
        line: v76SceneClose({
          ...baseContext,
          previousSpeaker: previous,
          seed: `${baseContext.seed}|close`,
        }),
      });
    }

    return { events, safeIndex, event, eventType, room, promotion, ticker, priorEvent, script, context: baseContext };
  }, [snapshot, selectedIndex, take]);

  useEffect(() => {
    if (selectedIndex !== model.safeIndex) setSelectedIndex(model.safeIndex);
  }, [model.safeIndex, selectedIndex]);

  useEffect(() => {
    setTake(0);
  }, [model.event ? eventId(model.event) : "NO_EVENT"]);

  const personality = V76_PERSONALITY_BIBLE[selectedCharacter];
  const relationships = v76RelationshipSummary(selectedCharacter);
  const safety = snapshot?.safety ?? {};

  return (
    <section className={`v76-shell v76-shell--${view}`} aria-label="V7.6 dialogue and personality engine">
      <header className="v76-header">
        <div>
          <span>V7.6 · DIALOGUE + PERSONALITY ENGINE</span>
          <h2>THEY GOT FACES. NOW GIVE THE BASTARDS A MEMORY, A VOICE, AND SOMEBODY TO ARGUE WITH.</h2>
          <p>Persisted receipts supply facts. V7.6 supplies presentation-only character voice, cadence, rivalries, callbacks and alternate takes. Dialogue is never raw model output and never creates evidence, approval, risk authority or execution.</p>
        </div>
        <div className="v76-seal">
          <strong>PRESENTATION ONLY</strong>
          <span>RECEIPT-BOUND · NOT MODEL SPEECH</span>
        </div>
      </header>

      <div className="v76-truth">
        <span>SOURCE · PERSISTED 9G RECEIPTS</span>
        <span>ANTI-REPEAT · RECEIPT + TAKE SEED</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>WRITE AUTHORITY · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
      </div>

      {error ? (
        <div className={`v76-source-state ${snapshot ? "is-retrying" : "is-hard-failure"}`}>
          <strong>
            {snapshot
              ? "SOURCE POLL MISSED · LAST GOOD RECEIPT RETAINED"
              : "DIALOGUE SOURCE UNAVAILABLE"}
          </strong>
          <span>
            {snapshot
              ? "Presentation remains bound to the last successful persisted snapshot. Retrying automatically."
              : error}
          </span>
        </div>
      ) : null}

      <div className="v76-layout">
        <aside className="v76-bible">
          <header>
            <span>THE FAMILY BIBLE</span>
            <strong>NINE VOICES. ZERO GENERIC CORPORATE BULLSHIT.</strong>
          </header>
          <div className="v76-cast-grid">
            {CAST_ORDER.map((key) => (
              <button
                className={selectedCharacter === key ? "is-selected" : ""}
                key={key}
                type="button"
                onClick={() => setSelectedCharacter(key)}
              >
                <CinematicCharacterPortrait characterKey={key} variant="card" showLabel={false} />
                <span>{LIVING_CAST[key].displayName}</span>
                <small>{V76_PERSONALITY_BIBLE[key].archetype}</small>
              </button>
            ))}
          </div>

          <article className="v76-profile">
            <span>{personality.displayName}</span>
            <h3>{personality.archetype}</h3>
            <p>{personality.cadence}</p>
            <dl>
              <div><dt>OBSESSES OVER</dt><dd>{personality.obsessions.join(" · ")}</dd></div>
              <div><dt>SIGNATURE MOVES</dt><dd>{personality.signatureMoves.join(" · ")}</dd></div>
              <div><dt>NEVER SOUNDS LIKE</dt><dd>{personality.neverSoundsLike.join(" · ")}</dd></div>
              <div><dt>PROFANITY</dt><dd>{personality.profanity.toUpperCase()}</dd></div>
            </dl>
            <div className="v76-rivalries">
              <strong>FAMILY DYNAMICS</strong>
              {relationships.length ? relationships.map((item, index) => (
                <p key={`${item.from}:${item.to}:${index}`}>
                  {LIVING_CAST[item.from].displayName} ↔ {LIVING_CAST[item.to].displayName} · {item.dynamic}
                </p>
              )) : <p>No hard-coded rivalry. Still allowed to insult everybody equally.</p>}
            </div>
          </article>
        </aside>

        <main className="v76-script-room">
          <header>
            <div>
              <span>CURRENT RECEIPT DIALOGUE ROOM</span>
              <strong>{model.event ? `${model.ticker} · ${readable(model.eventType)}` : "NO PERSISTED RECEIPT AVAILABLE"}</strong>
              <small>{model.event ? `${ROOM_LABEL[model.room]} · ${ageLabel(model.event.created_at)}${model.priorEvent ? ` · CALLBACK AVAILABLE TO ${readable(model.priorEvent.event_type)}` : ""}` : "WAITING FOR 9G"}</small>
            </div>
            <div className="v76-take">
              <button type="button" disabled={!model.events.length} onClick={() => setSelectedIndex((value) => (value + 1) % model.events.length)}>← OLDER RECEIPT</button>
              <button type="button" disabled={!model.event} onClick={() => setTake((value) => value + 1)}>NEW PRESENTATION TAKE · {take + 1}</button>
              <button type="button" disabled={!model.events.length} onClick={() => setSelectedIndex((value) => (value - 1 + model.events.length) % model.events.length)}>NEWER RECEIPT →</button>
            </div>
          </header>

          {model.event ? (
            <div className="v76-script">
              {model.script.map((beat, index) => (
                <article className={`v76-beat v76-beat--${beat.key}`} key={`${model.context.seed}:${beat.key}:${index}`}>
                  <div className="v76-beat-avatar"><CinematicCharacterPortrait characterKey={beat.key} variant={beat.key === "max" ? "boss" : "scene"} showLabel={false} /></div>
                  <div>
                    <span>BEAT {index + 1} · {LIVING_CAST[beat.key].title}</span>
                    <strong>{LIVING_CAST[beat.key].displayName}</strong>
                    <blockquote>“{beat.line}”</blockquote>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="v76-empty">NO RECEIPT, NO SCRIPT. THE FAMILY DOESN'T INVENT A FUCKIN' MARKET EVENT TO TEST ITS ACTING.</div>
          )}

          <footer>
            <span>TAKE {take + 1} CHANGES WORDING ONLY</span>
            <span>RECEIPT FACTS NEVER CHANGE</span>
            <span>CHARACTER CALLBACKS ARE PRESENTATION MEMORY</span>
          </footer>
        </main>
      </div>
    </section>
  );
}

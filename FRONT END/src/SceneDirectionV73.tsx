import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";
import { mobAmbientLine, mobReactionLine } from "./mobVoice";
import "./SceneDirectionV73.css";

type JsonObject = Record<string, unknown>;
type View = "floor" | "control";
type Phase = "idle" | "entering" | "dialogue" | "complete";
type StationKey = "radar" | "research" | "agents" | "committee" | "risk" | "paper" | "monitoring" | "learning";
type RoomKey = "pit" | "war" | "bullpen" | "commission" | "risk" | "paper" | "monitoring" | "learning" | "max";
type SceneKind = "dossier" | "war" | "bullpen" | "commission" | "risk" | "paper" | "monitor" | "confessional" | "briefing";

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
  agents?: { agent_keys?: string[] | null } | null;
  committee?: { disposition?: string | null; confidence?: number | null } | null;
  risk?: { decision?: string | null } | null;
  paper_execution?: { execution?: string | null; notional?: number | null } | null;
};

type Point = { x: number; y: number; pose: string };
type Beat = {
  key: LivingCastKey;
  line: string;
  action: string;
  interrupt?: boolean;
  basis: string;
};

type CharacterStyle = CSSProperties & {
  "--home-x": string;
  "--home-y": string;
  "--target-x": string;
  "--target-y": string;
  "--entry-delay": string;
};

const ROOMS: Array<{ key: RoomKey; code: string; label: string; subtitle: string }> = [
  { key: "pit", code: "PIT", label: "Intelligence Pit", subtitle: "Radar · tape · dossier intake" },
  { key: "war", code: "WAR", label: "Macro War Room", subtitle: "Policy · rates · geopolitics" },
  { key: "bullpen", code: "8A", label: "Specialist Bullpen", subtitle: "Eight-agent analysis" },
  { key: "commission", code: "IC", label: "The Commission", subtitle: "Governed synthesis" },
  { key: "risk", code: "RK", label: "Risk Inspection", subtitle: "Capital gate" },
  { key: "paper", code: "P", label: "Paper Bay", subtitle: "Rehearsal only" },
  { key: "monitoring", code: "M", label: "Monitoring Office", subtitle: "Thesis surveillance" },
  { key: "learning", code: "9J", label: "The Confessional", subtitle: "Outcome learning" },
  { key: "max", code: "MAX", label: "MAX's Office", subtitle: "Command overlook" },
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

const HOME_POINT: Record<LivingCastKey, Point> = {
  max: { x: 88, y: 18, pose: "boss" },
  policy: { x: 17, y: 18, pose: "binder" },
  macro: { x: 27, y: 18, pose: "rates" },
  fundamentals: { x: 43, y: 70, pose: "ledger" },
  market_structure: { x: 11, y: 70, pose: "tape" },
  commodities: { x: 24, y: 70, pose: "physical" },
  geo_weather: { x: 37, y: 18, pose: "map" },
  skeptic: { x: 64, y: 70, pose: "red-team" },
  portfolio: { x: 81, y: 70, pose: "risk" },
};

const FORMATIONS: Record<RoomKey, Point[]> = {
  pit: [
    { x: 31, y: 28, pose: "dossier-head" }, { x: 46, y: 22, pose: "tape-left" }, { x: 59, y: 34, pose: "dossier-right" },
    { x: 39, y: 57, pose: "huddle-left" }, { x: 57, y: 59, pose: "huddle-right" },
  ],
  war: [
    { x: 20, y: 28, pose: "map-left" }, { x: 39, y: 21, pose: "rates-center" }, { x: 60, y: 29, pose: "map-right" },
    { x: 31, y: 61, pose: "brief-left" }, { x: 57, y: 60, pose: "brief-right" },
  ],
  bullpen: [
    { x: 23, y: 26, pose: "desk-left" }, { x: 42, y: 22, pose: "lead" }, { x: 62, y: 27, pose: "desk-right" },
    { x: 34, y: 61, pose: "file-left" }, { x: 60, y: 61, pose: "file-right" },
  ],
  commission: [
    { x: 19, y: 25, pose: "table-left" }, { x: 42, y: 18, pose: "table-head" }, { x: 66, y: 25, pose: "table-right" },
    { x: 31, y: 61, pose: "table-near-left" }, { x: 58, y: 61, pose: "table-near-right" },
  ],
  risk: [
    { x: 24, y: 25, pose: "inspection-left" }, { x: 46, y: 18, pose: "gatekeeper" }, { x: 68, y: 25, pose: "inspection-right" },
    { x: 36, y: 62, pose: "line-left" }, { x: 60, y: 62, pose: "line-right" },
  ],
  paper: [
    { x: 31, y: 24, pose: "ticket-left" }, { x: 53, y: 20, pose: "ticket-head" }, { x: 68, y: 38, pose: "ticket-right" },
    { x: 38, y: 63, pose: "bay-left" }, { x: 62, y: 63, pose: "bay-right" },
  ],
  monitoring: [
    { x: 21, y: 25, pose: "screen-left" }, { x: 42, y: 20, pose: "screen-head" }, { x: 64, y: 25, pose: "screen-right" },
    { x: 31, y: 61, pose: "watch-left" }, { x: 59, y: 61, pose: "watch-right" },
  ],
  learning: [
    { x: 24, y: 24, pose: "confess-left" }, { x: 46, y: 18, pose: "confess-head" }, { x: 68, y: 24, pose: "confess-right" },
    { x: 35, y: 62, pose: "receipt-left" }, { x: 59, y: 62, pose: "receipt-right" },
  ],
  max: [
    { x: 46, y: 19, pose: "boss-desk" }, { x: 26, y: 39, pose: "visitor-left" }, { x: 66, y: 39, pose: "visitor-right" },
    { x: 36, y: 67, pose: "carpet-left" }, { x: 58, y: 67, pose: "carpet-right" },
  ],
};

const STATION_CAST: Record<StationKey, LivingCastKey[]> = {
  radar: ["max", "market_structure", "commodities", "skeptic"],
  research: ["max", "policy", "macro", "geo_weather"],
  agents: ["max", "fundamentals", "policy", "macro", "skeptic"],
  committee: ["max", "fundamentals", "skeptic", "portfolio"],
  risk: ["max", "portfolio", "skeptic", "fundamentals"],
  paper: ["max", "portfolio", "market_structure"],
  monitoring: ["max", "market_structure", "portfolio", "skeptic"],
  learning: ["max", "fundamentals", "skeptic", "portfolio"],
};

const QUIET_CAST: LivingCastKey[] = ["policy", "macro", "skeptic", "max"];

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

function sceneKindFor(station: StationKey | null, eventType: string): SceneKind {
  const type = eventType.toUpperCase();
  if (type.includes("PROMOT") || type.includes("RADAR") || station === "radar") return "dossier";
  if (station === "research") return "war";
  if (station === "agents") return "bullpen";
  if (station === "committee") return "commission";
  if (station === "risk") return "risk";
  if (station === "paper") return "paper";
  if (station === "monitoring") return "monitor";
  if (station === "learning") return "confessional";
  return "briefing";
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

function eventIdentity(event: FactoryEvent | null): string {
  if (!event) return "NO_EVENT";
  return [text(event.event_type, "UNKNOWN"), text(event.entity_id, "NO_ENTITY"), text(event.case_id, "NO_CASE"), text(event.created_at, "NO_TIME")].join("|");
}

function castFor(station: StationKey | null, promotion: Promotion | null): LivingCastKey[] {
  if (!station) return ["max"];
  const observed = persistedCast(promotion);
  const merged = Array.from(new Set<LivingCastKey>([...STATION_CAST[station], ...observed]));
  return merged.slice(0, 5);
}

function contextFor(eventType: string, ticker: string, promotion: Promotion | null) {
  const confidence = promotion?.committee?.confidence;
  return {
    eventType,
    ticker,
    disposition: readable(promotion?.committee?.disposition),
    confidence: typeof confidence === "number" ? `${Math.round(confidence * (confidence <= 1 ? 100 : 1))}%` : "UNREPORTED",
    riskDecision: readable(promotion?.risk?.decision),
    paperState: readable(promotion?.paper_execution?.execution),
  };
}

function introLine(kind: SceneKind, ticker: string): string {
  switch (kind) {
    case "dossier": return `${ticker} got a dossier and a chair. Nobody confuses that with a fuckin' coronation.`;
    case "war": return `${ticker} is in the war room. Frankie, Benny, Sal—tell me what can punch this thesis in the throat.`;
    case "bullpen": return `${ticker} hit the bullpen. Everybody gets one opinion and zero goddamn poetry.`;
    case "commission": return `${ticker} is before the Commission. Receipts on the table. Feelings under the table.`;
    case "risk": return `${ticker} is at Risk. Paulie owns the door. Nobody sweet-talks the capital gate.`;
    case "paper": return `${ticker} made the paper bay. Rehearsal money only, so keep your trader hard-on in your pants.`;
    case "monitor": return `${ticker} is on the monitors. Yesterday's thesis gets no pension and no fuckin' tenure.`;
    case "confessional": return `${ticker} is in the Confessional. Bring the original thesis, the outcome, and whichever ego needs last rites.`;
    default: return `${ticker} is on the floor. Everybody shut up long enough to read the receipt.`;
  }
}

function finalLine(kind: SceneKind, ticker: string): string {
  switch (kind) {
    case "commission": return `${ticker} stays on the record. When the market grades us, nobody edits the fuckin' minutes.`;
    case "risk": return `Whatever Risk says on ${ticker}, that's the gate. Charisma can go smoke outside.`;
    case "confessional": return `Write down what ${ticker} taught us before memory starts lying to protect somebody's feelings.`;
    default: return `${ticker} scene logged. Receipts stay. Bullshit leaves through the service entrance.`;
  }
}

function buildBeats(kind: SceneKind, cast: LivingCastKey[], eventType: string, ticker: string, promotion: Promotion | null): Beat[] {
  const context = contextFor(eventType, ticker, promotion);
  const beats: Beat[] = [{
    key: "max",
    line: introLine(kind, ticker),
    action: kind === "commission" ? "slaps the dossier onto the Commission table" : "calls the room to order",
    basis: "Narrative direction keyed to the selected persisted event type and room.",
  }];

  const others = cast.filter((key) => key !== "max");
  for (const key of others) {
    beats.push({
      key,
      line: mobReactionLine(key, context),
      action: key === "skeptic" ? "cuts into the room before anybody gets comfortable" : `takes the ${LIVING_CAST[key].title.toLowerCase()} beat`,
      interrupt: key === "skeptic",
      basis: persistedCast(promotion).includes(key)
        ? "Persisted participant lineage observed; wording is narrative presentation only."
        : "Room-matched narrative cast beat; not literal model speech.",
    });
  }

  beats.push({
    key: "max",
    line: finalLine(kind, ticker),
    action: kind === "risk" ? "shuts the gate and ends the argument" : "closes the scene and keeps the receipt",
    interrupt: kind === "risk",
    basis: "Narrative close bound to the selected persisted scene; no authority is created.",
  });
  return beats;
}

function roomTitle(kind: SceneKind): string {
  switch (kind) {
    case "dossier": return "THE DOSSIER WALK-UP";
    case "war": return "THE MACRO SHAKEDOWN";
    case "bullpen": return "THE BULLPEN PILE-ON";
    case "commission": return "THE COMMISSION HEARING";
    case "risk": return "THE CAPITAL SHAKEDOWN";
    case "paper": return "THE PAPER HANDOFF";
    case "monitor": return "THE NIGHT WATCH";
    case "confessional": return "THE CONFESSIONAL";
    default: return "THE BACK ROOM BRIEFING";
  }
}

async function loadOverview(signal: AbortSignal): Promise<LivingOverview> {
  const response = await fetch("/living/overview", { headers: { Accept: "application/json" }, cache: "no-store", signal });
  if (!response.ok) throw new Error(`V7.3 director source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingOverview>;
}

function SceneProp({ kind, ticker }: { kind: SceneKind; ticker: string }) {
  return (
    <div className={`v73-prop v73-prop--${kind}`} aria-hidden="true">
      <i /><i /><i />
      <strong>{kind === "dossier" ? ticker : roomTitle(kind)}</strong>
    </div>
  );
}

export default function SceneDirectionV73({ view }: { view: View }) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>("idle");
  const [beatIndex, setBeatIndex] = useState(-1);
  const [runId, setRunId] = useState(0);
  const phaseTimer = useRef<number | null>(null);
  const beatTimer = useRef<number | null>(null);

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
        setError(reason instanceof Error ? reason.message : "V7.3 director source unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
      if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current);
      if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
    };
  }, []);

  const model = useMemo(() => {
    const telemetry = record(snapshot?.validation?.layers?.factory_telemetry?.payload);
    const events = (rows(telemetry.recent_meaningful_events) as FactoryEvent[]).slice(0, 18);
    const promotions = rows(telemetry.recent_promotions) as Promotion[];
    const safeIndex = events.length ? Math.min(selectedIndex, events.length - 1) : 0;
    const event = events[safeIndex] ?? null;
    const eventType = event ? text(event.event_type, "UNKNOWN_EVENT") : "";
    const station = eventType ? stationForEvent(eventType) : null;
    const room = station ? STATION_ROOM[station] : "max";
    const promotion = promotionFor(event, promotions);
    const ticker = tickerFor(event, promotion);
    const kind = sceneKindFor(station, eventType);
    const cast = castFor(station, promotion);
    const beats = event ? buildBeats(kind, cast, eventType, ticker, promotion) : [];
    return { events, safeIndex, event, eventType, station, room, promotion, ticker, kind, cast, beats, identity: eventIdentity(event) };
  }, [snapshot, selectedIndex]);

  useEffect(() => {
    if (selectedIndex !== model.safeIndex) setSelectedIndex(model.safeIndex);
  }, [model.safeIndex, selectedIndex]);

  useEffect(() => {
    setPhase("idle");
    setBeatIndex(-1);
  }, [model.identity]);

  useEffect(() => {
    if (phase !== "dialogue" || beatIndex < 0) return;
    if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
    const current = model.beats[beatIndex];
    const duration = current?.interrupt ? 1650 : 2550;
    beatTimer.current = window.setTimeout(() => {
      if (beatIndex + 1 < model.beats.length) setBeatIndex((value) => value + 1);
      else setPhase("complete");
    }, duration);
    return () => {
      if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
    };
  }, [beatIndex, model.beats, phase]);

  const runScene = () => {
    if (!model.event) return;
    if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current);
    if (beatTimer.current !== null) window.clearTimeout(beatTimer.current);
    setRunId((value) => value + 1);
    setBeatIndex(-1);
    setPhase("entering");
    phaseTimer.current = window.setTimeout(() => {
      setPhase("dialogue");
      setBeatIndex(0);
    }, 2050);
  };

  const selectOlder = () => {
    if (!model.events.length) return;
    setSelectedIndex((value) => (value + 1) % model.events.length);
  };

  const selectNewer = () => {
    if (!model.events.length) return;
    setSelectedIndex((value) => (value - 1 + model.events.length) % model.events.length);
  };

  const safety = snapshot?.safety ?? {};
  const activeBeat = phase === "dialogue" && beatIndex >= 0 ? model.beats[beatIndex] ?? null : null;
  const transcriptCount = phase === "complete" ? model.beats.length : Math.max(0, beatIndex + 1);
  const transcript = model.beats.slice(0, transcriptCount);
  const formation = FORMATIONS[model.room] ?? FORMATIONS.max;

  return (
    <section className={`v73-shell v73-shell--${view} is-${phase} is-${model.kind}`} aria-label="V7.3 cinematic scene direction superbatch">
      <header className="v73-header">
        <div>
          <span>V7.3 · SCENE DIRECTION SUPERBATCH</span>
          <h2>THE FAMILY DOESN'T JUST SHOW UP. SOMEBODY DIRECTS THE FUCKIN' ROOM.</h2>
          <p>Real persisted receipts choose the scene. Room formations, entrances, interruptions, speech bubbles and mob-family dialogue are presentation-only reenactment. No character beat creates evidence, authority or execution.</p>
        </div>
        <div className="v73-stamp"><strong>DIRECTOR'S CUT</strong><span>HISTORICAL / PRESENTATION ONLY</span></div>
      </header>

      <div className="v73-truth">
        <span>RECEIPT · REAL PERSISTED 9G EVENT</span>
        <span>DIALOGUE · NARRATIVE ≠ RAW MODEL OUTPUT</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>WRITE AUTHORITY · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
      </div>

      <div className="v73-controls">
        <button type="button" onClick={selectOlder} disabled={!model.events.length || phase === "entering" || phase === "dialogue"}>← OLDER RECEIPT</button>
        <div>
          <span>RECEIPT {model.events.length ? model.safeIndex + 1 : 0} OF {model.events.length}</span>
          <strong>{model.event ? readable(model.eventType, "UNKNOWN EVENT") : "NO PERSISTED EVENT"}</strong>
          <small>{model.event ? `${model.ticker} · ${ageLabel(model.event.created_at)} · ${roomTitle(model.kind)}` : "WAITING FOR 9G"}</small>
        </div>
        <button className="v73-run" type="button" onClick={runScene} disabled={!model.event || phase === "entering" || phase === "dialogue"}>
          {phase === "entering" ? "CREW'S WALKIN' IN..." : phase === "dialogue" ? "SCENE ROLLING..." : phase === "complete" ? "↻ RUN THE FUCKIN' SCENE AGAIN" : "▶ DIRECT THE FUCKIN' SCENE"}
        </button>
        <button type="button" onClick={selectNewer} disabled={!model.events.length || phase === "entering" || phase === "dialogue"}>NEWER RECEIPT →</button>
      </div>

      {model.event ? (
        <>
          <div className="v73-marquee">
            <strong>{roomTitle(model.kind)}</strong>
            <span>{model.ticker} · {readable(model.eventType)} · {ROOMS.find((room) => room.key === model.room)?.label}</span>
            <em>{phase === "idle" ? "WAITING FOR ACTION" : phase === "entering" ? "CREW ENTERING" : phase === "dialogue" ? `BEAT ${beatIndex + 1} / ${model.beats.length}` : "SCENE HELD"}</em>
          </div>

          <div className={`v73-stage v73-stage--${model.room}`} key={runId}>
            <div className="v73-room-sign"><span>{ROOMS.find((room) => room.key === model.room)?.code}</span><strong>{ROOMS.find((room) => room.key === model.room)?.label}</strong></div>
            <SceneProp kind={model.kind} ticker={model.ticker} />

            {model.cast.map((key, index) => {
              const home = HOME_POINT[key];
              const target = formation[index % formation.length];
              const speaking = activeBeat?.key === key;
              const reacting = phase === "dialogue" && !speaking;
              const style: CharacterStyle = {
                "--home-x": `${home.x}%`, "--home-y": `${home.y}%`, "--target-x": `${target.x}%`, "--target-y": `${target.y}%`, "--entry-delay": `${index * 125}ms`,
              };
              return (
                <article
                  className={`v73-character ${speaking ? "is-speaking" : ""} ${reacting ? "is-reacting" : ""} ${activeBeat?.interrupt && speaking ? "is-interrupting" : ""} ${key === "skeptic" ? "is-red" : ""}`}
                  key={`${runId}:${model.identity}:${key}`}
                  style={style}
                >
                  <div className="v73-character-avatar">
                    <CinematicCharacterPortrait characterKey={key} active={phase !== "idle"} reacting={speaking} variant={key === "max" ? "boss" : "scene"} showLabel={false} />
                  </div>
                  <strong>{LIVING_CAST[key].displayName}</strong>
                  <span>{target.pose.replaceAll("-", " ")}</span>
                </article>
              );
            })}

            {activeBeat ? (
              <div className={`v73-bubble ${activeBeat.interrupt ? "is-interrupt" : ""}`}>
                <span>{LIVING_CAST[activeBeat.key].displayName} · {activeBeat.interrupt ? "INTERRUPTS" : activeBeat.action}</span>
                <blockquote>“{activeBeat.line}”</blockquote>
                <small>{activeBeat.basis}</small>
              </div>
            ) : phase === "complete" ? (
              <div className="v73-bubble is-complete"><span>SCENE HELD</span><blockquote>“Crew stays in formation. Receipt stays on the record. Nobody rewrites the fuckin' movie.”</blockquote></div>
            ) : null}
          </div>

          <div className="v73-lower-grid">
            <aside className="v73-receipt">
              <span>THE RECEIPT</span>
              <strong>{readable(model.eventType, "UNKNOWN EVENT")}</strong>
              <dl>
                <div><dt>TICKER</dt><dd>{model.ticker}</dd></div>
                <div><dt>CASE</dt><dd>{text(model.event.case_id, "NO CASE")}</dd></div>
                <div><dt>ENTITY</dt><dd>{text(model.event.entity_id, "NO ENTITY")}</dd></div>
                <div><dt>ROOM</dt><dd>{ROOMS.find((room) => room.key === model.room)?.label}</dd></div>
                <div><dt>AGE</dt><dd>{ageLabel(model.event.created_at)}</dd></div>
                <div><dt>LINEAGE</dt><dd>{persistedCast(model.promotion).length ? `${persistedCast(model.promotion).length} persisted specialist(s)` : "room-matched cast only"}</dd></div>
              </dl>
              <footer>{model.identity}</footer>
            </aside>

            <section className="v73-scene-log">
              <header><div><span>SCENE LOG</span><strong>{model.beats.length} DIRECTED BEATS</strong></div><em>{phase.toUpperCase()}</em></header>
              <div className="v73-beat-track">
                {model.beats.map((beat, index) => (
                  <div className={`${index === beatIndex && phase === "dialogue" ? "is-current" : ""} ${index < transcriptCount ? "is-done" : ""}`} key={`${beat.key}:${index}`}>
                    <span>{String(index + 1).padStart(2, "0")}</span><strong>{LIVING_CAST[beat.key].displayName}</strong><em>{beat.interrupt ? "CUTS IN" : beat.action}</em>
                  </div>
                ))}
              </div>
              <div className="v73-transcript">
                {transcript.map((beat, index) => (
                  <p key={`${beat.key}:transcript:${index}`}><strong>{LIVING_CAST[beat.key].displayName}:</strong> {beat.line}</p>
                ))}
                {!transcript.length ? <p className="is-empty">No dialogue plays until you direct the selected persisted receipt.</p> : null}
              </div>
            </section>
          </div>
        </>
      ) : (
        <section className="v73-quiet-floor">
          <header><span>QUIET FLOOR · FICTIONAL SET DRESSING ONLY</span><strong>NO PERSISTED EVENT → NO DIRECTED MARKET SCENE</strong></header>
          <div>{QUIET_CAST.map((key) => <article key={key}><CinematicCharacterPortrait characterKey={key} variant="card" showLabel={false} /><strong>{LIVING_CAST[key].displayName}</strong><p>{mobAmbientLine(key)}</p></article>)}</div>
        </section>
      )}

      {error ? <div className="v73-error">READ-ONLY DIRECTOR SOURCE WARNING · {error}</div> : null}
    </section>
  );
}

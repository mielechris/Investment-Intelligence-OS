import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";
import {
  v76ReactionLine,
  v76SceneClose,
  v76SceneIntro,
  type V76DialogueContext,
  type V76RoomKey,
} from "./dialogueEngineV76";
import {
  V77_VOICE_PROFILES,
  availableSpeechVoices,
  pickSpeechVoice,
  playV77SceneCue,
  speakV77Line,
  startV77RoomAmbience,
  stopV77Speech,
  type V77AmbienceHandle,
} from "./audioSoundstageV77";
import "./VoiceAudioSoundstageV77.css";

type JsonObject = Record<string, unknown>;
type View = "floor" | "control";

type ValidationLayer = {
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

type ScriptBeat = { key: LivingCastKey; line: string };

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

const AUTO_FRESH_MS = 15 * 60 * 1000;

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

function eventId(event: FactoryEvent | null): string {
  if (!event) return "NO_EVENT";
  return [
    text(event.event_type, "UNKNOWN"),
    text(event.case_id, "NO_CASE"),
    text(event.entity_id, "NO_ENTITY"),
    text(event.created_at, "NO_TIME"),
  ].join("|");
}

function promotionFor(event: FactoryEvent | null, promotions: Promotion[]): Promotion | null {
  const caseId = text(event?.case_id, "");
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
  if (!response.ok) throw new Error(`V7.7 soundstage source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingOverview>;
}

export default function VoiceAudioSoundstageV77({ view }: { view: View }) {
  const [snapshot, setSnapshot] = useState<LivingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [armed, setArmed] = useState(false);
  const [muted, setMuted] = useState(false);
  const [ambienceOn, setAmbienceOn] = useState(false);
  const [autoNarrate, setAutoNarrate] = useState(false);
  const [masterVolume, setMasterVolume] = useState(0.72);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [playing, setPlaying] = useState(false);
  const [activeBeat, setActiveBeat] = useState(-1);
  const ambienceRef = useRef<V77AmbienceHandle | null>(null);
  const initialReceiptRef = useRef(false);
  const lastAutoEventRef = useRef("NO_EVENT");

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const refresh = () => setVoices(availableSpeechVoices());
    refresh();
    window.speechSynthesis.addEventListener("voiceschanged", refresh);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", refresh);
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
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "V7.7 soundstage source unavailable");
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
    const event = events[0] ?? null;
    const eventType = event ? text(event.event_type, "UNKNOWN_EVENT") : "NO_PERSISTED_EVENT";
    const room = roomForEvent(eventType);
    const promotion = promotionFor(event, promotions);
    const ticker = tickerFor(event, promotion);
    const confidence = promotion?.committee?.confidence;
    const context: V76DialogueContext = {
      eventType,
      ticker,
      room,
      disposition: readable(promotion?.committee?.disposition),
      confidence: typeof confidence === "number" ? `${Math.round(confidence * (confidence <= 1 ? 100 : 1))}%` : "UNREPORTED",
      riskDecision: readable(promotion?.risk?.decision),
      paperState: readable(promotion?.paper_execution?.execution),
      seed: event ? `${eventId(event)}|soundstage` : "NO_EVENT|soundstage",
      cast: ROOM_CAST[room],
    };
    const script: ScriptBeat[] = [];
    if (event) {
      script.push({ key: "max", line: v76SceneIntro(context) });
      let previous: LivingCastKey = "max";
      for (const key of ROOM_CAST[room].filter((item) => item !== "max")) {
        script.push({
          key,
          line: v76ReactionLine(key, {
            ...context,
            previousSpeaker: previous,
            seed: `${context.seed}|${key}`,
          }),
        });
        previous = key;
      }
      script.push({
        key: "max",
        line: v76SceneClose({ ...context, previousSpeaker: previous, seed: `${context.seed}|close` }),
      });
    }
    return { event, eventType, room, ticker, context, script, identity: eventId(event) };
  }, [snapshot]);

  const effectiveVolume = muted ? 0 : masterVolume;

  const stopAll = useCallback(() => {
    stopV77Speech();
    setPlaying(false);
    setActiveBeat(-1);
  }, []);

  const playScene = useCallback(() => {
    if (!armed || !model.event || !model.script.length) return;
    stopV77Speech();
    setPlaying(true);
    setActiveBeat(-1);
    playV77SceneCue(model.room, effectiveVolume);
    model.script.forEach((beat, index) => {
      speakV77Line(
        beat.key,
        beat.line,
        effectiveVolume,
        voices,
        () => setActiveBeat(index),
        index === model.script.length - 1
          ? () => {
              setPlaying(false);
              setActiveBeat(-1);
            }
          : undefined,
      );
    });
  }, [armed, effectiveVolume, model.event, model.room, model.script, voices]);

  useEffect(() => {
    if (!armed || !ambienceOn) {
      ambienceRef.current?.stop();
      ambienceRef.current = null;
      return;
    }
    ambienceRef.current?.stop();
    ambienceRef.current = startV77RoomAmbience(model.room, effectiveVolume);
    return () => {
      ambienceRef.current?.stop();
      ambienceRef.current = null;
    };
  }, [ambienceOn, armed, effectiveVolume, model.room]);

  useEffect(() => {
    if (!model.event) return;
    if (!initialReceiptRef.current) {
      initialReceiptRef.current = true;
      lastAutoEventRef.current = model.identity;
      return;
    }
    if (model.identity === lastAutoEventRef.current) return;
    const previous = lastAutoEventRef.current;
    lastAutoEventRef.current = model.identity;
    if (!armed || !autoNarrate || previous === "NO_EVENT") return;
    const created = parseTime(model.event.created_at);
    const age = created === null ? Number.POSITIVE_INFINITY : Math.max(0, Date.now() - created);
    if (age <= AUTO_FRESH_MS) playScene();
  }, [armed, autoNarrate, model.event, model.identity, playScene]);

  useEffect(() => {
    ambienceRef.current?.setVolume(effectiveVolume);
  }, [effectiveVolume]);

  useEffect(() => () => {
    stopV77Speech();
    ambienceRef.current?.stop();
  }, []);

  const arm = () => {
    setArmed(true);
    setVoices(availableSpeechVoices());
    playV77SceneCue(model.room, Math.min(masterVolume, 0.45));
  };

  const audition = (key: LivingCastKey) => {
    if (!armed || !model.event) return;
    stopV77Speech();
    const line = key === "max"
      ? v76SceneIntro({ ...model.context, seed: `${model.context.seed}|audition:max` })
      : v76ReactionLine(key, { ...model.context, seed: `${model.context.seed}|audition:${key}` });
    setPlaying(true);
    speakV77Line(key, line, effectiveVolume, voices, () => setActiveBeat(CAST_ORDER.indexOf(key)), () => {
      setPlaying(false);
      setActiveBeat(-1);
    });
  };

  const safety = snapshot?.safety ?? {};

  return (
    <section className={`v77-shell v77-shell--${view}`} aria-label="V7.7 voice and audio soundstage">
      <header className="v77-header">
        <div>
          <span>V7.7 · VOICE + AUDIO SOUNDSTAGE</span>
          <h2>THE FAMILY'S GOT A VOICE. YOU STILL GOTTA TURN THE FUCKIN' SOUND ON.</h2>
          <p>Audio is presentation-only and user-armed. Browser speech narrates receipt-bound V7.6 dialogue; synthesized room tone and scene cues never create evidence, model activity, approval or execution.</p>
        </div>
        <div className={`v77-seal ${armed ? "is-armed" : ""}`}>
          <strong>{armed ? "SOUNDSTAGE ARMED" : "AUDIO OFF BY DEFAULT"}</strong>
          <span>{armed ? "USER-ARMED · PRESENTATION ONLY" : "SAFARI AUTOPLAY RESPECTED"}</span>
        </div>
      </header>

      <div className="v77-truth">
        <span>SOURCE · PERSISTED 9G RECEIPT</span>
        <span>SPEECH · V7.6 NARRATIVE ≠ MODEL SPEECH</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
        <span>WRITE AUTHORITY · {safety.backend_write_permission ? "TRUE" : "NONE"}</span>
      </div>

      {error ? (
        <div className={`v77-source-state ${snapshot ? "is-retrying" : "is-hard-failure"}`}>
          <strong>{snapshot ? "SOURCE POLL MISSED · LAST GOOD RECEIPT RETAINED" : "SOUNDSTAGE SOURCE UNAVAILABLE"}</strong>
          <span>{snapshot ? "Audio remains bound to the last successful persisted snapshot. Retrying automatically." : error}</span>
        </div>
      ) : null}

      <div className="v77-console">
        <div className="v77-receipt">
          <span>CURRENT SOUNDSTAGE RECEIPT</span>
          <strong>{model.event ? `${model.ticker} · ${readable(model.eventType)}` : "NO PERSISTED RECEIPT"}</strong>
          <small>{model.event ? `${ROOM_LABEL[model.room]} · ${ageLabel(model.event.created_at)}` : "WAITING FOR 9G"}</small>
          <div className="v77-wave" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /></div>
        </div>

        <div className="v77-controls">
          <button className="v77-arm" type="button" onClick={arm} disabled={armed}>{armed ? "✓ SOUNDSTAGE ARMED" : "▶ ARM SOUNDSTAGE"}</button>
          <button type="button" onClick={playScene} disabled={!armed || !model.event || playing}>{playing ? "SCENE SPEAKING..." : "▶ PLAY REAL RECEIPT SCENE"}</button>
          <button type="button" onClick={stopAll} disabled={!playing}>■ STOP</button>
          <button type="button" onClick={() => setMuted((value) => !value)}>{muted ? "UNMUTE" : "MUTE"}</button>
          <button type="button" onClick={() => setAmbienceOn((value) => !value)} disabled={!armed}>ROOM TONE · {ambienceOn ? "ON" : "OFF"}</button>
          <button type="button" onClick={() => setAutoNarrate((value) => !value)} disabled={!armed}>NEW RECEIPTS AUTO-VOICE · {autoNarrate ? "ON" : "OFF"}</button>
          <label>
            <span>MASTER {Math.round(masterVolume * 100)}%</span>
            <input type="range" min="0" max="1" step="0.05" value={masterVolume} onChange={(event) => setMasterVolume(Number(event.target.value))} />
          </label>
        </div>
      </div>

      <div className="v77-voice-grid">
        {CAST_ORDER.map((key, index) => {
          const voice = pickSpeechVoice(key, voices);
          const active = activeBeat === index || (key === "max" && activeBeat === model.script.length - 1);
          return (
            <article className={active ? "is-speaking" : ""} key={key}>
              <CinematicCharacterPortrait characterKey={key} variant={key === "max" ? "boss" : "card"} showLabel={false} active={active} reacting={active} />
              <div>
                <span>{LIVING_CAST[key].displayName}</span>
                <strong>{V77_VOICE_PROFILES[key].label}</strong>
                <small>{voice ? `SYSTEM VOICE · ${voice.name}` : "SYSTEM VOICE · DEFAULT / LOADING"}</small>
                <p>{V77_VOICE_PROFILES[key].delivery}</p>
                <button type="button" disabled={!armed || !model.event || playing} onClick={() => audition(key)}>VOICE CHECK</button>
              </div>
            </article>
          );
        })}
      </div>

      <footer className="v77-footer">
        <span>AUTO-VOICE ONLY FIRES AFTER USER ARMING AND ONLY FOR A GENUINELY NEW RECEIPT WITHIN 15 MINUTES.</span>
        <strong>NO STALE HISTORY YELLING FROM THE SPEAKERS. NO AUDIO = AUTHORITY. NO FUCKIN' GHOST TRADES.</strong>
      </footer>
    </section>
  );
}

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import CinematicCharacterPortrait from "./CinematicCharacterPortrait";
import {
  LIVING_CAST,
  agentNarrativeForEvent,
  maxNarrativeForStation,
  type LivingCastKey,
} from "./livingCast";
import "./LivingCharacterBehaviorV7.css";

type JsonObject = Record<string, unknown>;
type BehaviorView = "floor" | "control";
type StationKey =
  | "radar"
  | "research"
  | "agents"
  | "committee"
  | "risk"
  | "paper"
  | "monitoring"
  | "learning";
type RoomKey =
  | "pit"
  | "war"
  | "bullpen"
  | "commission"
  | "risk"
  | "paper"
  | "monitoring"
  | "learning"
  | "max";

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
  opportunity_score?: number | null;
  agents?: {
    agent_keys?: string[] | null;
  } | null;
  committee?: {
    disposition?: string | null;
    confidence?: number | null;
  } | null;
  risk?: {
    decision?: string | null;
  } | null;
  paper_execution?: {
    execution?: string | null;
    notional?: number | null;
  } | null;
};

type DialogueLine = {
  key: LivingCastKey;
  line: string;
  basis: string;
  persistedParticipant: boolean;
};

type TravelerStyle = CSSProperties & {
  "--home-left": string;
  "--target-left": string;
  "--lane-top": string;
  "--travel-delay": string;
};

type Props = {
  view: BehaviorView;
};

const ROOMS: Array<{ key: RoomKey; code: string; label: string; subtitle: string }> = [
  { key: "pit", code: "PIT", label: "Intelligence Pit", subtitle: "Radar · tape · physical markets" },
  { key: "war", code: "WAR", label: "Macro War Room", subtitle: "Policy · rates · geopolitics" },
  { key: "bullpen", code: "8A", label: "Specialist Bullpen", subtitle: "Eight-agent analysis" },
  { key: "commission", code: "IC", label: "The Commission", subtitle: "Governed synthesis" },
  { key: "risk", code: "RK", label: "Risk Inspection", subtitle: "Capital gate" },
  { key: "paper", code: "P", label: "Paper Bay", subtitle: "Rehearsal only" },
  { key: "monitoring", code: "M", label: "Monitoring", subtitle: "Thesis surveillance" },
  { key: "learning", code: "9J", label: "Learning Room", subtitle: "Outcomes · postmortems" },
  { key: "max", code: "MAX", label: "MAX's Office", subtitle: "Command overlook" },
];

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

const STATION_FALLBACK_CAST: Record<StationKey, LivingCastKey[]> = {
  radar: ["market_structure", "skeptic"],
  research: ["policy", "macro", "geo_weather"],
  agents: ["policy", "macro", "fundamentals"],
  committee: ["fundamentals", "skeptic", "portfolio"],
  risk: ["portfolio", "skeptic"],
  paper: ["portfolio"],
  monitoring: ["market_structure", "portfolio"],
  learning: ["fundamentals", "skeptic", "portfolio"],
};

const AMBIENT_SET_DRESSING: Array<{ key: LivingCastKey; line: string }> = [
  { key: "policy", line: "Frankie is reading the fine print and silently judging everyone who skipped page 47." },
  { key: "macro", line: "Benny is staring at the yield curve like it personally owes him money." },
  { key: "skeptic", line: "Johnny No is red-penning optimism for recreational purposes." },
  { key: "max", line: "MAX is guarding the snacks and calling it governance." },
];

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

function eventLabel(value: unknown): string {
  return text(value, "UNKNOWN EVENT").replaceAll("_", " ").toUpperCase();
}

function readable(value: unknown, fallback = "WAITING"): string {
  return text(value, fallback).replaceAll("_", " ").toUpperCase();
}

function meaningful(value: unknown): boolean {
  const normalized = readable(value, "");
  return Boolean(normalized) && !["WAITING", "UNKNOWN", "NONE", "PENDING", "NOT EXECUTED", "—"].includes(normalized);
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

function pct01(value: unknown): string {
  const numeric = numberValue(value);
  if (numeric === null) return "UNREPORTED";
  const points = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
  return `${points.toFixed(0)}%`;
}

function pct(value: unknown): string {
  const numeric = numberValue(value);
  return numeric === null ? "—" : `${numeric.toFixed(1)}%`;
}

function money(value: unknown): string {
  const numeric = numberValue(value);
  return numeric === null
    ? "UNREPORTED"
    : numeric.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      });
}

function isLivingCastKey(value: string): value is LivingCastKey {
  return Object.prototype.hasOwnProperty.call(LIVING_CAST, value);
}

function persistedAgentKeys(promotion: Promotion | null): LivingCastKey[] {
  const keys = promotion?.agents?.agent_keys;
  if (!Array.isArray(keys)) return [];
  return keys
    .map((value) => String(value))
    .filter((value): value is LivingCastKey => isLivingCastKey(value) && value !== "max");
}

function promotionForEvent(event: FactoryEvent | null, promotions: Promotion[]): Promotion | null {
  if (!event) return null;
  const caseId = text(event.case_id, "");
  if (!caseId) return null;
  return promotions.find((promotion) => text(promotion.case_id, "") === caseId) ?? null;
}

function tickerForEvent(event: FactoryEvent | null, promotion: Promotion | null): string {
  if (!event) return "—";
  const payload = record(event.payload);
  return text(payload.ticker, text(promotion?.ticker, "NO TICKER")).toUpperCase();
}

function stripSpeakerPrefix(value: string): string {
  const colon = value.indexOf(":");
  return colon >= 0 ? value.slice(colon + 1).trim() : value;
}

function sceneCastKeys(station: StationKey | null, eventType: string, promotion: Promotion | null): LivingCastKey[] {
  const type = eventType.toUpperCase();
  const persisted = persistedAgentKeys(promotion);
  if (persisted.length) {
    return Array.from(new Set<LivingCastKey>(["max", ...persisted.slice(0, 3)]));
  }

  if (type.includes("COMMITTEE") || type.includes("DECISION")) return ["max", "fundamentals", "skeptic", "portfolio"];
  if (type.includes("RISK")) return ["max", "portfolio", "skeptic"];
  if (type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) return ["max", "portfolio"];
  if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) return ["max", "fundamentals", "skeptic", "portfolio"];
  if (type.includes("MONITOR")) return ["max", "market_structure", "portfolio"];
  if (type.includes("PROMOT") || type.includes("RADAR")) return ["max", "market_structure", "skeptic"];
  if (station) return Array.from(new Set<LivingCastKey>(["max", ...STATION_FALLBACK_CAST[station]]));
  return ["max"];
}

function reactionLine(
  key: LivingCastKey,
  station: StationKey | null,
  eventType: string,
  ticker: string,
  promotion: Promotion | null,
): string {
  const type = eventType.toUpperCase();
  const disposition = readable(promotion?.committee?.disposition, "UNREPORTED");
  const riskDecision = readable(promotion?.risk?.decision, "UNREPORTED");
  const paperState = readable(promotion?.paper_execution?.execution, "UNREPORTED");

  if (key === "max") return maxNarrativeForStation(station, eventType);

  if (type.includes("PROMOT") && key === "market_structure") {
    return `${ticker} got promoted off radar. Tape gets a closer look; it did not get canonized.`;
  }
  if (type.includes("PROMOT") && key === "skeptic") {
    return `${ticker} has a case number now. Congratulations. I still want the fastest way this thesis dies.`;
  }
  if ((type.includes("COMMITTEE") || type.includes("DECISION")) && key === "fundamentals") {
    return `Committee recorded ${disposition} on ${ticker}. Fine. Now show me the numbers that make that disposition survivable.`;
  }
  if ((type.includes("COMMITTEE") || type.includes("DECISION")) && key === "skeptic") {
    return `${ticker} reached the Commission. My contribution remains simple: attack the assumption everybody else got attached to.`;
  }
  if ((type.includes("COMMITTEE") || type.includes("DECISION")) && key === "portfolio") {
    return `Even a correct ${disposition} call can become a stupid position. Committee is not a sizing waiver.`;
  }
  if (type.includes("RISK") && key === "portfolio") {
    return `Risk recorded ${riskDecision} on ${ticker}. Capital does not care how emotionally attached we are to the thesis.`;
  }
  if (type.includes("RISK") && key === "skeptic") {
    return `${riskDecision} is the persisted risk state. Nobody gets to negotiate with the UI because they liked the idea.`;
  }
  if ((type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) && key === "portfolio") {
    return `${ticker} paper state is ${paperState}. Rehearsal means we get to learn without pretending simulated money is courage.`;
  }
  if (type.includes("MONITOR") && key === "market_structure") {
    return `${ticker} is in monitoring. Yesterday's thesis does not get tenure; the tape gets another vote.`;
  }
  if ((type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) && key === "fundamentals") {
    return `Outcome evidence is finally on the table for ${ticker}. Good. Memory beats storytelling after the fact.`;
  }
  if ((type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) && key === "skeptic") {
    return `Postmortem time. Nobody gets to edit the original thesis after seeing the answer key.`;
  }
  if ((type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) && key === "portfolio") {
    return `Learning only matters if it changes future discipline. Score the decision separately from the lucky or unlucky print.`;
  }

  return stripSpeakerPrefix(agentNarrativeForEvent(key, eventType));
}

function maxInterruptLine(station: StationKey | null, eventType: string, ticker: string): string | null {
  const type = eventType.toUpperCase();
  if (!eventType) return null;
  if (type.includes("FAIL") || type.includes("ERROR") || type.includes("REJECT")) {
    return `Hold it. ${ticker} just produced a failure/rejection event. Label the damn thing correctly before anybody turns plumbing into alpha.`;
  }
  if (type.includes("PROMOT")) {
    return `${ticker} got upstairs. A case number is not a victory parade. Everybody do the work.`;
  }
  if (type.includes("COMMITTEE") || type.includes("DECISION")) {
    return `The Commission is on the record for ${ticker}. Nobody rewrites the meeting after the market grades us.`;
  }
  if (type.includes("RISK")) {
    return `Risk moved on ${ticker}. Capital rules beat charisma. End of discussion.`;
  }
  if (type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) {
    return `${ticker} reached the paper bay. Fake money, real discipline, zero permission to get cute with live capital.`;
  }
  if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) {
    return `${ticker} is in the postmortem room. Receipts out. Memory on. Ego can wait in the hallway.`;
  }
  if (station) return maxNarrativeForStation(station, eventType);
  return null;
}

function commissionDebate(
  station: StationKey | null,
  ticker: string,
  promotion: Promotion | null,
): DialogueLine[] {
  if (station !== "committee") return [];
  const disposition = readable(promotion?.committee?.disposition, "UNREPORTED");
  const confidence = pct01(promotion?.committee?.confidence);
  return [
    {
      key: "fundamentals",
      line: `${ticker}: persisted Committee disposition ${disposition}, confidence ${confidence}. My job is to make the economics earn that confidence.`,
      basis: "Narrative reaction to persisted Committee disposition/confidence.",
      persistedParticipant: persistedAgentKeys(promotion).includes("fundamentals"),
    },
    {
      key: "skeptic",
      line: `${ticker}: ${disposition} is a checkpoint, not immunity. I want the falsifier that makes the room uncomfortable.`,
      basis: "Narrative Red Team reaction to the persisted Committee event.",
      persistedParticipant: persistedAgentKeys(promotion).includes("skeptic"),
    },
    {
      key: "portfolio",
      line: `${ticker}: confidence ${confidence}. Fine. Sizing still answers to concentration, correlation and drawdown—not applause.`,
      basis: "Narrative portfolio reaction to persisted Committee confidence.",
      persistedParticipant: persistedAgentKeys(promotion).includes("portfolio"),
    },
  ];
}

function roomLeft(room: RoomKey): string {
  const index = ROOMS.findIndex((item) => item.key === room);
  return `${((Math.max(index, 0) + 0.5) / ROOMS.length) * 100}%`;
}

async function loadOverview(signal: AbortSignal): Promise<LivingOverview> {
  const response = await fetch("/living/overview", {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`V7 behavior source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingOverview>;
}

export default function LivingCharacterBehaviorV7({ view }: Props) {
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
        setError(reason instanceof Error ? reason.message : "V7 behavior source unavailable");
      }
    };

    void refresh();
    const pollTimer = window.setInterval(() => void refresh(), 5_000);
    const clockTimer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(pollTimer);
      window.clearInterval(clockTimer);
    };
  }, []);

  const model = useMemo(() => {
    const telemetryLayer = snapshot?.validation?.layers?.factory_telemetry ?? {};
    const telemetry = record(telemetryLayer.payload);
    const events = rows(telemetry.recent_meaningful_events) as FactoryEvent[];
    const promotions = rows(telemetry.recent_promotions) as Promotion[];
    const latestEvent = events[0] ?? null;
    const eventType = latestEvent ? text(latestEvent.event_type, "UNKNOWN_EVENT") : "";
    const station = eventType ? stationForEvent(eventType) : null;
    const targetRoom = station ? STATION_ROOM[station] : null;
    const promotion = promotionForEvent(latestEvent, promotions);
    const ticker = tickerForEvent(latestEvent, promotion);
    const eventAge = latestEvent ? ageSeconds(latestEvent.created_at, now) : null;
    const recent = eventAge !== null && eventAge <= 120;
    const castKeys = latestEvent ? sceneCastKeys(station, eventType, promotion) : [];
    const dialogue: DialogueLine[] = castKeys.map((key) => ({
      key,
      line: reactionLine(key, station, eventType, ticker, promotion),
      basis:
        key === "max"
          ? "MAX narrative reaction bound to persisted event station/type."
          : persistedAgentKeys(promotion).includes(key)
            ? "Persisted agent lineage observed; wording is narrative presentation only."
            : "Station-matched narrative cast reaction; not literal model speech.",
      persistedParticipant: persistedAgentKeys(promotion).includes(key),
    }));

    const validationLayer = snapshot?.validation?.layers?.market_validation ?? {};
    const validation = record(validationLayer.payload);
    const validationMetrics = record(validation.metrics);
    const shadowLayer = snapshot?.validation?.layers?.shadow_strategy ?? {};
    const shadow = record(shadowLayer.payload);
    const outcomeLayer = snapshot?.validation?.layers?.outcome_learning ?? {};
    const outcome = record(outcomeLayer.payload);
    const recentOutcomes = rows(outcome.recent_outcomes);
    const latestOutcome = recentOutcomes[0] ?? null;

    return {
      telemetryLayer,
      events,
      latestEvent,
      eventType,
      station,
      targetRoom,
      promotion,
      ticker,
      eventAge,
      recent,
      castKeys,
      dialogue,
      maxInterrupt: latestEvent ? maxInterruptLine(station, eventType, ticker) : null,
      commissionLines: commissionDebate(station, ticker, promotion),
      validationLayer,
      validation,
      validationMetrics,
      shadowLayer,
      shadow,
      outcomeLayer,
      outcome,
      latestOutcome,
    };
  }, [snapshot, now]);

  const safety = snapshot?.safety ?? {};
  const stateLabel = !snapshot
    ? "CONNECTING"
    : error
      ? "SOURCE WARNING"
      : !model.latestEvent
        ? "NO PERSISTED SCENE"
        : model.recent
          ? "CAST IN MOTION"
          : "LAST SCENE · MOTION QUIET";

  const latestOutcomeTicker = model.latestOutcome ? text(model.latestOutcome.ticker, "UNKNOWN") : "—";
  const latestOutcomeLabel = model.latestOutcome
    ? readable(
        model.latestOutcome.decision_quality_label,
        readable(model.latestOutcome.market_outcome_label, "PENDING"),
      )
    : "WAITING";

  return (
    <section
      className={`lcb7-shell lcb7-shell--${view} ${model.recent ? "is-recent" : "is-history"}`}
      aria-label="V7 character behavior superbatch"
    >
      <header className="lcb7-header">
        <div>
          <span>V7.1 · CHARACTER BEHAVIOR SUPERBATCH</span>
          <h2>THE FACTORY HAS ROOMS. NOW THE CAST HAS SOMEWHERE TO GO.</h2>
          <p>
            Persisted IIOS events choose the room and the event-bound cast. Character travel, expressions,
            dialogue and off-hours set dressing are presentation only; they never create evidence or activity.
          </p>
        </div>
        <div className={`lcb7-state ${model.recent ? "is-live" : ""}`}>
          <i aria-hidden="true" />
          <strong>{stateLabel}</strong>
          <span>{model.latestEvent ? ageLabel(model.eventAge) : "WAITING FOR 9G EVENT"}</span>
        </div>
      </header>

      <div className="lcb7-truth">
        <span>ROOM ROUTE · PERSISTED EVENT TYPE</span>
        <span>CAST LINEAGE · PERSISTED WHEN AVAILABLE</span>
        <span>DIALOGUE · NARRATIVE PRESENTATION ONLY</span>
        <span>LIVE EXECUTION · {safety.live_execution ? "TRUE" : "FALSE"}</span>
        <span>TRADE AUTHORITY · {safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
      </div>

      <div className="lcb7-house">
        <div className="lcb7-room-grid">
          {ROOMS.map((room) => (
            <article
              key={room.key}
              className={`lcb7-room ${room.key === model.targetRoom ? "is-target" : ""}`}
            >
              <span>{room.code}</span>
              <strong>{room.label}</strong>
              <small>{room.subtitle}</small>
              <i aria-hidden="true" />
            </article>
          ))}
        </div>

        <div className="lcb7-corridor" aria-hidden="true">
          <i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i />
        </div>

        <div className="lcb7-travelers" aria-label="Event-bound character route">
          {model.castKeys.map((key, index) => {
            const target = model.targetRoom ?? HOME_ROOM[key];
            const style: TravelerStyle = {
              "--home-left": roomLeft(HOME_ROOM[key]),
              "--target-left": roomLeft(target),
              "--lane-top": `${86 + index * 66}px`,
              "--travel-delay": `${index * 120}ms`,
            };
            return (
              <div
                className={`lcb7-traveler ${key === "skeptic" ? "is-red" : ""}`}
                key={`${model.eventType}:${key}`}
                style={style}
              >
                <div className="lcb7-traveler-portrait">
                  <CinematicCharacterPortrait
                    characterKey={key}
                    active={model.recent}
                    reacting={model.recent}
                    variant={key === "max" ? "boss" : "card"}
                    showLabel={false}
                  />
                </div>
                <div>
                  <strong>{LIVING_CAST[key].displayName}</strong>
                  <span>{HOME_ROOM[key] === target ? "AT HOME STATION" : `${ROOMS.find((room) => room.key === HOME_ROOM[key])?.code} → ${ROOMS.find((room) => room.key === target)?.code}`}</span>
                </div>
              </div>
            );
          })}
        </div>

        {!model.castKeys.length ? (
          <div className="lcb7-house-empty">
            <strong>NO PERSISTED EVENT → NO EVENT-BOUND CHARACTER TRAVEL</strong>
            <span>The headquarters remains visually present without inventing a working scene.</span>
          </div>
        ) : null}
      </div>

      <div className="lcb7-scene-grid">
        <aside className="lcb7-evidence-card">
          <span>{model.recent ? "CURRENT PERSISTED SCENE" : "LAST PERSISTED SCENE"}</span>
          <h3>{model.latestEvent ? eventLabel(model.eventType) : "NO EVENT ON FILE"}</h3>
          <dl>
            <div><dt>TICKER</dt><dd>{model.ticker}</dd></div>
            <div><dt>CASE</dt><dd>{text(model.latestEvent?.case_id, "NO CASE")}</dd></div>
            <div><dt>ENTITY</dt><dd>{text(model.latestEvent?.entity_id, "NO ENTITY")}</dd></div>
            <div><dt>ROOM</dt><dd>{model.targetRoom ? ROOMS.find((room) => room.key === model.targetRoom)?.label : "UNMAPPED"}</dd></div>
            <div><dt>TIME</dt><dd>{model.latestEvent ? timeLabel(model.latestEvent.created_at) : "—"}</dd></div>
            <div><dt>AGE</dt><dd>{model.latestEvent ? ageLabel(model.eventAge) : "—"}</dd></div>
          </dl>
          <footer>9G PERSISTED EVENT IDENTITY · PRESENTATION DOES NOT ALTER STATE</footer>
        </aside>

        <section className="lcb7-dialogue-stage">
          <header>
            <div>
              <span>EVENT-BOUND EXCHANGE</span>
              <strong>{model.dialogue.length ? `${model.dialogue.length} CAST REACTIONS` : "CAST QUIET"}</strong>
            </div>
            <em>{model.recent ? "RECENT EVENT · MOTION ENABLED" : "HISTORICAL EVENT · MOTION DISABLED"}</em>
          </header>
          <div className="lcb7-dialogue-grid">
            {model.dialogue.map((item) => {
              const member = LIVING_CAST[item.key];
              return (
                <article className={`${item.key === "skeptic" ? "is-red" : ""}`} key={`${item.key}:${model.eventType}`}>
                  <div className="lcb7-dialogue-avatar">
                    <CinematicCharacterPortrait
                      characterKey={item.key}
                      active={model.recent}
                      reacting={model.recent}
                      variant={item.key === "max" ? "boss" : "scene"}
                      showLabel={false}
                    />
                  </div>
                  <div>
                    <header><strong>{member.displayName}</strong><span>{member.governedRole}</span></header>
                    <blockquote>“{item.line}”</blockquote>
                    <footer>{item.basis}</footer>
                  </div>
                </article>
              );
            })}
            {!model.dialogue.length ? (
              <div className="lcb7-dialogue-empty">No persisted event means no event dialogue.</div>
            ) : null}
          </div>
        </section>
      </div>

      {model.maxInterrupt ? (
        <section className="lcb7-max-interrupt">
          <div className="lcb7-max-mini">
            <CinematicCharacterPortrait characterKey="max" active={model.recent} reacting={model.recent} variant="card" showLabel={false} />
          </div>
          <div>
            <span>MAX CUTS IN · NARRATIVE REACTION</span>
            <strong>“{model.maxInterrupt}”</strong>
            <small>Triggered only because the displayed persisted event exists. This is not raw model speech.</small>
          </div>
        </section>
      ) : null}

      <div className="lcb7-deep-scenes">
        <section className={`lcb7-commission ${model.commissionLines.length ? "is-active" : ""}`}>
          <header>
            <div><span>THE COMMISSION</span><strong>Case debate table</strong></div>
            <em>{model.commissionLines.length ? "PERSISTED COMMITTEE EVENT" : "QUIET"}</em>
          </header>
          {model.commissionLines.length ? (
            <div className="lcb7-commission-table">
              {model.commissionLines.map((lineItem) => (
                <article key={lineItem.key} className={lineItem.key === "skeptic" ? "is-red" : ""}>
                  <div className="lcb7-commission-avatar">
                    <CinematicCharacterPortrait characterKey={lineItem.key} active={model.recent} reacting={model.recent} variant="card" showLabel={false} />
                  </div>
                  <strong>{LIVING_CAST[lineItem.key].displayName}</strong>
                  <p>“{lineItem.line}”</p>
                  <small>{lineItem.basis}</small>
                </article>
              ))}
            </div>
          ) : (
            <div className="lcb7-quiet-scene">
              <strong>NO COMMITTEE EVENT ON THE CURRENT SCENE</strong>
              <span>The Commission does not stage a fake argument to make the room look busy.</span>
            </div>
          )}
        </section>

        <section className="lcb7-learning-bay">
          <header>
            <div><span>VALIDATION → SHADOW → LEARNING</span><strong>Postmortem hooks</strong></div>
            <em>9H · 9I · 9J PERSISTED STATE</em>
          </header>
          <div className="lcb7-learning-metrics">
            <article>
              <span>9H INDEPENDENT</span>
              <strong>{model.validation.benchmark_complete === true ? "BENCHMARK COMPLETE" : readable(model.validationLayer.availability, "WAITING")}</strong>
              <small>Detect {pct(model.validationMetrics.detection_rate_pct)} · Miss {pct(model.validationMetrics.opportunity_miss_rate_pct)}</small>
            </article>
            <article>
              <span>9I SHADOW</span>
              <strong>{text(model.shadow.complete_session_count, "0")} / {text(model.shadow.minimum_complete_sessions_for_advice, "5")} SESSIONS</strong>
              <small>{Array.isArray(model.shadow.recommendations) ? model.shadow.recommendations.length : 0} recommendation(s) · shadow only</small>
            </article>
            <article>
              <span>9J OUTCOME</span>
              <strong>{text(model.outcome.outcome_count, "0")} OUTCOME(S)</strong>
              <small>{text(model.outcome.mature_5d_count, "0")} mature 5-day · exact lineage</small>
            </article>
          </div>

          {model.latestOutcome ? (
            <div className="lcb7-postmortem">
              <div>
                <span>LATEST PERSISTED POSTMORTEM</span>
                <strong>{latestOutcomeTicker}</strong>
              </div>
              <div>
                <span>DECISION / MARKET LABEL</span>
                <strong>{latestOutcomeLabel}</strong>
              </div>
              <div>
                <span>5D RETURN</span>
                <strong>{pct(model.latestOutcome.return_5d_pct)}</strong>
              </div>
              <footer>OUTCOME CARD IS RAW PERSISTED 9J STATE · CHARACTER COMMENTARY REMAINS SEPARATE</footer>
            </div>
          ) : (
            <div className="lcb7-postmortem lcb7-postmortem--waiting">
              <strong>POSTMORTEM ROOM ARMED</strong>
              <span>Waiting for the first eligible persisted 9J outcome. No fake win/loss stories are generated.</span>
            </div>
          )}
        </section>
      </div>

      {!model.recent ? (
        <section className="lcb7-ambient">
          <header>
            <div><span>OFF-HOURS / IDLE SET DRESSING</span><strong>THE BUILDING CAN BREATHE WITHOUT PRETENDING THE MARKET MOVED.</strong></div>
            <em>FICTIONAL AMBIENT PRESENTATION · NOT AGENT ACTIVITY</em>
          </header>
          <div className="lcb7-ambient-grid">
            {AMBIENT_SET_DRESSING.map((item) => (
              <article key={item.key}>
                <div className="lcb7-ambient-avatar">
                  <CinematicCharacterPortrait characterKey={item.key} variant="card" showLabel={false} />
                </div>
                <div>
                  <strong>{LIVING_CAST[item.key].displayName}</strong>
                  <p>{item.line}</p>
                  <small>SET DRESSING ONLY · NOT PERSISTED WORK</small>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {error ? <div className="lcb7-warning">LATEST READ-ONLY REFRESH WARNING · {error}</div> : null}
    </section>
  );
}

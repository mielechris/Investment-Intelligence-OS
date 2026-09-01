import { useEffect, useMemo, useState } from "react";
import { telemetryUrl } from "./telemetryEndpoint";
import "./CharacterStoryEngine.css";

type ValidationLayer = {
  availability: string;
  age_seconds?: number | null;
  payload?: Record<string, unknown> | null;
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
  safety: {
    direct_ledger_access: boolean;
    backend_access: string;
    backend_write_permission: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
};

type StoryEvent = {
  case_id?: string | null;
  event_type?: string | null;
  entity_id?: string | null;
  payload?: Record<string, unknown> | null;
  created_at?: string | null;
};

type Promotion = {
  case_id?: string | null;
  ticker?: string | null;
  topic?: string | null;
  opportunity_score?: number | null;
  radar_rank_score?: number | null;
  priority?: string | null;
  agents?: {
    completed_count?: number | null;
    agent_keys?: string[] | null;
    eight_agent_complete?: boolean | null;
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

type Persona = {
  key: string;
  name: string;
  title: string;
  room: string;
  temperament: string;
  mantra: string;
  vocabulary: string;
};

type StoryLine = {
  speakerKey: string;
  text: string;
  basis: string;
};

type StoryBeat = {
  id: string;
  event: StoryEvent;
  eventType: string;
  caseId: string;
  ticker: string;
  createdAt: string;
  lines: StoryLine[];
};

const PERSONAS: Persona[] = [
  {
    key: "max",
    name: "MAX",
    title: "Factory Foreman",
    room: "The Floor",
    temperament: "Gruff, decisive, irreverent, allergic to fake certainty.",
    mantra: "Evidence first. Ego gets a folding chair.",
    vocabulary: "damn work · no heroics · no bullshit",
  },
  {
    key: "policy",
    name: "Policy Analyst",
    title: "Regulatory Bloodhound",
    room: "Policy Floor",
    temperament: "Literal, skeptical of political theater, obsessed with transmission mechanisms.",
    mantra: "A headline is not a causal chain.",
    vocabulary: "authority · transmission · implementation",
  },
  {
    key: "macro",
    name: "Macro & Rates Analyst",
    title: "Regime Obsessive",
    room: "Macro Desk",
    temperament: "Cool-headed, probabilistic, permanently suspicious of one-factor explanations.",
    mantra: "Rates have friends. Find them.",
    vocabulary: "liquidity · regime · second-order",
  },
  {
    key: "fundamentals",
    name: "Fundamentals Analyst",
    title: "Numbers Before Vibes",
    room: "Fundamentals Lab",
    temperament: "Dry, forensic, unimpressed by narrative without cash-flow support.",
    mantra: "Good company and good price are different species.",
    vocabulary: "margins · balance sheet · valuation",
  },
  {
    key: "market_structure",
    name: "Market Structure Analyst",
    title: "Tape Reader",
    room: "Tape & Positioning",
    temperament: "Fast, sardonic, watches price behavior before believing the story around it.",
    mantra: "The tape can throw a chair without explaining why.",
    vocabulary: "flows · crowding · volatility · priced in",
  },
  {
    key: "commodities",
    name: "Commodities & Supply Chain Analyst",
    title: "Physical-World Realist",
    room: "Physical Markets",
    temperament: "Practical, seasonal, distrusts elegant theories that ignore actual supply.",
    mantra: "You cannot spreadsheet a missing truck, crop or barrel into existence.",
    vocabulary: "inventory · freight · seasonality · constraint",
  },
  {
    key: "geo_weather",
    name: "Geopolitics & Weather Analyst",
    title: "Scenario Disciplinarian",
    room: "Global Events Room",
    temperament: "Calm around ugly scenarios, strict about separating confirmed facts from tail risk.",
    mantra: "Drama is not probability.",
    vocabulary: "confirmed · scenario · chokepoint · shock",
  },
  {
    key: "skeptic",
    name: "Skeptic / Red Team",
    title: "Professional Buzzkill",
    room: "Red Team",
    temperament: "Adversarial, funny in a dark way, happiest when a weak thesis dies early.",
    mantra: "Cute thesis. Now tell me how it dies.",
    vocabulary: "falsifier · base rate · confirmation bias",
  },
  {
    key: "portfolio",
    name: "Portfolio Context Analyst",
    title: "Risk-Adjusted Adult",
    room: "Portfolio Control",
    temperament: "Blunt, capital-aware, refuses to confuse being right with sizing intelligently.",
    mantra: "A good idea can still be a stupid position.",
    vocabulary: "concentration · correlation · drawdown · opportunity cost",
  },
];

const PERSONA_BY_KEY = new Map(PERSONAS.map((persona) => [persona.key, persona]));

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
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

function money(value: unknown): string {
  const n = numberValue(value);
  return n === null
    ? "unreported notional"
    : n.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      });
}

function pct01(value: unknown): string {
  const n = numberValue(value);
  return n === null ? "unreported confidence" : `${Math.round(n * 100)}% confidence`;
}

function timeLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function statusTone(value: string): string {
  const normalized = value.toUpperCase();
  if (normalized.includes("AVAILABLE") || normalized.includes("HEALTHY") || normalized.includes("COMPLETE")) return "good";
  if (normalized.includes("FAIL") || normalized.includes("ERROR") || normalized.includes("STALE")) return "bad";
  return "warm";
}

function eventLabel(eventType: string): string {
  return eventType.replaceAll("_", " ");
}

function eventIdentity(event: StoryEvent): string {
  return [
    text(event.event_type, "UNKNOWN_EVENT"),
    text(event.entity_id, "NO_ENTITY"),
    text(event.case_id, "NO_CASE"),
    text(event.created_at, "NO_TIME"),
  ].join("|");
}

function promotionRows(snapshot: LivingSnapshot): Promotion[] {
  const telemetry = record(snapshot.validation.layers.factory_telemetry.payload);
  return rows(telemetry.recent_promotions) as Promotion[];
}

function promotionForEvent(event: StoryEvent, promotions: Promotion[]): Promotion | null {
  const caseId = text(event.case_id, "");
  if (!caseId) return null;
  return promotions.find((row) => text(row.case_id, "") === caseId) ?? null;
}

function tickerForEvent(event: StoryEvent, promotion: Promotion | null): string {
  const payload = record(event.payload);
  return text(payload.ticker, text(promotion?.ticker, "NO TICKER")).toUpperCase();
}

function line(speakerKey: string, textValue: string, basis: string): StoryLine {
  return { speakerKey, text: textValue, basis };
}

function agentLineKeys(promotion: Promotion | null): string[] {
  const keys = promotion?.agents?.agent_keys;
  return Array.isArray(keys)
    ? keys.filter((key) => PERSONA_BY_KEY.has(key)).slice(0, 3)
    : [];
}

function renderEventLines(event: StoryEvent, promotion: Promotion | null): StoryLine[] {
  const type = text(event.event_type, "UNKNOWN_EVENT").toUpperCase();
  const payload = record(event.payload);
  const ticker = tickerForEvent(event, promotion);
  const caseId = text(event.case_id, "NO CASE");
  const disposition = text(payload.disposition, text(promotion?.committee?.disposition, "UNREPORTED"));
  const confidence = payload.confidence ?? promotion?.committee?.confidence;
  const riskDecision = text(payload.decision, text(promotion?.risk?.decision, "UNREPORTED"));
  const notional = payload.notional ?? promotion?.paper_execution?.notional;
  const agentKeys = agentLineKeys(promotion);

  if (type === "OPPORTUNITY_PROMOTED_TO_CASE") {
    const lines = [
      line(
        "max",
        `${ticker} made it off radar and into governed case ${caseId}. Everybody stop admiring the ticker and do the damn work.`,
        "Persisted OPPORTUNITY_PROMOTED_TO_CASE event.",
      ),
      line(
        "skeptic",
        `Promotion is an invitation to attack ${ticker}, not a compliment. Cute thesis; now show me the failure case.`,
        "Narrative response to the persisted promotion event; not raw agent output.",
      ),
      line(
        "market_structure",
        `Radar score ${text(promotion?.opportunity_score, text(payload.opportunity_score, "unreported"))}. Price violence is evidence, not a marriage proposal.`,
        "Uses persisted promotion/radar score when available.",
      ),
    ];
    return lines;
  }

  if (type === "COMMITTEE_COMPLETE") {
    return [
      line(
        "max",
        `Committee recorded ${disposition} on ${ticker} at ${pct01(confidence)}. That is a checkpoint, not a champagne cork.`,
        "Persisted COMMITTEE_COMPLETE disposition/confidence.",
      ),
      line(
        "skeptic",
        disposition.toUpperCase().includes("NO_TRADE")
          ? `Good. A dead idea can be profitable if it dies before the paper fund has to babysit it.`
          : `${ticker} survived Committee. Fine. Surviving me is still on the schedule.`,
        "Narrative commentary keyed to the persisted Committee disposition.",
      ),
    ];
  }

  if (type === "RISK_COMPLETE") {
    return [
      line(
        "portfolio",
        `Risk recorded ${riskDecision} for ${ticker}. Being right and sizing like an idiot can coexist beautifully, so the leash stays on.`,
        "Persisted RISK_COMPLETE decision.",
      ),
      line(
        "max",
        `Risk gate has spoken on ${caseId}. No backdoor bullshit; the governed state is the state.`,
        "Narrative response to the persisted Risk event.",
      ),
    ];
  }

  if (type === "GOVERNED_PAPER_ORDER_CREATED") {
    return [
      line(
        "max",
        `A governed PAPER order exists for ${ticker}: ${money(notional)}. Paper means rehearsal, not permission to hallucinate live capital.`,
        "Persisted GOVERNED_PAPER_ORDER_CREATED event and notional when available.",
      ),
      line(
        "portfolio",
        `Now the market gets to grade the decision. No victory lap because a simulated order got a receipt.`,
        "Narrative commentary bound to the persisted paper-order event.",
      ),
    ];
  }

  if (type === "AUTO_MONITOR_FAILED") {
    return [
      line(
        "max",
        `Monitor failed for ${ticker}. That is plumbing being an asshole, not a market signal. Label it correctly.`,
        "Persisted AUTO_MONITOR_FAILED event.",
      ),
      line(
        "skeptic",
        `Operational failure first, investment conclusion never. Nobody gets to turn missing telemetry into a thesis.`,
        "Narrative response to the persisted monitoring failure.",
      ),
    ];
  }

  if (type === "OPPORTUNITY_AUTOMATION_CYCLE_FAILED") {
    return [
      line(
        "max",
        `Opportunity automation failed. Nobody invents what did not happen. Fix the machine; do not cosplay a completed cycle.`,
        "Persisted OPPORTUNITY_AUTOMATION_CYCLE_FAILED event.",
      ),
      line(
        "skeptic",
        `Missing output is not negative evidence. It is missing output. Congratulations, we have discovered the difference.`,
        "Narrative response to the persisted automation failure.",
      ),
    ];
  }

  if (type === "HIGH_SPEED_MARKET_RADAR_COMPLETE") {
    return [
      line(
        "market_structure",
        `9E finished a radar cycle: scanned ${text(payload.scanned_count, "—")}, queued ${text(payload.queued_count, "—")}, promoted ${text(payload.promoted_case_count, "—")}. The machine looked; it did not promise gold.`,
        "Persisted HIGH_SPEED_MARKET_RADAR_COMPLETE counts.",
      ),
      line(
        "skeptic",
        `A quiet radar is data too. Forcing a trade because the screen looks boring is how adults turn money into a cautionary tale.`,
        "Narrative commentary bound to the persisted completed radar cycle.",
      ),
    ];
  }

  if (agentKeys.length) {
    return agentKeys.map((key) => {
      const persona = PERSONA_BY_KEY.get(key) ?? PERSONA_BY_KEY.get("max")!;
      return line(
        key,
        `${persona.name} is present in the persisted ${ticker} lineage for ${caseId}. ${persona.mantra}`,
        "Only rendered because this specialist key exists in persisted promotion lineage.",
      );
    });
  }

  return [
    line(
      "max",
      `${eventLabel(type)} was persisted for ${ticker} / ${caseId}. No extra story until the ledger gives us one.`,
      "Fallback narrative uses only the persisted event identity.",
    ),
  ];
}

function buildStoryBeats(snapshot: LivingSnapshot): StoryBeat[] {
  const telemetry = record(snapshot.validation.layers.factory_telemetry.payload);
  const events = rows(telemetry.recent_meaningful_events) as StoryEvent[];
  const promotions = promotionRows(snapshot);
  return events.slice(0, 18).map((event) => {
    const promotion = promotionForEvent(event, promotions);
    const eventType = text(event.event_type, "UNKNOWN_EVENT").toUpperCase();
    return {
      id: eventIdentity(event),
      event,
      eventType,
      caseId: text(event.case_id, "NO CASE"),
      ticker: tickerForEvent(event, promotion),
      createdAt: text(event.created_at, ""),
      lines: renderEventLines(event, promotion),
    };
  });
}

async function loadSnapshot(signal: AbortSignal): Promise<LivingSnapshot> {
  const response = await fetch(telemetryUrl("/living/overview"), {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`9M story source unavailable: HTTP ${response.status}`);
  return response.json() as Promise<LivingSnapshot>;
}

function PersonaCard({ persona, active }: { persona: Persona; active: boolean }) {
  const initials = persona.key === "max"
    ? "M"
    : persona.name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase())
        .join("");
  return (
    <article className={`cse-persona ${active ? "is-active" : ""}`}>
      <div className="cse-persona-head">
        <div className="cse-avatar">{initials}</div>
        <div>
          <strong>{persona.name}</strong>
          <span>{persona.title}</span>
        </div>
      </div>
      <p>{persona.temperament}</p>
      <blockquote>{persona.mantra}</blockquote>
      <footer>
        <span>{persona.room}</span>
        <em>{persona.vocabulary}</em>
      </footer>
    </article>
  );
}

function StoryLineView({ storyLine }: { storyLine: StoryLine }) {
  const persona = PERSONA_BY_KEY.get(storyLine.speakerKey) ?? PERSONA_BY_KEY.get("max")!;
  return (
    <div className={`cse-line cse-line--${persona.key}`}>
      <div className="cse-line-speaker">
        <span>{persona.name}</span>
        <em>{persona.title}</em>
      </div>
      <div>
        <p>“{storyLine.text}”</p>
        <small>{storyLine.basis}</small>
      </div>
    </div>
  );
}

export default function CharacterStoryEngine() {
  const [snapshot, setSnapshot] = useState<LivingSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedBeatId, setSelectedBeatId] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    const refresh = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await loadSnapshot(controller.signal);
        if (disposed) return;
        setSnapshot(next);
        setError(null);
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setError(reason instanceof Error ? reason.message : "9M story engine source unavailable");
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

  const beats = useMemo(() => (snapshot ? buildStoryBeats(snapshot) : []), [snapshot]);
  const selectedBeat = useMemo(
    () => beats.find((beat) => beat.id === selectedBeatId) ?? beats[0] ?? null,
    [beats, selectedBeatId],
  );
  const activeSpeakers = new Set(selectedBeat?.lines.map((storyLine) => storyLine.speakerKey) ?? []);

  if (!snapshot) {
    return (
      <section className="cse-shell cse-waiting">
        <span>BATCH 9M · CHARACTER & STORY ENGINE</span>
        <h2>{error ? "STORY SOURCE WARM-UP" : "WAITING FOR PERSISTED FACTORY EVENTS"}</h2>
        <p>{error ?? "No character speaks until a real 9G audited event exists."}</p>
      </section>
    );
  }

  const telemetryLayer = snapshot.validation.layers.factory_telemetry;
  const h9 = snapshot.validation.layers.market_validation;
  const i9 = snapshot.validation.layers.shadow_strategy;
  const j9 = snapshot.validation.layers.outcome_learning;

  return (
    <section className="cse-shell">
      <div className="cse-hero">
        <div>
          <span>BATCH 9M · CHARACTER & STORY ENGINE</span>
          <h2>THE FACTORY CAN TALK — BUT ONLY WHEN THE FACTORY ACTUALLY DID SOMETHING.</h2>
          <p>
            Consistent personalities, dark/adult commentary and case debate are deterministic narrative renders of persisted 9G audited events. They are not raw agent output, not new evidence, not trade instructions and never create activity.
          </p>
        </div>
        <div className="cse-contract">
          <strong>EVENT-BOUND NARRATIVE</strong>
          <span>NO EVENT → NO DIALOGUE</span>
          <span>LIVE EXECUTION FALSE</span>
        </div>
      </div>

      <div className="cse-source-rail">
        <span className={`tone-${statusTone(telemetryLayer.availability)}`}>9G · {telemetryLayer.availability}</span>
        <span className={`tone-${statusTone(h9.availability)}`}>9H · {h9.availability}</span>
        <span className={`tone-${statusTone(i9.availability)}`}>9I · {i9.availability}</span>
        <span className={`tone-${statusTone(j9.availability)}`}>9J · {j9.availability}</span>
        <span>BACKEND · {snapshot.safety.backend_access}</span>
        <span>WRITE · {snapshot.safety.backend_write_permission ? "TRUE" : "FALSE"}</span>
      </div>

      <div className="cse-layout">
        <aside className="cse-cast">
          <div className="cse-heading">
            <span>PERSISTENT CAST BIBLE</span>
            <strong>Same people. Same instincts. Every day.</strong>
          </div>
          <div className="cse-persona-grid">
            {PERSONAS.map((persona) => (
              <PersonaCard key={persona.key} persona={persona} active={activeSpeakers.has(persona.key)} />
            ))}
          </div>
        </aside>

        <div className="cse-stage">
          <div className="cse-heading">
            <span>LIVE FACTORY STORY FEED</span>
            <strong>{beats.length ? `${beats.length} persisted beats` : "WAITING"}</strong>
          </div>
          <div className="cse-feed">
            {beats.map((beat) => (
              <button
                type="button"
                key={beat.id}
                className={beat.id === selectedBeat?.id ? "is-selected" : ""}
                onClick={() => setSelectedBeatId(beat.id)}
              >
                <div>
                  <span>{eventLabel(beat.eventType)}</span>
                  <strong>{beat.ticker}</strong>
                </div>
                <small>{beat.caseId}</small>
                <em>{timeLabel(beat.createdAt)}</em>
              </button>
            ))}
            {!beats.length ? (
              <div className="cse-empty">
                <strong>NO PERSISTED 9G STORY EVENT</strong>
                <p>The cast stays quiet. That is a valid factory state.</p>
              </div>
            ) : null}
          </div>

          <div className="cse-theater">
            {selectedBeat ? (
              <>
                <header>
                  <div>
                    <span>EVENT-BOUND DEBATE</span>
                    <h3>{selectedBeat.ticker} · {eventLabel(selectedBeat.eventType)}</h3>
                  </div>
                  <div className="cse-event-ref">
                    <strong>SOURCE EVENT</strong>
                    <span>{selectedBeat.caseId}</span>
                    <span>{text(selectedBeat.event.entity_id, "NO ENTITY")}</span>
                    <span>{timeLabel(selectedBeat.createdAt)}</span>
                  </div>
                </header>
                <div className="cse-lines">
                  {selectedBeat.lines.map((storyLine, index) => (
                    <StoryLineView key={`${selectedBeat.id}:${index}:${storyLine.speakerKey}`} storyLine={storyLine} />
                  ))}
                </div>
                <footer>
                  NARRATIVE RENDERING ONLY · Every line above is anchored to the displayed persisted event. It is not represented as literal historical speech from the model agent.
                </footer>
              </>
            ) : (
              <div className="cse-empty">
                <strong>WAITING FOR A REAL EVENT</strong>
                <p>No debate is generated from empty state.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {error ? <div className="cse-warning">LATEST REFRESH WARNING · {error}</div> : null}
    </section>
  );
}

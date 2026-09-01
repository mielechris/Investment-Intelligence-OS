import { useEffect, useMemo, useState } from "react";
import { telemetryUrl } from "./telemetryEndpoint";
import "./InteractiveCaseTheater.css";

type JsonObject = Record<string, unknown>;

type ValidationLayer = {
  availability: string;
  payload?: JsonObject | null;
};

type Promotion = {
  case_id?: string | null;
  ticker?: string | null;
  topic?: string | null;
  source_candidate_id?: string | null;
  promoted_at?: string | null;
  opportunity_score?: number | null;
  radar_rank_score?: number | null;
  priority?: string | null;
  agents?: {
    completed_count?: number | null;
    agent_keys?: string[] | null;
    eight_agent_complete?: boolean | null;
  } | null;
  committee?: JsonObject | null;
  risk?: JsonObject | null;
  paper_execution?: JsonObject | null;
};

type CaseRow = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  stage?: string | null;
  active_room?: string | null;
  latest_event?: string | null;
  latest_event_at?: string | null;
  agent_count?: number | null;
  committee?: string | null;
  risk?: string | null;
  paper_execution?: string | null;
  live_execution?: boolean;
};

type LivingSnapshot = {
  generated_at: string;
  validation: {
    layers: {
      factory_telemetry: ValidationLayer;
      outcome_learning: ValidationLayer;
    };
  };
  factory: {
    availability: string;
    payload?: { cases?: CaseRow[] } | null;
  };
  jesse_dislocation: {
    availability: string;
    payload?: { latest_scan?: JsonObject | null } | null;
  };
  safety: {
    direct_ledger_access: boolean;
    backend_access: string;
    backend_write_permission: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
};

type JourneyRow = {
  key?: string | null;
  label?: string | null;
  status?: string | null;
  object_id?: string | null;
  created_at?: string | null;
};

type CaseDetail = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  journey?: JourneyRow[];
  committee?: {
    disposition?: string | null;
    confidence?: number | null;
    headline?: string | null;
    summary?: string | null;
    decision_id?: string | null;
  } | null;
  risk?: {
    decision?: string | null;
    triggered_rules?: string[] | null;
    risk_authorization_id?: string | null;
  } | null;
  council?: {
    packet_id?: string | null;
    views?: JsonObject[] | null;
    skeptic_escalation_recommended?: boolean | null;
  } | null;
  monitoring?: {
    status?: string | null;
    created_at?: string | null;
    latest_return_pct?: number | null;
    thesis_flags?: string[] | null;
  } | null;
  paper_execution?: {
    execution?: string | null;
    reason?: string | null;
    execution_id?: string | null;
    notional?: number | null;
  } | null;
  trade_execution_permission?: boolean;
  live_execution?: boolean;
};

type TheaterCase = {
  caseId: string;
  ticker: string;
  topic: string;
  promotion: Promotion | null;
  overview: CaseRow | null;
  learning: JsonObject | null;
  jesse: JsonObject | null;
  provenance: "BOTH" | "9E RADAR" | "JESSE DISLOCATION" | "MANUAL / OTHER";
};

type TheaterStage = {
  key: string;
  label: string;
  status: string;
  source: string;
  sourceId: string;
  timestamp: string;
  headline: string;
  body: string;
  facts: Array<{ label: string; value: string }>;
  rawArtifact?: JsonObject | null;
};

type StoryEvent = {
  case_id?: string | null;
  event_type?: string | null;
  entity_id?: string | null;
  payload?: JsonObject | null;
  created_at?: string | null;
};

const STAGES = [
  ["DISCOVERY", "Discovery"],
  ["RESEARCH", "Research"],
  ["AGENTS", "8 Agents"],
  ["SKEPTIC", "Skeptic"],
  ["COMMITTEE", "Committee"],
  ["RISK", "Risk"],
  ["PAPER", "Paper"],
  ["MONITORING", "Monitoring"],
  ["OUTCOME", "Outcome"],
  ["LEARNING", "Learning"],
] as const;

const AGENT_NAMES: Record<string, string> = {
  policy: "Policy Analyst",
  macro: "Macro & Rates Analyst",
  fundamentals: "Fundamentals Analyst",
  market_structure: "Market Structure Analyst",
  commodities: "Commodities & Supply Chain Analyst",
  geo_weather: "Geopolitics & Weather Analyst",
  skeptic: "Skeptic / Red Team",
  portfolio: "Portfolio Context Analyst",
};

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function objectRows(value: unknown): JsonObject[] {
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
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function pct(value: unknown): string {
  const numeric = numberValue(value);
  return numeric === null ? "—" : `${numeric.toFixed(2)}%`;
}

function confidence(value: unknown): string {
  const numeric = numberValue(value);
  return numeric === null ? "—" : `${Math.round(numeric * 100)}%`;
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

function normalize(value: unknown): string {
  return text(value, "UNKNOWN").toUpperCase().replaceAll(" ", "_");
}

function timeLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "WAITING";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "WAITING";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function statusTone(value: string): string {
  const state = normalize(value);
  if (
    state.includes("COMPLETE") ||
    state.includes("RECORDED") ||
    state.includes("AVAILABLE") ||
    state.includes("OBSERVED") ||
    state.includes("APPROV") ||
    state.includes("PAPER_ORDER_CREATED")
  ) return "good";
  if (
    state.includes("FAIL") ||
    state.includes("ERROR") ||
    state.includes("REJECT") ||
    state.includes("BLOCK") ||
    state.includes("VETO") ||
    state.includes("NO_TRADE")
  ) return "bad";
  return "warm";
}

function journeyMatch(detail: CaseDetail | null, terms: string[]): JourneyRow | null {
  const rows = Array.isArray(detail?.journey) ? detail?.journey ?? [] : [];
  return (
    rows.find((row) => {
      const haystack = `${normalize(row.key)} ${normalize(row.label)}`;
      return terms.some((term) => haystack.includes(term));
    }) ?? null
  );
}

function latestJesseRows(snapshot: LivingSnapshot): Map<string, JsonObject> {
  const scan = object(snapshot.jesse_dislocation.payload?.latest_scan);
  const combined = [...objectRows(scan.top_three), ...objectRows(scan.losers)];
  const output = new Map<string, JsonObject>();
  for (const row of combined) {
    const ticker = text(row.ticker, "").toUpperCase();
    if (!ticker || output.has(ticker)) continue;
    const decline = object(row.decline_analysis);
    const recommendation = normalize(row.recommendation);
    const classification = normalize(decline.classification);
    if (
      recommendation === "BUY" ||
      recommendation === "WATCH" ||
      classification === "POSSIBLE_TEMPORARY_DISLOCATION"
    ) output.set(ticker, row);
  }
  return output;
}

function buildCaseRoster(snapshot: LivingSnapshot): TheaterCase[] {
  const telemetry = object(snapshot.validation.layers.factory_telemetry.payload);
  const promotions = objectRows(telemetry.recent_promotions) as Promotion[];
  const cases = snapshot.factory.payload?.cases ?? [];
  const outcomes = objectRows(
    object(snapshot.validation.layers.outcome_learning.payload).recent_outcomes,
  );
  const outcomeByCaseId = new Map<string, JsonObject>();
  const outcomeByCandidateId = new Map<string, JsonObject>();
  for (const outcome of outcomes) {
    const caseId = text(outcome.case_id, "");
    const candidateId = text(outcome.candidate_id, "");
    if (caseId && !outcomeByCaseId.has(caseId)) outcomeByCaseId.set(caseId, outcome);
    if (candidateId && !outcomeByCandidateId.has(candidateId)) {
      outcomeByCandidateId.set(candidateId, outcome);
    }
  }

  const jesseByTicker = latestJesseRows(snapshot);
  const promotionByCase = new Map(
    promotions
      .map((row) => [text(row.case_id, ""), row] as const)
      .filter(([caseId]) => Boolean(caseId)),
  );
  const overviewByCase = new Map(cases.map((row) => [row.case_id, row]));
  const ids = new Set<string>([
    ...promotionByCase.keys(),
    ...overviewByCase.keys(),
  ]);

  return [...ids]
    .map((caseId) => {
      const promotion = promotionByCase.get(caseId) ?? null;
      const overview = overviewByCase.get(caseId) ?? null;
      const ticker = text(
        promotion?.ticker,
        text(overview?.ticker, "NO TICKER"),
      ).toUpperCase();
      const jesse = jesseByTicker.get(ticker) ?? null;
      const sourceCandidateId = text(promotion?.source_candidate_id, "");
      const learning =
        outcomeByCaseId.get(caseId) ??
        (sourceCandidateId
          ? outcomeByCandidateId.get(sourceCandidateId)
          : undefined) ??
        null;
      const provenance = promotion
        ? jesse
          ? ("BOTH" as const)
          : ("9E RADAR" as const)
        : jesse
          ? ("JESSE DISLOCATION" as const)
          : ("MANUAL / OTHER" as const);
      return {
        caseId,
        ticker,
        topic: text(promotion?.topic, text(overview?.topic, ticker)),
        promotion,
        overview,
        learning,
        jesse,
        provenance,
      };
    })
    .sort((left, right) => {
      const leftTime = new Date(
        text(left.promotion?.promoted_at, text(left.overview?.latest_event_at, "1970-01-01")),
      ).getTime();
      const rightTime = new Date(
        text(right.promotion?.promoted_at, text(right.overview?.latest_event_at, "1970-01-01")),
      ).getTime();
      return rightTime - leftTime;
    })
    .slice(0, 40);
}

function buildStages(theaterCase: TheaterCase, detail: CaseDetail | null): TheaterStage[] {
  const promotion = theaterCase.promotion;
  const agents = promotion?.agents ?? null;
  const agentKeys = Array.isArray(agents?.agent_keys) ? agents?.agent_keys ?? [] : [];
  const agentNames = agentKeys.map((key) => AGENT_NAMES[key] ?? key);
  const research = journeyMatch(detail, ["RESEARCH", "EVIDENCE", "KIMI", "GROK", "GEMINI"]);
  const committeeJourney = journeyMatch(detail, ["COMMITTEE", "COUNCIL"]);
  const riskJourney = journeyMatch(detail, ["RISK"]);
  const paperJourney = journeyMatch(detail, ["PAPER", "AUTHORIZATION", "SIZING"]);
  const learning = theaterCase.learning;
  const monitoring = detail?.monitoring ?? null;
  const paper = detail?.paper_execution ?? null;
  const skepticCompleted = agentKeys.includes("skeptic");
  const agentsCompleted = Number(
    agents?.completed_count ?? theaterCase.overview?.agent_count ?? 0,
  );
  const committeeDisposition = text(
    detail?.committee?.disposition,
    text(object(promotion?.committee).disposition, "WAITING"),
  );
  const riskDecision = text(
    detail?.risk?.decision,
    text(object(promotion?.risk).decision, "WAITING"),
  );
  const paperState = text(
    paper?.execution,
    text(object(promotion?.paper_execution).execution, "WAITING"),
  );
  const marketOutcome = text(
    learning?.market_outcome,
    text(learning?.market_outcome_label, "WARM-UP"),
  );
  const decisionQuality = text(
    learning?.decision_quality,
    text(learning?.decision_quality_label, "WARM-UP"),
  );
  const jesseDecline = object(theaterCase.jesse?.decline_analysis);

  return [
    {
      key: "DISCOVERY",
      label: "Discovery",
      status: promotion ? "COMPLETE" : "CASE EXISTS",
      source: promotion ? "9G / 9E persisted promotion lineage" : "Governed case record",
      sourceId: text(promotion?.source_candidate_id, theaterCase.caseId),
      timestamp: text(promotion?.promoted_at, text(theaterCase.overview?.latest_event_at, "")),
      headline: promotion
        ? `${theaterCase.ticker} was promoted from the persisted 9E opportunity pipeline.`
        : `${theaterCase.ticker} is a governed case whose original promotion is outside the current 9G window.`,
      body: promotion
        ? `Opportunity score ${text(promotion.opportunity_score, "—")} · radar rank ${text(promotion.radar_rank_score, "—")} · priority ${text(promotion.priority, "—")}.`
        : "9N labels missing source provenance instead of reconstructing it.",
      facts: [
        { label: "Signal provenance", value: theaterCase.provenance },
        { label: "Jesse classification", value: text(jesseDecline.classification, "—").replaceAll("_", " ") },
        { label: "Case", value: theaterCase.caseId },
      ],
      rawArtifact: promotion ? object(promotion) : null,
    },
    {
      key: "RESEARCH",
      label: "Research",
      status: research ? text(research.status, "RECORDED") : "WAITING",
      source: "Read-only backend case journey",
      sourceId: text(research?.object_id, "WAITING"),
      timestamp: text(research?.created_at, ""),
      headline: research
        ? "A persisted research/evidence artifact is exposed in this case journey."
        : "No explicit research artifact is exposed by the current case-detail contract.",
      body: research
        ? "The replay uses only the persisted object identity and state. It does not reconstruct missing research text."
        : "WAITING — downstream objects do not authorize 9N to invent the missing research artifact.",
      facts: [
        { label: "Journey key", value: text(research?.key, "WAITING") },
        { label: "Object", value: text(research?.object_id, "WAITING") },
      ],
    },
    {
      key: "AGENTS",
      label: "8 Agents",
      status:
        agentsCompleted >= 8
          ? "8 / 8 COMPLETE"
          : agentsCompleted > 0
            ? `${agentsCompleted} / 8 COMPLETE`
            : "WAITING",
      source: "9G persisted case lineage",
      sourceId: theaterCase.caseId,
      timestamp: text(promotion?.promoted_at, ""),
      headline: agentsCompleted
        ? `${agentsCompleted} specialist completion${agentsCompleted === 1 ? "" : "s"} are persisted in current lineage.`
        : "No persisted specialist completion roster is exposed for this case.",
      body: "RAW AGENT TEXT IS NOT EXPOSED BY THIS READ-ONLY CONTRACT. The theater shows completion identities only and never fabricates a transcript.",
      facts: [
        { label: "Completed", value: `${agentsCompleted} / 8` },
        { label: "Roster", value: agentNames.length ? agentNames.join(" · ") : "WAITING" },
      ],
      rawArtifact: agents ? object(agents) : null,
    },
    {
      key: "SKEPTIC",
      label: "Skeptic",
      status: skepticCompleted ? "COMPLETE" : "WAITING",
      source: skepticCompleted
        ? "9G persisted specialist completion roster"
        : "No persisted Skeptic completion in current lineage",
      sourceId: skepticCompleted ? theaterCase.caseId : "WAITING",
      timestamp: text(promotion?.promoted_at, ""),
      headline: skepticCompleted
        ? "Skeptic / Red Team is present in the persisted completion roster."
        : "The theater will not invent a Skeptic challenge.",
      body: skepticCompleted
        ? "Completion is persisted. Raw Skeptic text is not represented unless a future governed read contract exposes it."
        : "WAITING — no challenge is rendered without a persisted completion source.",
      facts: [
        { label: "Specialist completion", value: skepticCompleted ? "PERSISTED" : "WAITING" },
        { label: "Council escalation", value: detail?.council?.skeptic_escalation_recommended === true ? "RECOMMENDED" : detail?.council?.skeptic_escalation_recommended === false ? "NOT RECOMMENDED" : "NOT EXPOSED" },
      ],
    },
    {
      key: "COMMITTEE",
      label: "Committee",
      status: committeeDisposition,
      source: "Persisted Committee / council case detail",
      sourceId: text(detail?.committee?.decision_id, text(committeeJourney?.object_id, "WAITING")),
      timestamp: text(committeeJourney?.created_at, ""),
      headline: text(
        detail?.committee?.headline,
        committeeDisposition === "WAITING"
          ? "Committee has not produced a persisted decision for this replay."
          : `Committee recorded ${committeeDisposition}.`,
      ),
      body: text(detail?.committee?.summary, "No Committee summary is exposed by the current read-only case detail."),
      facts: [
        { label: "Disposition", value: committeeDisposition },
        { label: "Confidence", value: confidence(detail?.committee?.confidence) },
        { label: "Council packet", value: text(detail?.council?.packet_id, "—") },
      ],
      rawArtifact: detail?.committee ? object(detail.committee) : null,
    },
    {
      key: "RISK",
      label: "Risk",
      status: riskDecision,
      source: "Persisted deterministic Risk authorization",
      sourceId: text(detail?.risk?.risk_authorization_id, text(riskJourney?.object_id, "WAITING")),
      timestamp: text(riskJourney?.created_at, ""),
      headline: riskDecision === "WAITING"
        ? "Risk has not produced a persisted authorization for this replay."
        : `Risk recorded ${riskDecision}.`,
      body: Array.isArray(detail?.risk?.triggered_rules) && detail?.risk?.triggered_rules?.length
        ? `Triggered rules: ${detail.risk.triggered_rules.join(" · ")}`
        : "No triggered Risk rules are exposed in the current case detail.",
      facts: [
        { label: "Decision", value: riskDecision },
        { label: "Authorization", value: text(detail?.risk?.risk_authorization_id, "WAITING") },
      ],
      rawArtifact: detail?.risk ? object(detail.risk) : null,
    },
    {
      key: "PAPER",
      label: "Paper",
      status: paperState,
      source: "Persisted governed paper execution",
      sourceId: text(paper?.execution_id, text(paperJourney?.object_id, "WAITING")),
      timestamp: text(paperJourney?.created_at, ""),
      headline: paperState === "WAITING"
        ? "No governed paper execution is persisted for this replay."
        : `Governed PAPER state recorded: ${paperState}.`,
      body: paperState === "WAITING"
        ? "WAITING — this does not imply a paper order occurred."
        : `Notional ${money(paper?.notional)}. ${text(paper?.reason, "Paper state came from persisted case detail.")}`,
      facts: [
        { label: "Execution", value: paperState },
        { label: "Notional", value: money(paper?.notional) },
        { label: "LIVE execution", value: detail?.live_execution === true ? "TRUE" : "FALSE" },
      ],
      rawArtifact: paper ? object(paper) : null,
    },
    {
      key: "MONITORING",
      label: "Monitoring",
      status: text(monitoring?.status, learning ? "OBSERVED VIA 9J" : "WAITING"),
      source: "Persisted case monitoring snapshot",
      sourceId: theaterCase.caseId,
      timestamp: text(monitoring?.created_at, ""),
      headline: monitoring
        ? `Monitoring state: ${text(monitoring.status, "RECORDED")}.`
        : learning
          ? "9J has an exact-linked outcome, proving later observation exists even though case monitor detail is not exposed."
          : "Monitoring is waiting for a persisted snapshot.",
      body: monitoring
        ? `Latest recorded return ${pct(monitoring.latest_return_pct)}. Thesis flags: ${Array.isArray(monitoring.thesis_flags) && monitoring.thesis_flags.length ? monitoring.thesis_flags.join(" · ") : "none exposed"}.`
        : "No monitoring return or thesis flag is invented.",
      facts: [
        { label: "Status", value: text(monitoring?.status, learning ? "OBSERVED VIA 9J" : "WAITING") },
        { label: "Latest return", value: pct(monitoring?.latest_return_pct) },
      ],
      rawArtifact: monitoring ? object(monitoring) : null,
    },
    {
      key: "OUTCOME",
      label: "Outcome",
      status: learning ? marketOutcome : "WARM-UP",
      source: "9J exact case/candidate-linked outcome memory",
      sourceId: text(learning?.opportunity_id, text(learning?.case_id, "WARM-UP")),
      timestamp: text(learning?.event_at, text(learning?.measured_at, "")),
      headline: learning
        ? `9J recorded market outcome ${marketOutcome}.`
        : "Outcome has not matured into exact-linked 9J memory yet.",
      body: learning
        ? `Longest available horizon ${text(learning.longest_available_horizon, "—")} · forward return ${pct(learning.forward_return_pct)}. Measurement does not rewrite the original decision.`
        : "WARM-UP — no outcome is borrowed from another case with the same ticker.",
      facts: [
        { label: "Market outcome", value: marketOutcome },
        { label: "Forward return", value: pct(learning?.forward_return_pct) },
        { label: "Exact case", value: text(learning?.case_id, "—") },
        { label: "Exact candidate", value: text(learning?.candidate_id, "—") },
      ],
      rawArtifact: learning ? object(learning) : null,
    },
    {
      key: "LEARNING",
      label: "Learning",
      status: learning ? decisionQuality : "WARM-UP",
      source: "9J governed learning memory",
      sourceId: text(learning?.opportunity_id, "WARM-UP"),
      timestamp: text(learning?.event_at, text(learning?.measured_at, "")),
      headline: learning
        ? `Decision-quality label: ${decisionQuality}.`
        : "No exact-linked learning label is available yet.",
      body: learning
        ? "This is measurement memory only. It does not automatically change Committee logic, Risk rules, agent weights or capital authority."
        : "WARM-UP — the factory keeps the stage empty until the persisted learning system has enough evidence.",
      facts: [
        { label: "Decision quality", value: decisionQuality },
        { label: "Human review", value: "REQUIRED FOR GOVERNED CHANGES" },
      ],
      rawArtifact: learning ? object(learning) : null,
    },
  ];
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `IIOS replay request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function ProvenanceBadge({ value }: { value: TheaterCase["provenance"] }) {
  const key = value.toLowerCase().replaceAll(" ", "-").replaceAll("/", "-");
  return <span className={`ict-provenance ict-provenance--${key}`}>{value}</span>;
}

function StageStatus({ value }: { value: string }) {
  return <span className={`ict-status ict-status--${statusTone(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function CaseRail({
  cases,
  selected,
  onSelect,
}: {
  cases: TheaterCase[];
  selected: TheaterCase | null;
  onSelect: (value: TheaterCase) => void;
}) {
  return (
    <aside className="ict-case-rail">
      <div className="ict-heading">
        <span>GOVERNED CASE ARCHIVE</span>
        <strong>{cases.length} replayable</strong>
      </div>
      <div className="ict-case-list">
        {cases.map((row) => (
          <button
            type="button"
            key={row.caseId}
            className={row.caseId === selected?.caseId ? "is-selected" : ""}
            onClick={() => onSelect(row)}
          >
            <div>
              <strong>{row.ticker}</strong>
              <span>{row.topic}</span>
            </div>
            <ProvenanceBadge value={row.provenance} />
            <small>{row.caseId}</small>
          </button>
        ))}
        {!cases.length ? (
          <div className="ict-empty">
            <strong>WAITING FOR GOVERNED CASES</strong>
            <p>No persisted case can be replayed yet.</p>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function StageArtifact({ stage }: { stage: TheaterStage }) {
  const rawEntries = stage.rawArtifact
    ? Object.entries(stage.rawArtifact)
        .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value) || value === null)
        .slice(0, 10)
    : [];
  return (
    <article className="ict-artifact">
      <header>
        <div>
          <span>PERSISTED SOURCE</span>
          <strong>{stage.source}</strong>
        </div>
        <StageStatus value={stage.status} />
      </header>
      <div className="ict-source-id">
        <span>ID · {stage.sourceId}</span>
        <span>{timeLabel(stage.timestamp)}</span>
      </div>
      <h3>{stage.headline}</h3>
      <p className="ict-body">{stage.body}</p>
      <div className="ict-facts">
        {stage.facts.map((fact) => (
          <div key={fact.label}>
            <span>{fact.label}</span>
            <strong>{fact.value}</strong>
          </div>
        ))}
      </div>
      <div className="ict-raw">
        <span>READ-ONLY ARTIFACT SUMMARY</span>
        {rawEntries.length ? (
          <dl>
            {rawEntries.map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>{text(value, "null")}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p>No additional scalar fields are exposed for this stage.</p>
        )}
      </div>
    </article>
  );
}

function CaseEventRail({ events }: { events: StoryEvent[] }) {
  return (
    <div className="ict-event-rail">
      <div className="ict-heading">
        <span>EXACT CASE EVENT TAPE</span>
        <strong>{events.length} in current 9G window</strong>
      </div>
      <div className="ict-event-list">
        {events.map((event, index) => (
          <div key={`${text(event.event_type)}:${text(event.entity_id)}:${text(event.created_at)}:${index}`}>
            <strong>{text(event.event_type, "UNKNOWN").replaceAll("_", " ")}</strong>
            <span>{text(event.entity_id, "NO ENTITY")}</span>
            <em>{timeLabel(event.created_at)}</em>
          </div>
        ))}
        {!events.length ? <p>No exact-case meaningful event is present in the current 9G event window.</p> : null}
      </div>
    </div>
  );
}

export default function InteractiveCaseTheater() {
  const [snapshot, setSnapshot] = useState<LivingSnapshot | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [detailCaseId, setDetailCaseId] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let disposed = false;
    let timer: number | null = null;
    let controller: AbortController | null = null;
    const refresh = async () => {
      controller = new AbortController();
      try {
        const next = await getJson<LivingSnapshot>(telemetryUrl("/living/overview"), controller.signal);
        if (disposed) return;
        setSnapshot(next);
        setSnapshotError(null);
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setSnapshotError(reason instanceof Error ? reason.message : "Living case source unavailable");
      } finally {
        if (!disposed) timer = window.setTimeout(() => void refresh(), 10_000);
      }
    };
    void refresh();
    return () => {
      disposed = true;
      controller?.abort();
      if (timer !== null) window.clearTimeout(timer);
    };
  }, []);

  const cases = useMemo(() => (snapshot ? buildCaseRoster(snapshot) : []), [snapshot]);
  const selected = useMemo(
    () => cases.find((row) => row.caseId === selectedCaseId) ?? cases[0] ?? null,
    [cases, selectedCaseId],
  );

  useEffect(() => {
    setDetail(null);
    setDetailCaseId(null);
    setDetailError(null);
    if (!selected?.caseId) return;
    const controller = new AbortController();
    let disposed = false;
    void getJson<CaseDetail>(
      telemetryUrl(`/living/case/${encodeURIComponent(selected.caseId)}`),
      controller.signal,
    )
      .then((next) => {
        if (disposed) return;
        setDetail(next);
        setDetailCaseId(selected.caseId);
      })
      .catch((reason: unknown) => {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setDetailError(reason instanceof Error ? reason.message : "Case detail unavailable");
      });
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [selected?.caseId]);

  const activeDetail = selected && detailCaseId === selected.caseId ? detail : null;
  const stages = useMemo(
    () => (selected ? buildStages(selected, activeDetail) : []),
    [selected, activeDetail],
  );
  const safeCursor = Math.min(Math.max(cursor, 0), Math.max(0, stages.length - 1));
  const activeStage = stages[safeCursor] ?? null;
  const caseEvents = useMemo(() => {
    if (!snapshot || !selected) return [];
    const telemetry = object(snapshot.validation.layers.factory_telemetry.payload);
    return objectRows(telemetry.recent_meaningful_events)
      .filter((event) => text(event.case_id, "") === selected.caseId) as StoryEvent[];
  }, [snapshot, selected]);

  useEffect(() => {
    if (!playing || !stages.length) return;
    const timer = window.setInterval(() => {
      setCursor((current) => {
        if (current >= stages.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [playing, stages.length]);

  if (!snapshot) {
    return (
      <section className="ict-shell ict-waiting">
        <span>BATCH 9N · INTERACTIVE CASE THEATER</span>
        <h2>{snapshotError ? "CASE SOURCE WARM-UP" : "OPENING THE GOVERNED CASE ARCHIVE"}</h2>
        <p>{snapshotError ?? "No replay can begin until persisted case state is available."}</p>
      </section>
    );
  }

  return (
    <section className="ict-shell">
      <div className="ict-hero">
        <div>
          <span>BATCH 9N · INTERACTIVE CASE THEATER</span>
          <h2>REPLAY THE DECISION. DO NOT REWRITE HISTORY.</h2>
          <p>
            Select a real governed IIOS case and walk from discovery through research, specialist completion, Skeptic, Committee, Risk, paper, monitoring, outcome and learning. Missing artifacts stay WAITING instead of being reconstructed from imagination.
          </p>
        </div>
        <div className="ict-contract">
          <strong>REPLAY CURSOR ONLY · DOES NOT EXECUTE FACTORY</strong>
          <span>READ-ONLY CASE DETAIL</span>
          <span>LIVE EXECUTION FALSE</span>
        </div>
      </div>

      <div className="ict-safety">
        <span>DIRECT LEDGER ACCESS · {snapshot.safety.direct_ledger_access ? "YES" : "NONE"}</span>
        <span>BACKEND · {snapshot.safety.backend_access}</span>
        <span>BACKEND WRITE · {snapshot.safety.backend_write_permission ? "TRUE" : "FALSE"}</span>
        <span>TRADE EXECUTION · {snapshot.safety.trade_execution_permission ? "TRUE" : "FALSE"}</span>
      </div>

      <div className="ict-layout">
        <CaseRail
          cases={cases}
          selected={selected}
          onSelect={(row) => {
            setSelectedCaseId(row.caseId);
            setCursor(0);
            setPlaying(false);
          }}
        />

        <main className="ict-theater">
          {selected ? (
            <>
              <div className="ict-case-hero">
                <div>
                  <span>NOW REPLAYING</span>
                  <h3>{selected.ticker} · {selected.topic}</h3>
                  <small>{selected.caseId}</small>
                </div>
                <div>
                  <ProvenanceBadge value={selected.provenance} />
                  <StageStatus value={detailError ? "DETAIL WARM-UP" : snapshot.factory.availability} />
                </div>
              </div>

              <div className="ict-controls">
                <button type="button" onClick={() => setCursor(0)} disabled={!stages.length}>START</button>
                <button type="button" onClick={() => setCursor((value) => Math.max(0, value - 1))} disabled={safeCursor <= 0}>PREV</button>
                <button type="button" className={playing ? "is-playing" : ""} onClick={() => setPlaying((value) => !value)} disabled={!stages.length}>
                  {playing ? "PAUSE REPLAY" : "PLAY REPLAY"}
                </button>
                <button type="button" onClick={() => setCursor((value) => Math.min(stages.length - 1, value + 1))} disabled={safeCursor >= stages.length - 1}>NEXT</button>
                <span>UI CURSOR {safeCursor + 1} / {stages.length} · NO FACTORY COMMANDS SENT</span>
              </div>

              <div className="ict-stage-rail">
                {stages.map((stage, index) => (
                  <button
                    type="button"
                    key={stage.key}
                    className={`${index === safeCursor ? "is-active" : ""} tone-${statusTone(stage.status)}`}
                    onClick={() => {
                      setCursor(index);
                      setPlaying(false);
                    }}
                  >
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{stage.label}</strong>
                    <em>{stage.status.replaceAll("_", " ")}</em>
                  </button>
                ))}
              </div>

              {activeStage ? <StageArtifact stage={activeStage} /> : null}
              <CaseEventRail events={caseEvents} />

              <div className="ict-lineage-strip">
                {STAGES.map(([key, label], index) => {
                  const stage = stages[index];
                  return (
                    <div key={key} className={index === safeCursor ? "is-active" : ""}>
                      <span>{label}</span>
                      <strong>{stage?.sourceId ?? "WAITING"}</strong>
                    </div>
                  );
                })}
              </div>

              <div className="ict-integrity-note">
                <strong>REPLAY INTEGRITY</strong>
                <p>
                  This theater changes only a browser cursor. It cannot rerun an agent, rerun Committee, change Risk, submit a paper order, alter a 9J label or grant capital authority. 9J outcomes are joined only by exact persisted case/candidate IDs; ticker-only learning joins are prohibited.
                </p>
              </div>
            </>
          ) : (
            <div className="ict-empty">
              <strong>WAITING FOR A REPLAYABLE GOVERNED CASE</strong>
              <p>The theater does not generate demonstration cases.</p>
            </div>
          )}
          {detailError ? <div className="ict-warning">CASE DETAIL WARM-UP · {detailError}</div> : null}
          {snapshotError ? <div className="ict-warning">LATEST OVERVIEW REFRESH WARNING · {snapshotError}</div> : null}
        </main>
      </div>
    </section>
  );
}

import { useEffect, useMemo, useState } from "react";
import "./LivingFactoryExperience.css";

type JsonObject = Record<string, unknown>;

type ValidationLayer = {
  name: string;
  availability: string;
  age_seconds?: number | null;
  lineage_mode?: string;
  payload?: JsonObject | null;
};

type ValidationStack = {
  schema_version: string;
  generated_at: string;
  layers: {
    factory_telemetry: ValidationLayer;
    market_validation: ValidationLayer;
    shadow_strategy: ValidationLayer;
    outcome_learning: ValidationLayer;
  };
};

type DeskRow = {
  key: string;
  name: string;
  room: string;
  focus: string;
  status?: string;
  recent_completions?: number;
};

type CaseRow = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  stage?: string;
  active_room?: string;
  latest_event?: string | null;
  latest_event_at?: string | null;
  agent_count?: number;
  committee?: string;
  risk?: string;
  paper_execution?: string;
  live_execution?: boolean;
};

type FactoryOverview = {
  generated_at?: string;
  data_state?: string;
  factory?: {
    desks?: DeskRow[];
  };
  cases?: CaseRow[];
  safety?: {
    paper_mode?: boolean;
    live_capital_locked?: boolean;
    trade_execution_permission?: boolean;
    live_execution?: boolean;
  };
};

type JesseStatus = {
  latest_scan?: JsonObject | null;
  paper_mode?: boolean;
  trade_execution_permission?: boolean;
  live_execution?: boolean;
};

type BackendLayer<T> = {
  name: string;
  availability: string;
  error_type?: string | null;
  payload?: T | null;
};

type LivingSnapshot = {
  schema_version: string;
  generated_at: string;
  validation: ValidationStack;
  factory: BackendLayer<FactoryOverview>;
  jesse_dislocation: BackendLayer<JesseStatus>;
  safety: {
    preview_only: boolean;
    localhost_only: boolean;
    direct_ledger_access: boolean;
    backend_access: string;
    backend_write_permission: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
};

type CaseDetail = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  journey?: Array<{
    key: string;
    status: string;
    label: string;
    object_id?: string | null;
  }>;
  committee?: {
    disposition: string;
    confidence?: number | null;
    headline?: string;
    summary?: string;
  };
  risk?: {
    decision: string;
    triggered_rules?: string[];
  };
  monitoring?: {
    status: string;
    created_at?: string | null;
    latest_return_pct?: number | null;
    thesis_flags?: string[];
  };
  paper_execution?: {
    execution: string;
    reason?: string | null;
  };
  trade_execution_permission?: boolean;
  live_execution?: boolean;
};

type Provenance =
  | "JESSE DISLOCATION"
  | "9E RADAR"
  | "BOTH"
  | "MANUAL / OTHER";

type StageState = {
  label: string;
  state: string;
};

type Opportunity = {
  key: string;
  ticker: string;
  topic: string;
  caseId: string | null;
  sourceCandidateId: string | null;
  provenance: Provenance;
  radar: JsonObject | null;
  jesse: JsonObject | null;
  caseRow: CaseRow | null;
  learning: JsonObject | null;
  stageIndex: number;
  stageLabel: string;
  stageStates: StageState[];
};

const STAGES = [
  "Market",
  "9E Radar",
  "Research",
  "8 Agents",
  "Committee",
  "Risk",
  "Paper",
  "Monitoring",
  "Learning",
] as const;

const AGENT_ROSTER: DeskRow[] = [
  {
    key: "policy",
    name: "Policy Analyst",
    room: "Policy Floor",
    focus: "Policy transmission, regulation, tariffs and government action.",
  },
  {
    key: "macro",
    name: "Macro & Rates Analyst",
    room: "Macro Desk",
    focus: "Rates, inflation, growth, liquidity and market regime.",
  },
  {
    key: "fundamentals",
    name: "Fundamentals Analyst",
    room: "Fundamentals Lab",
    focus: "Earnings, balance sheet, valuation and business durability.",
  },
  {
    key: "market_structure",
    name: "Market Structure Analyst",
    room: "Tape & Positioning",
    focus: "Price action, liquidity, volatility, flows and crowding.",
  },
  {
    key: "commodities",
    name: "Commodities & Supply Chain Analyst",
    room: "Physical Markets",
    focus: "Energy, agriculture, metals, freight and supply constraints.",
  },
  {
    key: "geo_weather",
    name: "Geopolitics & Weather Analyst",
    room: "Global Events Room",
    focus: "War, sanctions, chokepoints, weather and event shocks.",
  },
  {
    key: "skeptic",
    name: "Skeptic / Red Team",
    room: "Red Team",
    focus: "False causality, missing evidence, base rates and falsifiers.",
  },
  {
    key: "portfolio",
    name: "Portfolio Context Analyst",
    room: "Portfolio Control",
    focus: "Concentration, correlation, drawdown and portfolio fit.",
  },
];

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
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function pct(value: unknown, decimals = 1): string {
  const numeric = numberValue(value);
  return numeric === null ? "—" : `${numeric.toFixed(decimals)}%`;
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

function tickerOf(value: JsonObject): string {
  return text(value.ticker, "").trim().toUpperCase();
}

function timeLabel(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "WAITING";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "WAITING";
  return parsed.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function ageLabel(value?: number | null): string {
  if (value === undefined || value === null) return "WARM-UP";
  if (value < 60) return `${value}s`;
  if (value < 3600) return `${Math.floor(value / 60)}m`;
  return `${Math.floor(value / 3600)}h`;
}

function stateTone(value: string): string {
  const normalized = value.toUpperCase();
  if (
    normalized.includes("COMPLETE") ||
    normalized.includes("AVAILABLE") ||
    normalized.includes("ACTIVE") ||
    normalized.includes("HEALTHY") ||
    normalized.includes("READY") ||
    normalized.includes("ON_CADENCE") ||
    normalized.includes("OBSERVED")
  ) {
    return "good";
  }
  if (
    normalized.includes("WAIT") ||
    normalized.includes("WARM") ||
    normalized.includes("PENDING") ||
    normalized.includes("IDLE") ||
    normalized.includes("NO_") ||
    normalized.includes("UNKNOWN")
  ) {
    return "warm";
  }
  if (
    normalized.includes("ERROR") ||
    normalized.includes("OFFLINE") ||
    normalized.includes("FAIL") ||
    normalized.includes("STALE") ||
    normalized.includes("REJECT") ||
    normalized.includes("VETO")
  ) {
    return "bad";
  }
  return "neutral";
}

function Status({ value }: { value: string }) {
  return (
    <span className={`lfx-status lfx-status--${stateTone(value)}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}

function ProvenanceBadge({ value }: { value: Provenance }) {
  const key = value.toLowerCase().replaceAll(" ", "-").replaceAll("/", "-");
  return <span className={`lfx-provenance lfx-provenance--${key}`}>{value}</span>;
}

async function sameOriginJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `IIOS sidecar request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function isPersistedDecision(value: unknown): boolean {
  const normalized = text(value, "").trim().toUpperCase();
  return Boolean(normalized) && ![
    "UNKNOWN",
    "WAITING",
    "PENDING",
    "NOT_STARTED",
    "NO_STATE",
    "NO_SNAPSHOT",
    "NONE",
  ].includes(normalized);
}

function isPersistedPaper(value: unknown): boolean {
  const normalized = text(value, "").trim().toUpperCase();
  return Boolean(normalized) && ![
    "UNKNOWN",
    "WAITING",
    "PENDING",
    "NOT_STARTED",
    "NOT_EXECUTED",
    "NO_ORDER",
    "NONE",
  ].includes(normalized);
}

function jesseSignalRows(status: JesseStatus | null): JsonObject[] {
  const scan = object(status?.latest_scan);
  const combined = [...objectRows(scan.top_three), ...objectRows(scan.losers)];
  const selected = new Map<string, JsonObject>();
  for (const row of combined) {
    const ticker = tickerOf(row);
    if (!ticker) continue;
    const decline = object(row.decline_analysis);
    const recommendation = text(row.recommendation, "NO_TRADE").toUpperCase();
    const classification = text(decline.classification, "UNRESOLVED").toUpperCase();
    const qualifies =
      recommendation === "BUY" ||
      recommendation === "WATCH" ||
      classification === "POSSIBLE_TEMPORARY_DISLOCATION";
    if (qualifies && !selected.has(ticker)) selected.set(ticker, row);
  }
  return [...selected.values()].slice(0, 12);
}

function buildStageStates(
  radar: JsonObject | null,
  caseRow: CaseRow | null,
  learning: JsonObject | null,
): StageState[] {
  const agents = object(radar?.agents);
  const committee = object(radar?.committee);
  const risk = object(radar?.risk);
  const paper = object(radar?.paper_execution);
  const completedAgents = Number(
    agents.completed_count ?? caseRow?.agent_count ?? 0,
  );
  const committeeValue = text(
    committee.disposition,
    caseRow?.committee ?? "UNKNOWN",
  );
  const riskValue = text(risk.decision, caseRow?.risk ?? "UNKNOWN");
  const paperValue = text(
    paper.execution,
    caseRow?.paper_execution ?? "NOT_EXECUTED",
  );
  const stageText = `${caseRow?.stage ?? ""} ${caseRow?.active_room ?? ""} ${
    caseRow?.latest_event ?? ""
  }`.toUpperCase();
  const monitoringObserved =
    stageText.includes("MONITOR") || stageText.includes("PORTFOLIO");
  const committeeObserved =
    Boolean(committee.decision_id) || isPersistedDecision(committeeValue);
  const riskObserved =
    Boolean(risk.risk_authorization_id) || isPersistedDecision(riskValue);
  const paperObserved =
    Boolean(paper.execution_id) || isPersistedPaper(paperValue);

  return [
    { label: "Market", state: "COMPLETE" },
    { label: "9E Radar", state: radar ? "COMPLETE" : "WAITING" },
    {
      label: "Research",
      state: radar || caseRow ? "OBSERVED" : "WAITING",
    },
    {
      label: "8 Agents",
      state:
        completedAgents >= 8
          ? "8 / 8 COMPLETE"
          : completedAgents > 0
            ? `${completedAgents} / 8 COMPLETE`
            : "WAITING",
    },
    {
      label: "Committee",
      state: committeeObserved ? committeeValue : "WAITING",
    },
    {
      label: "Risk",
      state: riskObserved ? riskValue : "WAITING",
    },
    {
      label: "Paper",
      state: paperObserved ? paperValue : "WAITING",
    },
    {
      label: "Monitoring",
      state: monitoringObserved
        ? "OBSERVED"
        : learning
          ? "OBSERVED VIA 9J"
          : "WAITING",
    },
    {
      label: "Learning",
      state: learning
        ? text(
            learning.decision_quality,
            text(learning.market_outcome, "RECORDED"),
          )
        : "WARM-UP",
    },
  ];
}

function mostAdvancedStage(states: StageState[]): number {
  for (let index = states.length - 1; index >= 0; index -= 1) {
    const state = states[index].state.toUpperCase();
    if (!state.includes("WAIT") && !state.includes("WARM")) return index;
  }
  return 0;
}

function buildOpportunities(snapshot: LivingSnapshot): Opportunity[] {
  const telemetry = object(snapshot.validation.layers.factory_telemetry.payload);
  const promotions = objectRows(telemetry.recent_promotions);
  const outcomePayload = object(
    snapshot.validation.layers.outcome_learning.payload,
  );
  const outcomes = objectRows(outcomePayload.recent_outcomes);
  const learningByCaseId = new Map<string, JsonObject>();
  const learningByCandidateId = new Map<string, JsonObject>();

  for (const outcome of outcomes) {
    const caseId = text(outcome.case_id, "").trim();
    const candidateId = text(outcome.candidate_id, "").trim();
    if (caseId && !learningByCaseId.has(caseId)) {
      learningByCaseId.set(caseId, outcome);
    }
    if (candidateId && !learningByCandidateId.has(candidateId)) {
      learningByCandidateId.set(candidateId, outcome);
    }
  }

  const overview = snapshot.factory.payload ?? null;
  const cases = overview?.cases ?? [];
  const caseById = new Map(cases.map((row) => [row.case_id, row]));
  const jesseRows = jesseSignalRows(snapshot.jesse_dislocation.payload ?? null);
  const jesseByTicker = new Map(jesseRows.map((row) => [tickerOf(row), row]));
  const seenCaseIds = new Set<string>();
  const seenTickers = new Set<string>();
  const output: Opportunity[] = [];

  const append = (
    key: string,
    ticker: string,
    topic: string,
    caseId: string | null,
    radar: JsonObject | null,
    jesse: JsonObject | null,
    caseRow: CaseRow | null,
  ) => {
    const sourceCandidateId = text(radar?.source_candidate_id, "").trim() || null;
    const learning =
      (caseId ? learningByCaseId.get(caseId) : undefined) ??
      (sourceCandidateId
        ? learningByCandidateId.get(sourceCandidateId)
        : undefined) ??
      null;
    const provenance: Provenance = radar
      ? jesse
        ? "BOTH"
        : "9E RADAR"
      : jesse
        ? "JESSE DISLOCATION"
        : "MANUAL / OTHER";
    const stageStates = buildStageStates(radar, caseRow, learning);
    const stageIndex = mostAdvancedStage(stageStates);
    output.push({
      key,
      ticker: ticker || "NO TICKER",
      topic: topic || ticker || key,
      caseId,
      sourceCandidateId,
      provenance,
      radar,
      jesse,
      caseRow,
      learning,
      stageIndex,
      stageLabel: STAGES[stageIndex],
      stageStates,
    });
  };

  for (const promotion of promotions) {
    const caseId = text(promotion.case_id, "").trim() || null;
    const caseRow = caseId ? caseById.get(caseId) ?? null : null;
    const ticker =
      tickerOf(promotion) || text(caseRow?.ticker, "").trim().toUpperCase();
    append(
      caseId ?? `radar:${ticker}:${text(promotion.source_candidate_id, "unknown")}`,
      ticker,
      text(promotion.topic, caseRow?.topic ?? ticker),
      caseId,
      promotion,
      jesseByTicker.get(ticker) ?? null,
      caseRow,
    );
    if (caseId) seenCaseIds.add(caseId);
    if (ticker) seenTickers.add(ticker);
  }

  for (const caseRow of cases) {
    if (seenCaseIds.has(caseRow.case_id)) continue;
    const ticker = text(caseRow.ticker, "").trim().toUpperCase();
    append(
      caseRow.case_id,
      ticker,
      caseRow.topic ?? ticker || caseRow.case_id,
      caseRow.case_id,
      null,
      jesseByTicker.get(ticker) ?? null,
      caseRow,
    );
    seenCaseIds.add(caseRow.case_id);
    if (ticker) seenTickers.add(ticker);
  }

  for (const jesse of jesseRows) {
    const ticker = tickerOf(jesse);
    if (!ticker || seenTickers.has(ticker)) continue;
    append(
      `jesse:${ticker}`,
      ticker,
      text(jesse.company, ticker),
      null,
      null,
      jesse,
      null,
    );
  }

  return output
    .sort((left, right) => {
      if (right.stageIndex !== left.stageIndex) {
        return right.stageIndex - left.stageIndex;
      }
      return left.ticker.localeCompare(right.ticker);
    })
    .slice(0, 24);
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <div className="lfx-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function IntelligenceDock({ snapshot }: { snapshot: LivingSnapshot }) {
  const telemetryLayer = snapshot.validation.layers.factory_telemetry;
  const telemetry = object(telemetryLayer.payload);
  const validationLayer = snapshot.validation.layers.market_validation;
  const validation = object(validationLayer.payload);
  const validationMetrics = object(validation.metrics);
  const shadowLayer = snapshot.validation.layers.shadow_strategy;
  const shadow = object(shadowLayer.payload);
  const outcomeLayer = snapshot.validation.layers.outcome_learning;
  const outcome = object(outcomeLayer.payload);
  const reviewCount =
    numberValue(outcome.judgment_bank_review_queue_count) ??
    objectRows(outcome.judgment_bank_review_queue).length;
  const cards = [
    {
      code: "9G",
      title: "Factory Telemetry",
      state: telemetryLayer.availability,
      age: ageLabel(telemetryLayer.age_seconds),
      metric: `${objectRows(telemetry.recent_meaningful_events).length} events`,
      detail: text(object(telemetry.health).state, "WARM-UP"),
    },
    {
      code: "9H",
      title: "Independent Grading",
      state: validationLayer.availability,
      age: ageLabel(validationLayer.age_seconds),
      metric: `Detect ${pct(validationMetrics.detection_rate_pct)}`,
      detail: `Miss ${pct(validationMetrics.opportunity_miss_rate_pct)}`,
    },
    {
      code: "9I",
      title: "Shadow Experiments",
      state: shadowLayer.availability,
      age: ageLabel(shadowLayer.age_seconds),
      metric: `${text(shadow.complete_session_count, "0")} sessions`,
      detail: `${objectRows(shadow.recommendations).length} advisory recs`,
    },
    {
      code: "9J",
      title: "Outcome Learning",
      state: outcomeLayer.availability,
      age: ageLabel(outcomeLayer.age_seconds),
      metric: `${text(outcome.outcome_count, "0")} outcomes`,
      detail: `${reviewCount} review inputs · ${outcomeLayer.lineage_mode ?? "WAITING"}`,
    },
  ];

  return (
    <section className="lfx-dock">
      {cards.map((card) => (
        <article key={card.code}>
          <header>
            <span>{card.code}</span>
            <Status value={card.state} />
          </header>
          <h4>{card.title}</h4>
          <strong>{card.metric}</strong>
          <footer>
            <span>{card.detail}</span>
            <em>{card.age}</em>
          </footer>
        </article>
      ))}
    </section>
  );
}

function FactoryConveyor({
  opportunities,
  selectedKey,
  onSelect,
}: {
  opportunities: Opportunity[];
  selectedKey: string | null;
  onSelect: (opportunity: Opportunity) => void;
}) {
  const stageCounts = STAGES.map(
    (_, index) => opportunities.filter((item) => item.stageIndex === index).length,
  );

  return (
    <section className="lfx-conveyor-panel">
      <div className="lfx-section-heading">
        <div>
          <span>EVENT-DRIVEN FACTORY CONVEYOR</span>
          <h3>Cases only move when persisted IIOS state advances.</h3>
        </div>
        <div className="lfx-live-rule">NO SYNTHETIC MOVEMENT</div>
      </div>
      <div className="lfx-stage-rail">
        {STAGES.map((stage, index) => (
          <div className="lfx-stage" key={stage}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{stage}</strong>
            <em>{stageCounts[index]} here</em>
          </div>
        ))}
      </div>
      <div className="lfx-opportunity-list">
        {opportunities.map((item) => {
          const progress = (item.stageIndex / (STAGES.length - 1)) * 100;
          const radar = item.radar ?? {};
          const jesse = item.jesse ?? {};
          const decline = object(jesse.decline_analysis);
          return (
            <button
              className={`lfx-opportunity ${
                item.key === selectedKey ? "is-selected" : ""
              }`}
              key={item.key}
              onClick={() => onSelect(item)}
              type="button"
            >
              <div className="lfx-opportunity-head">
                <div>
                  <strong>{item.ticker}</strong>
                  <span>{item.topic}</span>
                </div>
                <ProvenanceBadge value={item.provenance} />
              </div>
              <div className="lfx-progress-track">
                <div
                  className="lfx-progress-fill"
                  style={{ width: `${progress}%` }}
                />
                {STAGES.map((stage, index) => (
                  <span
                    className={`lfx-progress-node ${
                      index <= item.stageIndex ? "is-reached" : ""
                    }`}
                    key={stage}
                    style={{ left: `${(index / (STAGES.length - 1)) * 100}%` }}
                  />
                ))}
              </div>
              <div className="lfx-opportunity-meta">
                <span>NOW · {item.stageLabel.toUpperCase()}</span>
                <span>CASE · {item.caseId ?? "NOT PROMOTED"}</span>
                <span>
                  SCORE ·{" "}
                  {text(
                    radar.opportunity_score,
                    text(jesse.financial_strength_score, "—"),
                  )}
                </span>
                <span>
                  JESSE ·{" "}
                  {text(
                    decline.classification,
                    item.jesse ? text(jesse.recommendation, "OBSERVED") : "—",
                  )}
                </span>
              </div>
            </button>
          );
        })}
        {!opportunities.length ? (
          <div className="lfx-empty">
            <strong>WAITING FOR PERSISTED OPPORTUNITIES</strong>
            <p>
              No 9E promotion, governed factory case, or qualifying persisted
              Jesse dislocation signal is available to render.
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function CharacterFloor({
  snapshot,
  selected,
}: {
  snapshot: LivingSnapshot;
  selected: Opportunity | null;
}) {
  const backendDesks = snapshot.factory.payload?.factory?.desks ?? [];
  const deskByKey = new Map(backendDesks.map((desk) => [desk.key, desk]));
  const desks = AGENT_ROSTER.map((base) => ({
    ...base,
    ...(deskByKey.get(base.key) ?? {}),
  }));
  const telemetry = object(snapshot.validation.layers.factory_telemetry.payload);
  const latestEvent = objectRows(telemetry.recent_meaningful_events)[0] ?? null;
  const latestPayload = object(latestEvent?.payload);
  const selectedAgentKeys = new Set(
    Array.isArray(object(selected?.radar?.agents).agent_keys)
      ? (object(selected?.radar?.agents).agent_keys as unknown[]).map(String)
      : [],
  );

  return (
    <section className="lfx-character-floor">
      <div className="lfx-max-card">
        <div className="lfx-max-avatar" aria-hidden="true">
          <span>MAX</span>
          <strong>M</strong>
        </div>
        <div className="lfx-character-copy">
          <span>FACTORY FOREMAN · PERSISTENT CHARACTER</span>
          <h3>MAX</h3>
          {latestEvent ? (
            <p>
              Latest persisted event:{" "}
              <strong>
                {text(latestEvent.event_type, "UNKNOWN EVENT").replaceAll(
                  "_",
                  " ",
                )}
              </strong>
              {text(latestPayload.ticker, "")
                ? ` · ${text(latestPayload.ticker, "")}`
                : ""}
              {text(latestEvent.case_id, "")
                ? ` · ${text(latestEvent.case_id, "")}`
                : ""}
              . Recorded {timeLabel(latestEvent.created_at)}.
            </p>
          ) : (
            <p>
              WAITING — no persisted 9G factory event is available in the
              current telemetry window.
            </p>
          )}
          <footer>
            No trading activity, movement, or dialogue is inferred beyond
            persisted state.
          </footer>
        </div>
      </div>
      <div className="lfx-agent-grid">
        {desks.map((desk, index) => {
          const selectedCompletion = selectedAgentKeys.has(desk.key);
          const recentCompletions = desk.recent_completions ?? 0;
          const active = selectedCompletion || recentCompletions > 0;
          const monogram = desk.name
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0]?.toUpperCase())
            .join("");
          return (
            <article
              className={`lfx-agent-card ${active ? "is-active" : ""}`}
              key={desk.key}
            >
              <header>
                <div className="lfx-agent-avatar">
                  {monogram || String(index + 1)}
                </div>
                <Status value={active ? "ACTIVE" : "WAITING"} />
              </header>
              <span>{desk.room}</span>
              <h4>{desk.name}</h4>
              <p>
                {selectedCompletion && selected
                  ? `Persisted on ${selected.ticker} lineage.`
                  : recentCompletions > 0
                    ? `${recentCompletions} persisted completion(s) in the backend activity window.`
                    : "WAITING — no persisted completion in the current activity window."}
              </p>
              <footer>{desk.focus}</footer>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function JesseSourceRoom({ snapshot }: { snapshot: LivingSnapshot }) {
  const status = snapshot.jesse_dislocation.payload ?? null;
  const scan = object(status?.latest_scan);
  const signals = jesseSignalRows(status);

  return (
    <section className="lfx-jesse-room">
      <div className="lfx-section-heading">
        <div>
          <span>GOVERNED SIGNAL SOURCE</span>
          <h3>Jesse Rebound / Dislocation Logic</h3>
        </div>
        <Status value={snapshot.jesse_dislocation.availability} />
      </div>
      <div className="lfx-jesse-grid">
        <article className="lfx-logic-card">
          <strong>Deterministic rebound heuristic</strong>
          <p>
            Day losers → financial strength → structural vs temporary decline →
            deterministic next-day +5% rebound estimate → BUY / WATCH /
            NO_TRADE.
          </p>
          <div className="lfx-formula">
            <span>Base 10%</span>
            <span>+0.3% per strength point above 40</span>
            <span>+5 pts at ≤ −5% decline</span>
            <span>+3 pts at ≤ −10% decline</span>
            <span>+10 pts temporary dislocation</span>
            <span>−20 pts structural risk</span>
            <span>Clamp 3%–65%</span>
          </div>
          <footer>
            BUY: strength ≥75 + estimate ≥30% + non-structural · WATCH:
            strength ≥60 + non-structural · probability calibrated: FALSE
          </footer>
        </article>
        <article className="lfx-scan-card">
          <header>
            <div>
              <span>LATEST PERSISTED SCAN</span>
              <strong>{text(scan.dislocation_scan_id, "WAITING")}</strong>
            </div>
            <em>{timeLabel(scan.created_at)}</em>
          </header>
          <div className="lfx-signal-list">
            {signals.slice(0, 8).map((row) => {
              const decline = object(row.decline_analysis);
              return (
                <div key={tickerOf(row)}>
                  <strong>{tickerOf(row)}</strong>
                  <span>{text(row.recommendation, "—")}</span>
                  <span>strength {text(row.financial_strength_score, "—")}</span>
                  <em>
                    {text(
                      decline.classification,
                      "UNRESOLVED",
                    ).replaceAll("_", " ")}
                  </em>
                </div>
              );
            })}
            {!signals.length ? (
              <p>
                WARM-UP — no qualifying persisted Jesse dislocation rows are
                available.
              </p>
            ) : null}
          </div>
        </article>
      </div>
      <div className="lfx-governance-line">
        <span>TRADE SIGNAL FALSE</span>
        <span>PAPER ORDER PERMISSION FALSE</span>
        <span>LIVE EXECUTION FALSE</span>
        <span>BOTH = persisted ticker overlap, not inferred causality</span>
      </div>
    </section>
  );
}

function LineageInspector({
  opportunity,
  detail,
  loading,
  error,
}: {
  opportunity: Opportunity | null;
  detail: CaseDetail | null;
  loading: boolean;
  error: string | null;
}) {
  if (!opportunity) {
    return (
      <section className="lfx-lineage-panel lfx-empty">
        <strong>SELECT AN OPPORTUNITY</strong>
        <p>
          Click a ticker/case card to open its persisted source-to-learning
          lineage.
        </p>
      </section>
    );
  }

  const radar = opportunity.radar ?? {};
  const agents = object(radar.agents);
  const committee = object(radar.committee);
  const risk = object(radar.risk);
  const paper = object(radar.paper_execution);
  const jesse = opportunity.jesse ?? {};
  const decline = object(jesse.decline_analysis);
  const learning = opportunity.learning;
  const journey = detail?.journey ?? [];

  return (
    <section className="lfx-lineage-panel">
      <div className="lfx-lineage-hero">
        <div>
          <span>SIGNAL → DECISION LINEAGE</span>
          <h3>
            {opportunity.ticker} · {opportunity.topic}
          </h3>
          <em>
            {opportunity.caseId ?? "JESSE SIGNAL · NOT PROMOTED TO CASE"}
          </em>
        </div>
        <div>
          <ProvenanceBadge value={opportunity.provenance} />
          <Status value={loading ? "LOADING CASE" : opportunity.stageLabel} />
        </div>
      </div>
      {error ? (
        <div className="lfx-inline-warning">CASE DETAIL WARM-UP · {error}</div>
      ) : null}
      <div className="lfx-lineage-grid">
        <article>
          <span>SIGNAL PROVENANCE</span>
          <strong>{opportunity.provenance}</strong>
          <p>
            Radar candidate: {opportunity.sourceCandidateId ?? "—"}
            <br />
            Jesse ticker: {opportunity.jesse ? opportunity.ticker : "—"}
            <br />
            Jesse classification:{" "}
            {text(decline.classification, "—").replaceAll("_", " ")}
          </p>
        </article>
        <article>
          <span>9E RADAR / RESEARCH</span>
          <strong>{text(radar.opportunity_score, "—")}</strong>
          <p>
            Radar rank: {text(radar.radar_rank_score, "—")} · Priority{" "}
            {text(radar.priority, "—")}
            <br />
            Promoted: {timeLabel(radar.promoted_at)}
          </p>
        </article>
        <article>
          <span>EIGHT AGENTS</span>
          <strong>
            {text(
              agents.completed_count,
              String(opportunity.caseRow?.agent_count ?? 0),
            )}{" "}
            / 8
          </strong>
          <p>
            {Array.isArray(agents.agent_keys) && agents.agent_keys.length
              ? agents.agent_keys.map(String).join(" · ")
              : "WAITING — no persisted agent keys in 9G lineage."}
          </p>
        </article>
        <article>
          <span>COMMITTEE</span>
          <strong>
            {text(
              committee.disposition,
              opportunity.caseRow?.committee ?? "WAITING",
            )}
          </strong>
          <p>
            ID {text(committee.decision_id, "—")} · confidence{" "}
            {confidence(committee.confidence)}
          </p>
        </article>
        <article>
          <span>RISK</span>
          <strong>
            {text(risk.decision, opportunity.caseRow?.risk ?? "WAITING")}
          </strong>
          <p>ID {text(risk.risk_authorization_id, "—")}</p>
        </article>
        <article>
          <span>PAPER</span>
          <strong>
            {text(
              paper.execution,
              opportunity.caseRow?.paper_execution ?? "WAITING",
            )}
          </strong>
          <p>
            ID {text(paper.execution_id, "—")} · notional{" "}
            {text(paper.notional, "—")}
          </p>
        </article>
        <article>
          <span>MONITORING</span>
          <strong>
            {detail?.monitoring?.status ??
              (learning ? "OBSERVED VIA 9J" : "WARM-UP")}
          </strong>
          <p>
            {detail?.monitoring
              ? `Snapshot ${timeLabel(
                  detail.monitoring.created_at,
                )} · return ${pct(detail.monitoring.latest_return_pct)}`
              : "Open a promoted case to resolve its backend monitoring object."}
          </p>
        </article>
        <article>
          <span>9J EXACT LINEAGE</span>
          <strong>
            {learning
              ? text(
                  learning.decision_quality,
                  text(learning.market_outcome, "RECORDED"),
                )
              : "WARM-UP"}
          </strong>
          <p>
            {learning
              ? `Case ${text(learning.case_id, "—")} · candidate ${text(
                  learning.candidate_id,
                  "—",
                )} · opportunity ${text(
                  learning.opportunity_id,
                  "—",
                )} · outcome ${text(
                  learning.market_outcome,
                  "—",
                )} · return ${pct(learning.forward_return_pct)}`
              : "No persisted 9J outcome matched this exact case or source candidate."}
          </p>
        </article>
      </div>
      <div className="lfx-stage-detail">
        {opportunity.stageStates.map((stage, index) => (
          <div
            key={stage.label}
            className={index <= opportunity.stageIndex ? "is-reached" : ""}
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{stage.label}</strong>
            <em>{stage.state.replaceAll("_", " ")}</em>
          </div>
        ))}
      </div>
      {detail ? (
        <div className="lfx-case-detail-strip">
          <div>
            <span>BACKEND CASE JOURNEY</span>
            <strong>
              {journey.filter((row) => row.status === "COMPLETE").length}{" "}
              persisted objects complete
            </strong>
          </div>
          <div>
            <span>COMMITTEE</span>
            <strong>
              {detail.committee?.disposition ?? "UNKNOWN"} ·{" "}
              {confidence(detail.committee?.confidence)}
            </strong>
          </div>
          <div>
            <span>RISK</span>
            <strong>{detail.risk?.decision ?? "UNKNOWN"}</strong>
          </div>
          <div>
            <span>LIVE EXECUTION</span>
            <strong>{detail.live_execution ? "TRUE" : "FALSE"}</strong>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function LivingFactoryExperience() {
  const [snapshot, setSnapshot] = useState<LivingSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await sameOriginJson<LivingSnapshot>(
          "/living/overview",
          controller.signal,
        );
        if (disposed) return;
        setSnapshot(next);
        setError(null);
      } catch (reason) {
        if (
          disposed ||
          (reason instanceof DOMException && reason.name === "AbortError")
        ) {
          return;
        }
        setError(
          reason instanceof Error
            ? reason.message
            : "Living factory sidecar unavailable",
        );
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

  const opportunities = useMemo(
    () => (snapshot ? buildOpportunities(snapshot) : []),
    [snapshot],
  );
  const selected = useMemo(
    () =>
      opportunities.find((item) => item.key === selectedKey) ??
      opportunities[0] ??
      null,
    [opportunities, selectedKey],
  );

  useEffect(() => {
    setDetail(null);
    setDetailError(null);
    if (!selected?.caseId) {
      setDetailLoading(false);
      return;
    }
    let disposed = false;
    const controller = new AbortController();
    setDetailLoading(true);
    void sameOriginJson<CaseDetail>(
      `/living/case/${encodeURIComponent(selected.caseId)}`,
      controller.signal,
    )
      .then((next) => {
        if (disposed) return;
        setDetail(next);
        setDetailLoading(false);
      })
      .catch((reason: unknown) => {
        if (
          disposed ||
          (reason instanceof DOMException && reason.name === "AbortError")
        ) {
          return;
        }
        setDetailLoading(false);
        setDetailError(
          reason instanceof Error ? reason.message : "Case detail unavailable",
        );
      });
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [selected?.caseId]);

  if (!snapshot) {
    return (
      <section className="lfx-shell">
        <div className="lfx-loading">
          <span>BATCH 9L · LIVING FACTORY + SIGNAL PROVENANCE</span>
          <h2>
            {error
              ? "SIDECAR WARM-UP"
              : "CONNECTING TO PERSISTED FACTORY STATE"}
          </h2>
          <p>
            {error ??
              "Opening 9G/9H/9I/9J plus read-only backend lineage…"}
          </p>
        </div>
      </section>
    );
  }

  const telemetry = object(snapshot.validation.layers.factory_telemetry.payload);
  const radar = object(telemetry.radar);
  const fund = object(telemetry.paper_fund);
  const overviewCases = snapshot.factory.payload?.cases ?? [];

  return (
    <section className="lfx-shell">
      <div className="lfx-hero">
        <div>
          <span>BATCH 9L · LIVING FACTORY EXPERIENCE + SIGNAL PROVENANCE</span>
          <h2>THE INVESTMENT FACTORY IS NOW A TRACEABLE FLOOR</h2>
          <p>
            MAX, eight specialist characters, real case movement, Jesse + 9E
            signal provenance, and 9G/9H/9I/9J intelligence — driven only by
            persisted IIOS state.
          </p>
        </div>
        <div className="lfx-hero-safety">
          <Status value={snapshot.factory.availability} />
          <strong>
            LIVE EXECUTION {snapshot.safety.live_execution ? "TRUE" : "FALSE"}
          </strong>
          <span>BACKEND 8002 · READ-ONLY GETS</span>
        </div>
      </div>

      <div className="lfx-safety-rail">
        <span>
          DIRECT LEDGER ACCESS ·{" "}
          {snapshot.safety.direct_ledger_access ? "YES" : "NONE"}
        </span>
        <span>
          BACKEND WRITE PERMISSION ·{" "}
          {snapshot.safety.backend_write_permission ? "YES" : "NONE"}
        </span>
        <span>
          TRADE EXECUTION PERMISSION ·{" "}
          {snapshot.safety.trade_execution_permission ? "TRUE" : "FALSE"}
        </span>
        <span>NO FABRICATED EVENTS</span>
      </div>

      <div className="lfx-headline-metrics">
        <Metric
          label="Market universe"
          value={text(radar.governed_universe_count, "0")}
          detail="persisted 9G"
        />
        <Metric
          label="9E radar hits"
          value={text(radar.screener_hit_count, "0")}
        />
        <Metric
          label="Visible opportunities"
          value={opportunities.length}
          detail="persisted sources only"
        />
        <Metric label="Governed cases" value={overviewCases.length} />
        <Metric label="Paper NAV" value={money(fund.nav)} />
        <Metric
          label="Paper positions"
          value={text(fund.position_count, "0")}
        />
      </div>

      <div className="lfx-provenance-legend">
        <strong>SIGNAL PROVENANCE</strong>
        <ProvenanceBadge value="JESSE DISLOCATION" />
        <ProvenanceBadge value="9E RADAR" />
        <ProvenanceBadge value="BOTH" />
        <ProvenanceBadge value="MANUAL / OTHER" />
        <span>
          BOTH means the ticker is independently present in persisted Jesse and
          9E records; it does not claim one caused the other.
        </span>
      </div>

      <IntelligenceDock snapshot={snapshot} />
      <FactoryConveyor
        opportunities={opportunities}
        selectedKey={selected?.key ?? null}
        onSelect={(opportunity) => setSelectedKey(opportunity.key)}
      />
      <div className="lfx-two-column">
        <CharacterFloor snapshot={snapshot} selected={selected} />
        <JesseSourceRoom snapshot={snapshot} />
      </div>
      <LineageInspector
        opportunity={selected}
        detail={detail}
        loading={detailLoading}
        error={detailError}
      />
      {error ? (
        <div className="lfx-inline-warning">LATEST REFRESH WARNING · {error}</div>
      ) : null}
    </section>
  );
}

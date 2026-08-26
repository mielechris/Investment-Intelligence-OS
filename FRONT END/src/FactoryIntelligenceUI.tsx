import { useEffect, useMemo, useState } from "react";
import LegacyApp from "./App";
import FactoryRoom from "./FactoryRoom";
import InterviewPortalPanel from "./InterviewPortalPanel";
import JesseIntelligencePanel from "./JesseIntelligencePanel";
import OpportunityFloor from "./OpportunityFloor";
import PaperCapitalControlPanel from "./PaperCapitalControlPanel";
import "./FactoryIntelligenceUI.css";

const API =
  import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8002";

type RoomKey =
  | "command"
  | "factory"
  | "research"
  | "cases"
  | "capital"
  | "judgment";

type PipelineStage = {
  id: string;
  name: string;
  status: string;
  version: string;
  room: string;
};

type SourceAvailability = {
  availability: string;
  error_type?: string | null;
};

type FactoryRoomRow = {
  key: string;
  label: string;
  count?: number | null;
  activity_count?: number | null;
};

type DeskRow = {
  key: string;
  name: string;
  room: string;
  focus: string;
  status: string;
  recent_completions: number;
};

type CaseRow = {
  case_id: string;
  ticker?: string | null;
  topic?: string | null;
  stage: string;
  active_room: string;
  latest_event?: string | null;
  latest_event_at?: string | null;
  agent_count: number;
  committee: string;
  committee_confidence?: number | null;
  risk: string;
  qualified: boolean;
  capital: string;
  sizing: string;
  authorization: string;
  paper_execution: string;
  trade_execution_permission: boolean;
  live_execution: boolean;
};

type ModelCard = {
  id: string;
  label: string;
  role: string;
  provider: string;
  availability: string;
  configured?: boolean | null;
  observation_status: string;
  stance: string;
  confidence?: number | null;
  citation_count: number;
  summary: string;
  provider_model?: string | null;
  latency_ms?: number | null;
  untrusted_model_output: boolean;
};

type Reconciliation = {
  available_model_count: number;
  consensus_stance: string;
  consensus_score?: number | null;
  divergence_score?: number | null;
  directional_conflict: boolean;
  skeptic_escalation_recommended: boolean;
};

type CalibrationModel = {
  model: string;
  sample_count: number;
  mature: boolean;
  quality_score?: number | null;
  composite_score?: number | null;
  recommended_task_weight?: number | null;
  recommendation_active: boolean;
  manual_review_required: boolean;
  automatically_applied_to_council: boolean;
};

type CalibrationTask = {
  task_type: string;
  status: string;
  mature_model_count: number;
  minimum_mature_models_required: number;
  models: CalibrationModel[];
  manual_promotion_required: boolean;
  automatically_applied_to_council: boolean;
};

type ProductionGate = {
  key: string;
  label: string;
  status: string;
  ready: boolean;
  detail: string;
  blocks_read_only_ui: boolean;
  blocks_live_execution: boolean;
};

type Activity = {
  recent_event_count?: number;
  agent_completions?: number;
  committee_completions?: number;
  risk_completions?: number;
  latest_event?: {
    event_type?: string;
    room?: string;
    created_at?: string;
  } | null;
  recent_events?: Array<{
    event_type?: string;
    room?: string;
    created_at?: string;
    case_id?: string;
  }>;
};

type FactoryOverview = {
  name: string;
  ui_version: string;
  system_version: string;
  generated_at: string;
  refresh_seconds: number;
  data_state: string;
  unknown_state_semantics: boolean;
  source_availability: Record<string, SourceAvailability>;
  pipeline: PipelineStage[];
  factory: {
    rooms: FactoryRoomRow[];
    activity: Activity;
    desks: DeskRow[];
    portfolio: Record<string, unknown>;
    validation: Record<string, unknown>;
  };
  cases: CaseRow[];
  case_count: number;
  council: {
    packet_count: number;
    latest_packet_id?: string | null;
    latest_case_id?: string | null;
    reconciliation: Reconciliation;
    models: ModelCard[];
    universal_model_weighting: boolean;
    governed_iios_committee_remains_authoritative: boolean;
  };
  calibration: {
    availability: string;
    calibration_version?: string | null;
    evaluation_count: number;
    minimum_samples_per_model_task: number;
    weight_bounds: {
      minimum: number;
      maximum: number;
    };
    model_weighting_mode: string;
    universal_model_weighting: boolean;
    manual_promotion_required: boolean;
    automatically_applied_to_council: boolean;
    tasks: CalibrationTask[];
  };
  production_gates: ProductionGate[];
  ready_gate_count: number;
  pending_gate_count: number;
  safety: {
    paper_mode: boolean;
    live_capital_locked: boolean;
    all_current_safety_invariants_pass: boolean;
    reported_violation_count: number;
    committee_override: boolean;
    risk_override: boolean;
    capital_authority: boolean;
    auto_trade_authority: boolean;
    trade_execution_permission: boolean;
    live_execution: boolean;
  };
};

type JourneyRow = {
  key: string;
  status: string;
  label: string;
  object_id?: string | null;
};

type CouncilView = {
  model?: string;
  status?: string;
  stance?: string;
  confidence?: number | null;
  summary?: string;
  citation_count?: number;
};

type CaseDetail = {
  case_id: string;
  topic?: string | null;
  ticker?: string | null;
  generated_at: string;
  journey: JourneyRow[];
  committee: {
    disposition: string;
    confidence?: number | null;
    headline: string;
    summary: string;
  };
  risk: {
    decision: string;
    triggered_rules: string[];
  };
  qualification: {
    qualified_buy_candidate: boolean;
    status: string;
  };
  council: {
    packet_id?: string | null;
    views: CouncilView[];
    reconciliation: Reconciliation | Record<string, unknown>;
    skeptic_escalation_recommended: boolean;
  };
  monitoring: {
    status: string;
    created_at?: string | null;
    latest_return_pct?: number | null;
    thesis_flags: string[];
  };
  paper_execution: {
    execution: string;
    reason?: string | null;
  };
  capital_authority: boolean;
  auto_trade_authority: boolean;
  trade_execution_permission: boolean;
  live_execution: boolean;
};

const ROOMS: Array<{
  key: RoomKey;
  label: string;
  eyebrow: string;
  description: string;
}> = [
  {
    key: "command",
    label: "Command",
    eyebrow: "FACTORY INTELLIGENCE",
    description:
      "Live operating picture, model council, gates, cases, and safety.",
  },
  {
    key: "factory",
    label: "Factory",
    eyebrow: "LIVING FLOOR",
    description:
      "Eight desks, case movement, rooms, recent activity, and the governed conveyor.",
  },
  {
    key: "research",
    label: "Research",
    eyebrow: "INTELLIGENCE ANNEX",
    description:
      "OpenAI core, Kimi deep research, Grok narrative intelligence, and opportunity discovery.",
  },
  {
    key: "cases",
    label: "Cases",
    eyebrow: "UNDERWRITING",
    description:
      "Case queue, evidence-to-paper journey, committee state, risk state, and monitoring.",
  },
  {
    key: "capital",
    label: "Capital",
    eyebrow: "CONTROL & RISK",
    description:
      "Paper capital controls, permanent locks, portfolio validation, and execution boundaries.",
  },
  {
    key: "judgment",
    label: "Judgment",
    eyebrow: "CALIBRATION LAB",
    description:
      "Task-specific model evaluation, manual promotion, and governed human judgment capture.",
  },
];

const ACTIVE_CASE_KEY = "iios.factoryIntelligence.activeCaseId";

async function apiJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      detail || `IIOS request failed with ${response.status}`,
    );
  }
  return response.json() as Promise<T>;
}

function percent(value?: number | null): string {
  if (
    value === undefined ||
    value === null ||
    Number.isNaN(value)
  ) {
    return "UNKNOWN";
  }
  return `${Math.round(value * 100)}%`;
}

function decimal(value?: number | null): string {
  if (
    value === undefined ||
    value === null ||
    Number.isNaN(value)
  ) {
    return "—";
  }
  return value.toFixed(3);
}

function timeLabel(value?: string | null): string {
  if (!value) return "UNKNOWN";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "UNKNOWN";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function shortModel(model: string): string {
  if (model === "IIOS_OPENAI_CORE") return "IIOS";
  if (model === "KIMI_RESEARCH") return "KIMI";
  if (model === "GROK_NARRATIVE") return "GROK";
  return model;
}

function stateClass(value: string): string {
  const normalized = value.toUpperCase();
  if (
    normalized.includes("READY") ||
    normalized.includes("COMPLETE") ||
    normalized.includes("LIVE") ||
    normalized === "AVAILABLE" ||
    normalized === "ACTIVE" ||
    normalized === "INTACT"
  ) {
    return "state-ready";
  }
  if (
    normalized.includes("PENDING") ||
    normalized.includes("INSUFFICIENT") ||
    normalized.includes("NO_") ||
    normalized.includes("UNKNOWN") ||
    normalized === "PARTIAL" ||
    normalized === "IDLE"
  ) {
    return "state-pending";
  }
  if (
    normalized.includes("OFFLINE") ||
    normalized.includes("ERROR") ||
    normalized.includes("BROKEN") ||
    normalized.includes("REJECT")
  ) {
    return "state-danger";
  }
  return "state-neutral";
}

function StatusPill({
  value,
  compact = false,
}: {
  value: string;
  compact?: boolean;
}) {
  return (
    <span
      className={`fi-status-pill ${stateClass(value)} ${
        compact ? "fi-status-pill--compact" : ""
      }`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
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
    <div className="fi-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="fi-empty">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function PipelineRail({
  pipeline,
}: {
  pipeline: PipelineStage[];
}) {
  return (
    <section className="fi-panel fi-pipeline-panel">
      <div className="fi-panel-heading">
        <div>
          <span className="fi-kicker">BATCH 8 RELEASE LINE</span>
          <h3>Intelligence engineering pipeline</h3>
        </div>
        <StatusPill
          value={
            pipeline.every((row) => row.status === "COMPLETE")
              ? "COMPLETE"
              : "IN PROGRESS"
          }
        />
      </div>
      <div className="fi-pipeline">
        {pipeline.map((stage, index) => (
          <div className="fi-pipeline-stage" key={stage.id}>
            <div className="fi-pipeline-index">{stage.id}</div>
            <div className="fi-pipeline-copy">
              <span>{stage.version}</span>
              <strong>{stage.name}</strong>
              <em>{stage.room.replaceAll("_", " ")}</em>
            </div>
            <StatusPill value={stage.status} compact />
            {index < pipeline.length - 1 ? (
              <div className="fi-pipeline-connector" />
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function SourceHealth({
  sources,
}: {
  sources: Record<string, SourceAvailability>;
}) {
  const rows = Object.entries(sources);
  return (
    <section className="fi-panel">
      <div className="fi-panel-heading">
        <div>
          <span className="fi-kicker">SOURCE TRUTH</span>
          <h3>Live backend contracts</h3>
        </div>
        <span className="fi-count">{rows.length} sources</span>
      </div>
      <div className="fi-source-grid">
        {rows.map(([key, source]) => (
          <div className="fi-source-row" key={key}>
            <div>
              <strong>{key.replaceAll("_", " ")}</strong>
              <span>
                {source.error_type
                  ? `ERROR TYPE: ${source.error_type}`
                  : "NO REPORTED CONTRACT ERROR"}
              </span>
            </div>
            <StatusPill value={source.availability} compact />
          </div>
        ))}
      </div>
    </section>
  );
}

function ModelCouncil({
  models,
  reconciliation,
}: {
  models: ModelCard[];
  reconciliation: Reconciliation;
}) {
  return (
    <section className="fi-panel fi-council-panel">
      <div className="fi-panel-heading">
        <div>
          <span className="fi-kicker">
            MULTI-MODEL INTELLIGENCE COUNCIL
          </span>
          <h3>Three views. One governed authority chain.</h3>
        </div>
        <div className="fi-council-summary">
          <StatusPill
            value={reconciliation.consensus_stance}
          />
          <span>
            Divergence{" "}
            {decimal(reconciliation.divergence_score)}
          </span>
        </div>
      </div>
      <div className="fi-model-grid">
        {models.map((model) => (
          <article className="fi-model-card" key={model.id}>
            <div className="fi-model-topline">
              <div className="fi-model-monogram">
                {shortModel(model.id)}
              </div>
              <StatusPill value={model.availability} compact />
            </div>
            <span className="fi-model-role">{model.role}</span>
            <h4>{model.label}</h4>
            <div className="fi-model-stats">
              <Metric
                label="Stance"
                value={model.stance}
              />
              <Metric
                label="Confidence"
                value={percent(model.confidence)}
              />
              <Metric
                label="Citations"
                value={model.citation_count}
              />
            </div>
            <p>{model.summary}</p>
            <footer>
              <span>{model.provider}</span>
              <span>
                {model.provider_model ?? "MODEL UNKNOWN"}
              </span>
            </footer>
          </article>
        ))}
      </div>
      <div className="fi-council-footer">
        <div>
          <span>Available models</span>
          <strong>
            {reconciliation.available_model_count} / 3
          </strong>
        </div>
        <div>
          <span>Directional conflict</span>
          <strong>
            {reconciliation.directional_conflict
              ? "YES"
              : "NO"}
          </strong>
        </div>
        <div>
          <span>Skeptic escalation</span>
          <strong>
            {reconciliation.skeptic_escalation_recommended
              ? "RECOMMENDED"
              : "NOT REQUIRED"}
          </strong>
        </div>
        <div>
          <span>Universal model weighting</span>
          <strong>DISABLED</strong>
        </div>
      </div>
    </section>
  );
}

function ProductionGates({
  gates,
}: {
  gates: ProductionGate[];
}) {
  return (
    <section className="fi-panel">
      <div className="fi-panel-heading">
        <div>
          <span className="fi-kicker">PRODUCTION GATES</span>
          <h3>Inputs and provider readiness</h3>
        </div>
        <span className="fi-count">
          {gates.filter((gate) => gate.ready).length} /{" "}
          {gates.length} ready
        </span>
      </div>
      <div className="fi-gate-list">
        {gates.map((gate) => (
          <div className="fi-gate" key={gate.key}>
            <div className="fi-gate-light" />
            <div>
              <strong>{gate.label}</strong>
              <p>{gate.detail}</p>
            </div>
            <StatusPill value={gate.status} compact />
          </div>
        ))}
      </div>
    </section>
  );
}

function SafetyLock({
  safety,
}: {
  safety: FactoryOverview["safety"];
}) {
  const controls = [
    ["PAPER MODE", safety.paper_mode],
    ["LIVE CAPITAL LOCKED", safety.live_capital_locked],
    ["COMMITTEE OVERRIDE", safety.committee_override],
    ["RISK OVERRIDE", safety.risk_override],
    ["CAPITAL AUTHORITY", safety.capital_authority],
    ["AUTO TRADE", safety.auto_trade_authority],
    ["TRADE EXECUTION", safety.trade_execution_permission],
    ["LIVE EXECUTION", safety.live_execution],
  ] as const;
  return (
    <section className="fi-safety-lock">
      <div className="fi-safety-title">
        <span>PERMANENT SAFETY RAIL</span>
        <strong>
          PAPER / SHADOW · LIVE CAPITAL LOCKED
        </strong>
      </div>
      <div className="fi-safety-controls">
        {controls.map(([label, enabled]) => {
          const expectedEnabled =
            label === "PAPER MODE" ||
            label === "LIVE CAPITAL LOCKED";
          const safe = enabled === expectedEnabled;
          return (
            <div
              className={`fi-safety-control ${
                safe ? "safe" : "unsafe"
              }`}
              key={label}
            >
              <span>{label}</span>
              <strong>{enabled ? "TRUE" : "FALSE"}</strong>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function CaseQueue({
  cases,
  activeCaseId,
  onSelect,
}: {
  cases: CaseRow[];
  activeCaseId: string | null;
  onSelect: (caseId: string) => void;
}) {
  if (!cases.length) {
    return (
      <EmptyState
        title="NO CASES IN THE FACTORY"
        detail="The backend returned an empty governed case queue. Nothing has been invented for display."
      />
    );
  }
  return (
    <div className="fi-case-table-wrap">
      <table className="fi-case-table">
        <thead>
          <tr>
            <th>Case</th>
            <th>Stage</th>
            <th>Desks</th>
            <th>Committee</th>
            <th>Risk</th>
            <th>Paper</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((row) => (
            <tr
              className={
                row.case_id === activeCaseId ? "active" : ""
              }
              key={row.case_id}
              onClick={() => onSelect(row.case_id)}
            >
              <td>
                <strong>{row.ticker ?? "NO TICKER"}</strong>
                <span>{row.topic ?? row.case_id}</span>
              </td>
              <td>
                <StatusPill value={row.stage} compact />
                <em>{row.active_room}</em>
              </td>
              <td>{row.agent_count}</td>
              <td>
                <strong>{row.committee}</strong>
                <span>
                  {percent(row.committee_confidence)}
                </span>
              </td>
              <td>{row.risk}</td>
              <td>{row.paper_execution}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CaseInspector({
  detail,
  loading,
}: {
  detail: CaseDetail | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <EmptyState
        title="OPENING CASE FOLDER"
        detail="Reading the latest governed objects from the ledger."
      />
    );
  }
  if (!detail) {
    return (
      <EmptyState
        title="NO CASE SELECTED"
        detail="Select a case from the queue to inspect its evidence-to-paper journey."
      />
    );
  }
  return (
    <div className="fi-case-inspector">
      <div className="fi-case-hero">
        <div>
          <span>{detail.ticker ?? "NO TICKER"}</span>
          <h3>{detail.topic ?? detail.case_id}</h3>
          <em>{detail.case_id}</em>
        </div>
        <div className="fi-case-decision">
          <StatusPill
            value={detail.committee.disposition}
          />
          <strong>
            {percent(detail.committee.confidence)}
          </strong>
        </div>
      </div>
      <div className="fi-journey">
        {detail.journey.map((row, index) => (
          <div className="fi-journey-step" key={row.key}>
            <div className="fi-journey-node">
              {index + 1}
            </div>
            <div>
              <span>{row.key.replaceAll("_", " ")}</span>
              <strong>{row.label}</strong>
              {row.object_id ? (
                <em>{row.object_id}</em>
              ) : null}
            </div>
            <StatusPill value={row.status} compact />
          </div>
        ))}
      </div>
      <div className="fi-inspector-grid">
        <article>
          <span>COMMITTEE</span>
          <h4>{detail.committee.headline}</h4>
          <p>{detail.committee.summary}</p>
        </article>
        <article>
          <span>RISK INSPECTION</span>
          <h4>{detail.risk.decision}</h4>
          <p>
            {detail.risk.triggered_rules.length
              ? detail.risk.triggered_rules.join(" · ")
              : "No triggered rules were returned."}
          </p>
        </article>
        <article>
          <span>QUALIFICATION</span>
          <h4>{detail.qualification.status}</h4>
          <p>
            Qualified buy candidate:{" "}
            {detail.qualification.qualified_buy_candidate
              ? "TRUE"
              : "FALSE"}
          </p>
        </article>
        <article>
          <span>MONITORING</span>
          <h4>{detail.monitoring.status}</h4>
          <p>
            {detail.monitoring.thesis_flags.length
              ? detail.monitoring.thesis_flags.join(" · ")
              : "No thesis flags were returned."}
          </p>
        </article>
      </div>
      <div className="fi-case-model-views">
        {(detail.council.views ?? []).length ? (
          detail.council.views.map((view, index) => (
            <article key={`${view.model ?? "model"}-${index}`}>
              <div>
                <strong>
                  {view.model ?? "UNKNOWN MODEL"}
                </strong>
                <StatusPill
                  value={view.status ?? "UNKNOWN"}
                  compact
                />
              </div>
              <span>
                {view.stance ?? "UNKNOWN"} ·{" "}
                {percent(view.confidence)} ·{" "}
                {view.citation_count ?? 0} citations
              </span>
              <p>
                {view.summary ??
                  "No model summary was returned."}
              </p>
            </article>
          ))
        ) : (
          <EmptyState
            title="NO MODEL COUNCIL PACKET"
            detail="This case has no persisted multi-model comparison yet."
          />
        )}
      </div>
    </div>
  );
}

function FactoryFloor({
  rooms,
  desks,
  activity,
}: {
  rooms: FactoryRoomRow[];
  desks: DeskRow[];
  activity: Activity;
}) {
  return (
    <>
      <div className="fi-floor-metrics">
        <Metric
          label="Recent events"
          value={activity.recent_event_count ?? 0}
          detail="5-minute factory window"
        />
        <Metric
          label="Desk completions"
          value={activity.agent_completions ?? 0}
        />
        <Metric
          label="Committee passes"
          value={activity.committee_completions ?? 0}
        />
        <Metric
          label="Risk inspections"
          value={activity.risk_completions ?? 0}
        />
      </div>
      <div className="fi-factory-map">
        {rooms.map((room, index) => (
          <div className="fi-room-tile" key={room.key}>
            <div className="fi-room-number">
              {String(index + 1).padStart(2, "0")}
            </div>
            <span>{room.key.replaceAll("_", " ")}</span>
            <strong>{room.label}</strong>
            <div>
              <em>{room.count ?? 0} cases</em>
              <em>{room.activity_count ?? 0} live events</em>
            </div>
          </div>
        ))}
      </div>
      <section className="fi-panel">
        <div className="fi-panel-heading">
          <div>
            <span className="fi-kicker">EIGHT SPECIALIST DESKS</span>
            <h3>Real roster and recent activity</h3>
          </div>
          <span className="fi-count">{desks.length} desks</span>
        </div>
        <div className="fi-desk-grid">
          {desks.map((desk) => (
            <article className="fi-desk-card" key={desk.key}>
              <div className="fi-desk-head">
                <span>{desk.key.toUpperCase()}</span>
                <StatusPill value={desk.status} compact />
              </div>
              <h4>{desk.name}</h4>
              <em>{desk.room}</em>
              <p>{desk.focus}</p>
              <footer>
                {desk.recent_completions} recent completions
              </footer>
            </article>
          ))}
        </div>
      </section>
      <section className="fi-panel">
        <div className="fi-panel-heading">
          <div>
            <span className="fi-kicker">FACTORY EVENT RAIL</span>
            <h3>Latest governed ledger movement</h3>
          </div>
          <span className="fi-count">
            {timeLabel(activity.latest_event?.created_at)}
          </span>
        </div>
        <div className="fi-event-rail">
          {(activity.recent_events ?? []).slice(0, 12).map(
            (event, index) => (
              <div
                className="fi-event-row"
                key={`${event.created_at ?? "event"}-${index}`}
              >
                <span>{timeLabel(event.created_at)}</span>
                <strong>
                  {event.event_type ?? "UNKNOWN EVENT"}
                </strong>
                <em>{event.room ?? "SYSTEM"}</em>
                <code>{event.case_id ?? "NO CASE"}</code>
              </div>
            ),
          )}
          {(activity.recent_events ?? []).length === 0 ? (
            <EmptyState
              title="NO RECENT LEDGER EVENTS"
              detail="The five-minute activity window is quiet."
            />
          ) : null}
        </div>
      </section>
    </>
  );
}

function CalibrationLab({
  calibration,
}: {
  calibration: FactoryOverview["calibration"];
}) {
  return (
    <section className="fi-panel fi-calibration-panel">
      <div className="fi-panel-heading">
        <div>
          <span className="fi-kicker">
            TASK-SPECIFIC MODEL CALIBRATION
          </span>
          <h3>No universal winner. Performance by job.</h3>
        </div>
        <StatusPill value={calibration.availability} />
      </div>
      <div className="fi-calibration-banner">
        <Metric
          label="Evaluations"
          value={calibration.evaluation_count}
        />
        <Metric
          label="Minimum samples"
          value={calibration.minimum_samples_per_model_task}
          detail="per model and task"
        />
        <Metric
          label="Weight floor"
          value={calibration.weight_bounds.minimum}
        />
        <Metric
          label="Weight ceiling"
          value={calibration.weight_bounds.maximum}
        />
        <Metric
          label="Promotion"
          value="MANUAL"
          detail="never automatic"
        />
      </div>
      <div className="fi-calibration-table-wrap">
        <table className="fi-calibration-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Status</th>
              <th>IIOS</th>
              <th>Kimi</th>
              <th>Grok</th>
              <th>Maturity</th>
            </tr>
          </thead>
          <tbody>
            {calibration.tasks.map((task) => {
              const lookup = new Map(
                task.models.map((model) => [
                  model.model,
                  model,
                ]),
              );
              const modelCell = (modelId: string) => {
                const model = lookup.get(modelId);
                return (
                  <td>
                    <strong>
                      {model?.recommended_task_weight ===
                        undefined ||
                      model?.recommended_task_weight === null
                        ? "—"
                        : model.recommended_task_weight.toFixed(
                            3,
                          )}
                    </strong>
                    <span>
                      {model?.sample_count ?? 0} samples
                    </span>
                  </td>
                );
              };
              return (
                <tr key={task.task_type}>
                  <td>
                    <strong>
                      {task.task_type.replaceAll("_", " ")}
                    </strong>
                  </td>
                  <td>
                    <StatusPill
                      value={task.status}
                      compact
                    />
                  </td>
                  {modelCell("IIOS_OPENAI_CORE")}
                  {modelCell("KIMI_RESEARCH")}
                  {modelCell("GROK_NARRATIVE")}
                  <td>
                    {task.mature_model_count} /{" "}
                    {task.minimum_mature_models_required}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="fi-governance-note">
        <strong>Calibration boundary</strong>
        <p>
          Recommendations are operational context only. They
          are not automatically applied to the council, cannot
          override Committee or Risk, and cannot authorize a
          paper or live order.
        </p>
      </div>
    </section>
  );
}

function CommandRoom({
  overview,
  activeCaseId,
  onSelectCase,
}: {
  overview: FactoryOverview;
  activeCaseId: string | null;
  onSelectCase: (caseId: string) => void;
}) {
  return (
    <>
      <div className="fi-command-metrics">
        <Metric
          label="System"
          value={`v${overview.system_version}`}
          detail={overview.data_state}
        />
        <Metric
          label="Cases"
          value={overview.case_count}
          detail="governed queue"
        />
        <Metric
          label="Council packets"
          value={overview.council.packet_count}
          detail="persisted comparisons"
        />
        <Metric
          label="Production gates"
          value={`${overview.ready_gate_count}/${
            overview.ready_gate_count +
            overview.pending_gate_count
          }`}
          detail="ready"
        />
        <Metric
          label="Safety violations"
          value={
            overview.safety.reported_violation_count
          }
          detail={
            overview.safety
              .all_current_safety_invariants_pass
              ? "current invariants pass"
              : "review required"
          }
        />
      </div>
      <PipelineRail pipeline={overview.pipeline} />
      <ModelCouncil
        models={overview.council.models}
        reconciliation={
          overview.council.reconciliation
        }
      />
      <div className="fi-two-column">
        <ProductionGates
          gates={overview.production_gates}
        />
        <SourceHealth
          sources={overview.source_availability}
        />
      </div>
      <section className="fi-panel">
        <div className="fi-panel-heading">
          <div>
            <span className="fi-kicker">CASE QUEUE</span>
            <h3>Where every case is right now</h3>
          </div>
          <span className="fi-count">
            {overview.case_count} governed cases
          </span>
        </div>
        <CaseQueue
          cases={overview.cases}
          activeCaseId={activeCaseId}
          onSelect={onSelectCase}
        />
      </section>
      <CalibrationLab
        calibration={overview.calibration}
      />
    </>
  );
}

function LoadingRoom() {
  return (
    <div className="fi-loading-room">
      <div className="fi-loading-orbit" />
      <span>CONNECTING TO THE INTELLIGENCE FACTORY</span>
      <strong>Reading live governed contracts…</strong>
    </div>
  );
}

export default function FactoryIntelligenceUI() {
  const [activeRoom, setActiveRoom] =
    useState<RoomKey>("command");
  const [overview, setOverview] =
    useState<FactoryOverview | null>(null);
  const [overviewError, setOverviewError] =
    useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastRefresh, setLastRefresh] =
    useState<string | null>(null);
  const [activeCaseId, setActiveCaseId] = useState<
    string | null
  >(() => window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [caseDetail, setCaseDetail] =
    useState<CaseDetail | null>(null);
  const [caseLoading, setCaseLoading] = useState(false);

  const room =
    ROOMS.find((item) => item.key === activeRoom) ??
    ROOMS[0];

  const activeCase = useMemo(
    () =>
      overview?.cases.find(
        (item) => item.case_id === activeCaseId,
      ) ?? null,
    [overview, activeCaseId],
  );

  const selectCase = (caseId: string) => {
    setActiveCaseId(caseId);
    window.localStorage.setItem(
      ACTIVE_CASE_KEY,
      caseId,
    );
  };

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;

    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await apiJson<FactoryOverview>(
          "/experience/factory-intelligence/overview",
          controller.signal,
        );
        if (disposed) return;
        setOverview(next);
        setConnected(true);
        setOverviewError(null);
        setLastRefresh(next.generated_at);
        setActiveCaseId((current) => {
          const currentExists =
            current !== null &&
            next.cases.some(
              (item) => item.case_id === current,
            );
          const selected = currentExists
            ? current
            : next.cases[0]?.case_id ?? null;
          if (selected) {
            window.localStorage.setItem(
              ACTIVE_CASE_KEY,
              selected,
            );
          } else {
            window.localStorage.removeItem(
              ACTIVE_CASE_KEY,
            );
          }
          return selected;
        });
      } catch (error) {
        if (
          disposed ||
          (error instanceof DOMException &&
            error.name === "AbortError")
        ) {
          return;
        }
        setConnected(false);
        setOverviewError(
          error instanceof Error
            ? error.message
            : "Factory overview unavailable.",
        );
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 10_000);

    return () => {
      disposed = true;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!activeCaseId) {
      setCaseDetail(null);
      return;
    }
    const controller = new AbortController();
    setCaseLoading(true);
    apiJson<CaseDetail>(
      `/experience/factory-intelligence/case/${encodeURIComponent(
        activeCaseId,
      )}`,
      controller.signal,
    )
      .then((detail) => {
        setCaseDetail(detail);
      })
      .catch((error) => {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }
        setCaseDetail(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setCaseLoading(false);
        }
      });
    return () => controller.abort();
  }, [activeCaseId, overview?.generated_at]);

  return (
    <main className="fi-shell">
      <header className="fi-masthead">
        <div className="fi-brand">
          <span>INVESTMENT INTELLIGENCE OS</span>
          <h1>THE INTELLIGENCE FACTORY</h1>
          <p>
            Evidence → 8 desks → Committee → Risk →
            Paper → Monitoring → Judgment Bank
          </p>
        </div>
        <div className="fi-live-command">
          <div className="fi-live-state">
            <i
              className={connected ? "online" : "offline"}
            />
            <span>
              {connected
                ? overview?.data_state ?? "CONNECTED"
                : "OFFLINE"}
            </span>
          </div>
          <strong>
            {overview
              ? `IIOS v${overview.system_version}`
              : "IIOS VERSION UNKNOWN"}
          </strong>
          <em>
            LAST REFRESH {timeLabel(lastRefresh)}
          </em>
        </div>
      </header>

      <SafetyLock
        safety={
          overview?.safety ?? {
            paper_mode: true,
            live_capital_locked: true,
            all_current_safety_invariants_pass: false,
            reported_violation_count: 0,
            committee_override: false,
            risk_override: false,
            capital_authority: false,
            auto_trade_authority: false,
            trade_execution_permission: false,
            live_execution: false,
          }
        }
      />

      <nav className="fi-room-nav" aria-label="IIOS rooms">
        {ROOMS.map((item) => (
          <button
            type="button"
            className={
              item.key === activeRoom ? "active" : ""
            }
            key={item.key}
            onClick={() => {
              setActiveRoom(item.key);
              window.scrollTo({
                top: 0,
                behavior: "smooth",
              });
            }}
          >
            <span>{item.eyebrow}</span>
            <strong>{item.label}</strong>
          </button>
        ))}
      </nav>

      <section className="fi-room-header">
        <div>
          <span>{room.eyebrow}</span>
          <h2>{room.label}</h2>
          <p>{room.description}</p>
        </div>
        <div className="fi-room-context">
          <span>ACTIVE CASE</span>
          <strong>
            {activeCase?.ticker ??
              activeCase?.case_id ??
              "NONE"}
          </strong>
          <em>
            {activeCase?.stage ?? "NO CASE SELECTED"}
          </em>
        </div>
      </section>

      {overviewError ? (
        <div className="fi-error-banner">
          <strong>FACTORY CONTRACT OFFLINE</strong>
          <p>
            {overviewError}. The screen is retaining explicit
            offline state rather than manufacturing data.
          </p>
        </div>
      ) : null}

      {!overview ? (
        <LoadingRoom />
      ) : (
        <section
          className={`fi-room-body fi-room-body--${activeRoom}`}
        >
          {activeRoom === "command" ? (
            <CommandRoom
              overview={overview}
              activeCaseId={activeCaseId}
              onSelectCase={selectCase}
            />
          ) : null}

          {activeRoom === "factory" ? (
            <>
              <FactoryFloor
                rooms={overview.factory.rooms}
                desks={overview.factory.desks}
                activity={overview.factory.activity}
              />
              <details className="fi-native-drawer">
                <summary>
                  Open the existing governed factory conveyor
                </summary>
                <div className="fi-native-workspace">
                  <FactoryRoom />
                </div>
              </details>
            </>
          ) : null}

          {activeRoom === "research" ? (
            <>
              <ModelCouncil
                models={overview.council.models}
                reconciliation={
                  overview.council.reconciliation
                }
              />
              <ProductionGates
                gates={overview.production_gates}
              />
              <details
                className="fi-native-drawer"
                open
              >
                <summary>Opportunity discovery floor</summary>
                <div className="fi-native-workspace">
                  <OpportunityFloor />
                </div>
              </details>
              <details className="fi-native-drawer">
                <summary>
                  Jesse and external research intelligence
                </summary>
                <div className="fi-native-workspace">
                  <JesseIntelligencePanel />
                </div>
              </details>
            </>
          ) : null}

          {activeRoom === "cases" ? (
            <>
              <section className="fi-panel">
                <div className="fi-panel-heading">
                  <div>
                    <span className="fi-kicker">
                      GOVERNED CASE QUEUE
                    </span>
                    <h3>Select a live case folder</h3>
                  </div>
                  <span className="fi-count">
                    {overview.case_count} cases
                  </span>
                </div>
                <CaseQueue
                  cases={overview.cases}
                  activeCaseId={activeCaseId}
                  onSelect={selectCase}
                />
              </section>
              <section className="fi-panel">
                <CaseInspector
                  detail={caseDetail}
                  loading={caseLoading}
                />
              </section>
              <details className="fi-native-drawer">
                <summary>
                  Open legacy underwriting controls
                </summary>
                <div className="fi-native-workspace">
                  <LegacyApp />
                </div>
              </details>
            </>
          ) : null}

          {activeRoom === "capital" ? (
            <>
              <SafetyLock safety={overview.safety} />
              <div className="fi-two-column">
                <ProductionGates
                  gates={overview.production_gates}
                />
                <section className="fi-panel">
                  <div className="fi-panel-heading">
                    <div>
                      <span className="fi-kicker">
                        EXECUTION BOUNDARY
                      </span>
                      <h3>Authority remains locked</h3>
                    </div>
                    <StatusPill value="PAPER ONLY" />
                  </div>
                  <div className="fi-lock-list">
                    <div>
                      <span>Committee authority</span>
                      <strong>AUTHORITATIVE</strong>
                    </div>
                    <div>
                      <span>Risk authority</span>
                      <strong>AUTHORITATIVE</strong>
                    </div>
                    <div>
                      <span>Model council override</span>
                      <strong>FALSE</strong>
                    </div>
                    <div>
                      <span>Calibration override</span>
                      <strong>FALSE</strong>
                    </div>
                    <div>
                      <span>Live execution</span>
                      <strong>FALSE</strong>
                    </div>
                  </div>
                </section>
              </div>
              <details
                className="fi-native-drawer"
                open
              >
                <summary>
                  Governed paper capital controls
                </summary>
                <div className="fi-native-workspace">
                  <PaperCapitalControlPanel />
                </div>
              </details>
            </>
          ) : null}

          {activeRoom === "judgment" ? (
            <>
              <CalibrationLab
                calibration={overview.calibration}
              />
              <details
                className="fi-native-drawer"
                open
              >
                <summary>
                  Professional interview and Judgment Bank portal
                </summary>
                <div className="fi-native-workspace">
                  <InterviewPortalPanel />
                </div>
              </details>
            </>
          ) : null}
        </section>
      )}

      <footer className="fi-footer">
        <div>
          <strong>IIOS FACTORY INTELLIGENCE UI</strong>
          <span>
            READ-ONLY OPERATING SURFACE · UNKNOWN MEANS
            UNKNOWN
          </span>
        </div>
        <div>
          <span>COMMITTEE + RISK REMAIN AUTHORITATIVE</span>
          <strong>LIVE EXECUTION: FALSE</strong>
        </div>
      </footer>
    </main>
  );
}

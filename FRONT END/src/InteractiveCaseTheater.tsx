import { useEffect, useMemo, useState } from "react";
import "./InteractiveCaseTheater.css";

type ValidationLayer = {
  availability: string;
  payload?: Record<string, unknown> | null;
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
  committee?: Record<string, unknown> | null;
  risk?: Record<string, unknown> | null;
  paper_execution?: Record<string, unknown> | null;
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

type FactoryOverview = {
  cases?: CaseRow[];
};

type JesseStatus = {
  latest_scan?: Record<string, unknown> | null;
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
    payload?: FactoryOverview | null;
  };
  jesse_dislocation: {
    availability: string;
    payload?: JesseStatus | null;
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
  qualification?: Record<string, unknown> | null;
  council?: {
    packet_id?: string | null;
    views?: Record<string, unknown>[] | null;
    reconciliation?: Record<string, unknown> | null;
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
  learning: Record<string, unknown> | null;
  jesse: Record<string, unknown> | null;
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
  rawArtifact?: Record<string, unknown> | null;
};

const STAGE_KEYS = [
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
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return fallback;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function pct(value: unknown): string {
  const n = numberValue(value);
  return n === null ? "—" : `${n.toFixed(2)}%`;
}

function confidence(value: unknown): string {
  const n = numberValue(value);
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

function money(value: unknown): string {
  const n = numberValue(value);
  return n === null
    ? "—"
    : n.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      });
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

function normalize(value: unknown): string {
  return text(value, "UNKNOWN").toUpperCase().replaceAll(" ", "_");
}

function statusTone(value: string): string {
  const state = normalize(value);
  if (
    state.includes("COMPLETE") ||
    state.includes("RECORDED") ||
    state.includes("APPROV") ||
    state.includes("EXECUTED") ||
    state.includes("AVAILABLE") ||
    state.includes("OBSERVED")
  ) return "good";
  if (
    state.includes("REJECT") ||
    state.includes("FAIL") ||
    state.includes("BLOCK") ||
    state.includes("ERROR") ||
    state.includes("NO_TRADE")
  ) return "bad";
  return "warm";
}

function journeyByKey(detail: CaseDetail | null, key: string): JourneyRow | null {
  const journey = Array.isArray(detail?.journey) ? detail!.journey! : [];
  return journey.find((row) => normalize(row.key) === key) ?? null;
}

function latestJesseRows(snapshot: LivingSnapshot): Map<string, Record<string, unknown>> {
  const scan = record(snapshot.jesse_dislocation.payload?.latest_scan);
  const merged = [...rows(scan.top_three), ...rows(scan.losers)];
  const output = new Map<string, Record<string, unknown>>();
  for (const row of merged) {
    const ticker = text(row.ticker, "").toUpperCase();
    if (!ticker || output.has(ticker)) continue;
    const decline = record(row.decline_analysis);
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
  const telemetry = record(snapshot.validation.layers.factory_telemetry.payload);
  const promotions = rows(telemetry.recent_promotions) as Promotion[];
  const cases = snapshot.factory.payload?.cases ?? [];
  const outcomes = rows(record(snapshot.validation.layers.outcome_learning.payload).recent_outcomes);
  const outcomeByTicker = new Map(
    outcomes
      .map((row) => [text(row.ticker, "").toUpperCase(), row] as const)
      .filter(([ticker]) => Boolean(ticker)),
  );
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
      const ticker = text(promotion?.ticker, text(overview?.ticker, "NO TICKER")).toUpperCase();
      const jesse = jesseByTicker.get(ticker) ?? null;
      const provenance = promotion
        ? jesse
          ? "BOTH" as const
          : "9E RADAR" as const
        : jesse
          ? "JESSE DISLOCATION" as const
          : "MANUAL / OTHER" as const;
      return {
        caseId,
        ticker,
        topic: text(promotion?.topic, text(overview?.topic, ticker)),
        promotion,
        overview,
        learning: outcomeByTicker.get(ticker) ?? null,
        jesse,
        provenance,
      };
    })
    .sort((left, right) => {
      const leftTime = new Date(text(left.promotion?.promoted_at, text(left.overview?.latest_event_at, "1970-01-01"))).getTime();
      const rightTime = new Date(text(right.promotion?.promoted_at, text(right.overview?.latest_event_at, "1970-01-01"))).getTime();
      return rightTime - leftTime;
    })
    .slice(0, 40);
}

function councilViewSummary(view: Record<string, unknown>): string {
  const provider = text(view.provider, text(view.model, text(view.source, "Council view")));
  const disposition = text(view.disposition, text(view.recommendation, text(view.verdict, "RECORDED")));
  const rationale = text(view.rationale, text(view.summary, text(view.reason, "Persisted council artifact available.")));
  return `${provider}: ${disposition} — ${rationale}`;
}

function buildStages(theaterCase: TheaterCase, detail: CaseDetail | null): TheaterStage[] {
  const promotion = theaterCase.promotion;
  const agents = promotion?.agents ?? null;
  const agentKeys = Array.isArray(agents?.agent_keys) ? agents!.agent_keys! : [];
  const agentNames = agentKeys.map((key) => AGENT_NAMES[key] ?? key);
  const research = journeyByKey(detail, "KIMI_RESEARCH");
  const committeeJourney = journeyByKey(detail, "COMMITTEE");
  const councilJourney = journeyByKey(detail, "MULTI_MODEL_COUNCIL");
  const riskJourney = journeyByKey(detail, "RISK");
  const paperJourney = journeyByKey(detail, "PAPER_EXECUTION");
  const evidenceJourney = journeyByKey(detail, "EVIDENCE");
  const council = detail?.council ?? null;
  const views = Array.isArray(council?.views) ? council!.views! : [];
  const learning = theaterCase.learning;
  const marketOutcome = text(learning?.market_outcome_label, "WARM-UP");
  const quality = text(learning?.decision_quality_label, "WARM-UP");
  const monitoring = detail?.monitoring ?? null;
  const paper = detail?.paper_execution ?? null;
  const skepticCompleted = agentKeys.includes("skeptic");
  const skepticEscalation = council?.skeptic_escalation_recommended;

  const discoveryStatus = promotion ? "COMPLETE" : evidenceJourney ? "CASE EXISTS" : "WAITING";
  const researchStatus = research ? text(research.status, "COMPLETE") : "WAITING";
  const agentsCompleted = Number(agents?.completed_count ?? theaterCase.overview?.agent_count ?? 0);
  const agentStatus = agentsCompleted >= 8 ? "8 / 8 COMPLETE" : agentsCompleted > 0 ? `${agentsCompleted} / 8 COMPLETE` : "WAITING";
  const skepticStatus = skepticCompleted ? "COMPLETE" : "WAITING";
  const committeeStatus = text(detail?.committee?.disposition, committeeJourney ? text(committeeJourney.status, "RECORDED") : "WAITING");
  const riskStatus = text(detail?.risk?.decision, riskJourney ? text(riskJourney.status, "RECORDED") : "WAITING");
  const paperStatus = text(paper?.execution, paperJourney ? text(paperJourney.status, "RECORDED") : "WAITING");
  const monitorStatus = text(monitoring?.status, learning ? "OBSERVED VIA 9J" : "WAITING");
  const outcomeStatus = learning ? marketOutcome : "WARM-UP";
  const learningStatus = learning ? quality : "WARM-UP";

  return [
    {
      key: "DISCOVERY",
      label: "Discovery",
      status: discoveryStatus,
      source: promotion ? "9G / 9E promotion lineage" : "Governed case record",
      sourceId: text(promotion?.source_candidate_id, theaterCase.caseId),
      timestamp: text(promotion?.promoted_at, text(theaterCase.overview?.latest_event_at, "")),
      headline: promotion
        ? `${theaterCase.ticker} was promoted from the persisted 9E opportunity pipeline.`
        : `${theaterCase.ticker} exists as a governed case, but its original promotion is outside the current 9G telemetry window.`,
      body: promotion
        ? `Opportunity score ${text(promotion.opportunity_score, "—")} · radar rank ${text(promotion.radar_rank_score, "—")} · priority ${text(promotion.priority, "—")}.`
        : "The theater refuses to infer a 9E source candidate when current persisted promotion lineage is unavailable.",
      facts: [
        { label: "Signal provenance", value: theaterCase.provenance },
        { label: "Source candidate", value: text(promotion?.source_candidate_id, "NOT IN CURRENT 9G WINDOW") },
        { label: "Case", value: theaterCase.caseId },
      ],
      rawArtifact: promotion ? record(promotion) : null,
    },
    {
      key: "RESEARCH",
      label: "Research",
      status: researchStatus,
      source: "Read-only case journey",
      sourceId: text(research?.object_id, "WAITING"),
      timestamp: text(research?.created_at, ""),
      headline: research
        ? "A persisted Kimi research object exists for this case."
        : "Research artifact is not exposed for this case yet.",
      body: research
        ? "9N shows the persisted research-object identity and completion state. It does not invent research text that the current read-only contract does not return."
        : "WAITING — the replay holds this room empty until a persisted research object is visible.",
      facts: [
        { label: "Object", value: text(research?.object_id, "WAITING") },
        { label: "Status", value: researchStatus },
      ],
    },
    {
      key: "AGENTS",
      label: "8 Agents",
      status: agentStatus,
      source: "9G persisted promotion lineage",
      sourceId: theaterCase.caseId,
      timestamp: text(promotion?.promoted_at, ""),
      headline: agentsCompleted > 0
        ? `${agentsCompleted} specialist completion${agentsCompleted === 1 ? "" : "s"} are persisted in current lineage.`
        : "No specialist completion roster is exposed in the current 9G lineage.",
      body: "RAW AGENT TEXT NOT EXPOSED BY READ-ONLY CONTRACT. 9N shows only persisted completion keys and never fabricates an agent debate transcript.",
      facts: [
        { label: "Completed", value: `${agentsCompleted} / 8` },
        { label: "Roster", value: agentNames.length ? agentNames.join(" · ") : "WAITING" },
      ],
      rawArtifact: agents ? record(agents) : null,
    },
    {
      key: "SKEPTIC",
      label: "Skeptic",
      status: skepticStatus,
      source: skepticCompleted ? "9G persisted agent completion roster" : "No persisted Skeptic completion in current lineage",
      sourceId: skepticCompleted ? theaterCase.caseId : "WAITING",
      timestamp: text(promotion?.promoted_at, ""),
      headline: skepticCompleted
        ? "Skeptic / Red Team is present in the persisted completion roster."
        : "The theater will not invent a Skeptic challenge.",
      body: skepticCompleted
        ? `Completion is persisted. RAW SKEPTIC TEXT NOT EXPOSED BY READ-ONLY CONTRACT.${skepticEscalation === true ? " The persisted council also recommends Skeptic escalation." : ""}`
        : "WAITING — no raw challenge or completion is represented without a persisted source.",
      facts: [
        { label: "Specialist completion", value: skepticCompleted ? "PERSISTED" : "WAITING" },
        { label: "Council escalation", value: skepticEscalation === true ? "RECOMMENDED" : skepticEscalation === false ? "NOT RECOMMENDED" : "NOT EXPOSED" },
      ],
    },
    {
      key: "COMMITTEE",
      label: "Committee",
      status: committeeStatus,
      source: "Persisted Committee + multi-model council artifacts",
      sourceId: text(detail?.committee?.decision_id, text(committeeJourney?.object_id, "WAITING")),
      timestamp: text(committeeJourney?.created_at, ""),
      headline: text(detail?.committee?.headline, committeeJourney ? `Committee recorded ${committeeStatus}.` : "Committee has not produced a persisted decision for this replay."),
      body: text(detail?.committee?.summary, views.length ? views.map(councilViewSummary).join("\n") : "WAITING — no Committee summary or council views exposed."),
      facts: [
        { label: "Disposition", value: committeeStatus },
        { label: "Confidence", value: confidence(detail?.committee?.confidence) },
        { label: "Council packet", value: text(council?.packet_id, text(councilJourney?.object_id, "—")) },
        { label: "Persisted council views", value: String(views.length) },
      ],
      rawArtifact: detail?.committee ? record(detail.committee) : null,
    },
    {
      key: "RISK",
      label: "Risk",
      status: riskStatus,
      source: "Persisted deterministic Risk authorization",
      sourceId: text(detail?.risk?.risk_authorization_id, text(riskJourney?.object_id, "WAITING")),
      timestamp: text(riskJourney?.created_at, ""),
      headline: riskJourney ? `Risk recorded ${riskStatus}.` : "Risk has not produced a persisted authorization for this replay.",
      body: Array.isArray(detail?.risk?.triggered_rules) && detail!.risk!.triggered_rules!.length
        ? `Triggered rules: ${detail!.risk!.triggered_rules!.join(" · ")}`
        : "No triggered Risk rules are exposed in the current read-only case detail.",
      facts: [
        { label: "Decision", value: riskStatus },
        { label: "Authorization", value: text(detail?.risk?.risk_authorization_id, "WAITING") },
      ],
      rawArtifact: detail?.risk ? record(detail.risk) : null,
    },
    {
      key: "PAPER",
      label: "Paper",
      status: paperStatus,
      source: "Persisted governed paper execution",
      sourceId: text(paper?.execution_id, text(paperJourney?.object_id, "WAITING")),
      timestamp: text(paperJourney?.created_at, ""),
      headline: paperJourney ? `Governed PAPER state recorded: ${paperStatus}.` : "No governed paper execution is persisted for this replay.",
      body: paperJourney
        ? `Notional ${money(paper?.notional)}. ${text(paper?.reason, "Paper state came from persisted case detail.")}`
        : "WAITING — this does not imply a paper order occurred.",
      facts: [
        { label: "Execution", value: paperStatus },
        { label: "Notional", value: money(paper?.notional) },
        { label: "LIVE execution", value: detail?.live_execution === true ? "TRUE" : "FALSE" },
      ],
      rawArtifact: paper ? record(paper) : null,
    },
    {
      key: "MONITORING",
      label: "Monitoring",
      status: monitorStatus,
      source: "Persisted case monitor snapshot",
      sourceId: theaterCase.caseId,
      timestamp: text(monitoring?.created_at, ""),
      headline: monitoring ? `Monitoring state: ${monitorStatus}.` : "Monitoring is still waiting for a persisted snapshot.",
      body: monitoring
        ? `Latest recorded return ${pct(monitoring.latest_return_pct)}. Thesis flags: ${Array.isArray(monitoring.thesis_flags) && monitoring.thesis_flags.length ? monitoring.thesis_flags.join(" · ") : "none exposed"}.`
        : "No monitoring return or thesis flag is invented.",
      facts: [
        { label: "Status", value: monitorStatus },
        { label: "Latest return", value: pct(monitoring?.latest_return_pct) },
      ],
      rawArtifact: monitoring ? record(monitoring) : null,
    },
    {
      key: "OUTCOME",
      label: "Outcome",
      status: outcomeStatus,
      source: "9J persisted outcome memory",
      sourceId: text(learning?.outcome_id, text(learning?.session_id, "WARM-UP")),
      timestamp: text(learning?.labeled_at, text(learning?.created_at, "")),
      headline: learning ? `9J recorded market outcome ${marketOutcome}.` : "Outcome has not matured into current 9J memory yet.",
      body: learning
        ? `Observed returns remain measurement evidence; they do not rewrite the original decision. 1d ${pct(learning.return_1d_pct)} · 3d ${pct(learning.return_3d_pct)} · 5d ${pct(learning.return_5d_pct)}.`
        : "WARM-UP — eventual outcome remains unknown in the current persisted learning window.",
      facts: [
        { label: "Market outcome", value: marketOutcome },
        { label: "1-day", value: pct(learning?.return_1d_pct) },
        { label: "5-day", value: pct(learning?.return_5d_pct) },
      ],
      rawArtifact: learning,
    },
    {
      key: "LEARNING",
      label: "Learning",
      status: learningStatus,
      source: "9J Outcome Learning Memory",
      sourceId: text(learning?.outcome_id, text(learning?.session_id, "WARM-UP")),
      timestamp: text(learning?.labeled_at, text(learning?.created_at, "")),
      headline: learning ? `Decision quality: ${quality}.` : "Learning remains in WARM-UP until a persisted 9J label exists.",
      body: learning
        ? `9J market outcome ${marketOutcome} · decision quality ${quality}. The theater presents the persisted label without changing thresholds, agent weights, Committee logic or Risk rules.`
        : "No learning label is manufactured to make an incomplete case feel finished.",
      facts: [
        { label: "Decision quality", value: quality },
        { label: "Market outcome", value: marketOutcome },
        { label: "Auto-improvement authority", value: "FALSE" },
      ],
      rawArtifact: learning,
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
    const detail = await response.text();
    throw new Error(detail || `IIOS read-only sidecar request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function StageStatus({ value }: { value: string }) {
  return <span className={`ict-status ict-status--${statusTone(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function ProvenanceBadge({ value }: { value: TheaterCase["provenance"] }) {
  return <span className={`ict-provenance ict-provenance--${value.toLowerCase().replaceAll(" ", "-").replaceAll("/", "-")}`}>{value}</span>;
}

function CaseRail({ cases, selected, onSelect }: {
  cases: TheaterCase[];
  selected: TheaterCase | null;
  onSelect: (row: TheaterCase) => void;
}) {
  return (
    <aside className="ict-case-rail">
      <div className="ict-heading">
        <span>GOVERNED CASE LIBRARY</span>
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
    let controller: AbortController | null = null;
    const refresh = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await getJson<LivingSnapshot>("/living/overview", controller.signal);
        if (disposed) return;
        setSnapshot(next);
        setSnapshotError(null);
      } catch (reason) {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setSnapshotError(reason instanceof Error ? reason.message : "Living case source unavailable");
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

  const cases = useMemo(() => (snapshot ? buildCaseRoster(snapshot) : []), [snapshot]);
  const selected = useMemo(
    () => cases.find((row) => row.caseId === selectedCaseId) ?? cases[0] ?? null,
    [cases, selectedCaseId],
  );

  useEffect(() => {
    if (!selected?.caseId) return;
    const controller = new AbortController();
    let disposed = false;
    void getJson<CaseDetail>(`/living/case/${encodeURIComponent(selected.caseId)}`, controller.signal)
      .then((next) => {
        if (disposed) return;
        setDetail(next);
        setDetailCaseId(selected.caseId);
        setDetailError(null);
      })
      .catch((reason: unknown) => {
        if (disposed || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setDetail(null);
        setDetailCaseId(null);
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

  useEffect(() => {
    if (!playing || stages.length === 0) return;
    const timer = window.setInterval(() => {
      setCursor((current) => {
        if (current >= stages.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 1_200);
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

              <div className="ict-lineage-strip">
                {STAGE_KEYS.map(([key, label], index) => {
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
                  This theater changes only a browser cursor. It cannot rerun an agent, rerun Committee, change Risk, submit a paper order, alter a learning label or grant capital authority. RAW AGENT TEXT NOT EXPOSED BY READ-ONLY CONTRACT, so no synthetic transcript is substituted.
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

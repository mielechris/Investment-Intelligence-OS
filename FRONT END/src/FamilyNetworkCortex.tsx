import { useEffect, useMemo, useState } from "react";
import "./FamilyNetworkCortex.css";

const API =
  import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8002";

const ACTIVE_CASE_KEY = "iios.factoryIntelligence.activeCaseId";
const ACTIVE_WINDOW_SECONDS = 300;
const RECENT_WINDOW_SECONDS = 90;

type CortexEvent = {
  event_type?: string | null;
  case_id?: string | null;
  created_at?: string | null;
  room?: string | null;
  payload?: {
    agent_key?: string | null;
    confidence?: number | null;
    disposition?: string | null;
    orchestration_wave?: number | null;
    [key: string]: unknown;
  } | null;
};

type Desk = {
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
  stage?: string | null;
  committee?: string | null;
  committee_confidence?: number | null;
  risk?: string | null;
  capital?: string | null;
  sizing?: string | null;
  authorization?: string | null;
  paper_execution?: string | null;
};

type FactoryOverview = {
  data_state: string;
  generated_at: string;
  factory: {
    desks: Desk[];
    activity: {
      recent_event_count?: number;
      latest_event?: CortexEvent | null;
      recent_events?: CortexEvent[];
    };
  };
  cases: CaseRow[];
};

type Worker = {
  cadence_state?: string | null;
  last_completed_at?: string | null;
  next_due_at?: string | null;
};

type PaperFundOperations = {
  observation: Worker & {
    latest_promoted_case?: {
      case_id?: string | null;
      ticker?: string | null;
      score?: number | null;
    } | null;
  };
  paper_trading: Worker & {
    market_phase?: string | null;
    paper_execution_window_open?: boolean;
  };
  latest_deepened_case?: {
    case_id?: string | null;
    ticker?: string | null;
    topic?: string | null;
    qualified?: boolean;
  } | null;
};

type NodeState = "working" | "recent" | "blocked" | "idle" | "offline";

type AgentSpec = {
  key: string;
  alias: string;
  canonical: string;
  x: number;
  y: number;
};

type LinkSpec = {
  id: string;
  from: string;
  to: string;
  d: string;
};

const AGENTS: AgentSpec[] = [
  {
    key: "policy",
    alias: "Policy Crew",
    canonical: "Policy Analyst",
    x: 95,
    y: 92,
  },
  {
    key: "macro",
    alias: "The Banker",
    canonical: "Macro & Rates",
    x: 190,
    y: 58,
  },
  {
    key: "fundamentals",
    alias: "The Books",
    canonical: "Fundamentals",
    x: 330,
    y: 58,
  },
  {
    key: "market_structure",
    alias: "The Tape",
    canonical: "Market Structure",
    x: 425,
    y: 92,
  },
  {
    key: "commodities",
    alias: "The Supplier",
    canonical: "Commodities",
    x: 90,
    y: 188,
  },
  {
    key: "geo_weather",
    alias: "The Scout",
    canonical: "Geo & Weather",
    x: 430,
    y: 188,
  },
  {
    key: "skeptic",
    alias: "Consigliere",
    canonical: "Skeptic / Red Team",
    x: 160,
    y: 278,
  },
  {
    key: "portfolio",
    alias: "The Treasurer",
    canonical: "Portfolio Context",
    x: 360,
    y: 278,
  },
];

const LINKS: LinkSpec[] = [
  { id: "objective-policy", from: "objective", to: "policy", d: "M260 165 Q175 110 95 92" },
  { id: "objective-macro", from: "objective", to: "macro", d: "M260 165 Q230 95 190 58" },
  { id: "objective-fundamentals", from: "objective", to: "fundamentals", d: "M260 165 Q292 95 330 58" },
  { id: "objective-market", from: "objective", to: "market_structure", d: "M260 165 Q345 110 425 92" },
  { id: "objective-commodities", from: "objective", to: "commodities", d: "M260 165 Q165 170 90 188" },
  { id: "objective-geo", from: "objective", to: "geo_weather", d: "M260 165 Q355 170 430 188" },
  { id: "policy-skeptic", from: "policy", to: "skeptic", d: "M95 92 Q105 225 160 278" },
  { id: "macro-skeptic", from: "macro", to: "skeptic", d: "M190 58 Q190 190 160 278" },
  { id: "fundamentals-skeptic", from: "fundamentals", to: "skeptic", d: "M330 58 Q265 185 160 278" },
  { id: "market-skeptic", from: "market_structure", to: "skeptic", d: "M425 92 Q330 220 160 278" },
  { id: "commodities-skeptic", from: "commodities", to: "skeptic", d: "M90 188 Q120 245 160 278" },
  { id: "geo-skeptic", from: "geo_weather", to: "skeptic", d: "M430 188 Q315 250 160 278" },
  { id: "skeptic-portfolio", from: "skeptic", to: "portfolio", d: "M160 278 Q260 315 360 278" },
  { id: "agents-committee-a", from: "skeptic", to: "committee", d: "M160 278 Q200 330 260 338" },
  { id: "agents-committee-b", from: "portfolio", to: "committee", d: "M360 278 Q320 330 260 338" },
  { id: "committee-risk", from: "committee", to: "risk", d: "M260 338 Q315 348 355 354" },
  { id: "risk-capital", from: "risk", to: "capital", d: "M355 354 Q400 350 430 338" },
  { id: "capital-paper", from: "capital", to: "paper", d: "M430 338 Q465 325 490 302" },
];

const EVENT_ALIASES: Record<string, string> = {
  AGENT_STARTED: "started work",
  AGENT_COMPLETE: "finished analysis",
  AGENT_FAILED_CLOSED: "failed closed",
  EIGHT_AGENT_ORCHESTRATION_COMPLETE: "crew review complete",
  COMMITTEE_STARTED: "sit-down started",
  COMMITTEE_COMPLETE: "sit-down complete",
  RISK_COMPLETE: "risk inspection complete",
  PAPER_TRADING_CYCLE_COMPLETE: "paper ops cycle complete",
  OBSERVATION_CYCLE_COMPLETE: "observation cycle complete",
};

async function apiJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(
      (await response.text()) || `IIOS request failed ${response.status}`,
    );
  }
  return response.json() as Promise<T>;
}

function parseTime(value?: string | null): number | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function ageSeconds(event: CortexEvent | undefined, now: number): number {
  const parsed = parseTime(event?.created_at);
  if (parsed === null) return Number.POSITIVE_INFINITY;
  return Math.max(0, (now - parsed) / 1000);
}

function normalized(value?: string | null): string {
  return String(value || "UNKNOWN").toUpperCase();
}

function isBlocked(value?: string | null): boolean {
  const text = normalized(value);
  return [
    "VETO",
    "BLOCK",
    "REJECT",
    "ERROR",
    "FAILED",
    "NO_TRADE",
    "BROKEN",
    "INVALID",
  ].some((token) => text.includes(token));
}

function caseTicker(
  caseId: string | null,
  cases: CaseRow[],
): string | null {
  if (!caseId) return null;
  return (
    cases.find((row) => row.case_id === caseId)?.ticker ?? null
  );
}

function eventLabel(event: CortexEvent): string {
  const type = normalized(event.event_type);
  return EVENT_ALIASES[type] ?? type.replaceAll("_", " ").toLowerCase();
}

function systemState(
  event: CortexEvent | undefined,
  now: number,
  blockedValue?: string | null,
): NodeState {
  if (blockedValue && isBlocked(blockedValue)) return "blocked";
  if (!event) return "idle";
  const age = ageSeconds(event, now);
  if (age <= RECENT_WINDOW_SECONDS) return "recent";
  return "idle";
}

export default function FamilyNetworkCortex() {
  const [open, setOpen] = useState(true);
  const [overview, setOverview] = useState<FactoryOverview | null>(null);
  const [operations, setOperations] = useState<PaperFundOperations | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(() =>
    window.localStorage.getItem(ACTIVE_CASE_KEY),
  );

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const [nextOverview, nextOperations] = await Promise.all([
          apiJson<FactoryOverview>("/experience/factory-intelligence/overview"),
          apiJson<PaperFundOperations>("/paper-fund/operations"),
        ]);
        if (disposed) return;
        setOverview(nextOverview);
        setOperations(nextOperations);
        setConnected(true);
        setError(null);
      } catch (err) {
        if (disposed) return;
        setConnected(false);
        setError(err instanceof Error ? err.message : "Cortex telemetry unavailable");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 2_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSelectedCaseId(window.localStorage.getItem(ACTIVE_CASE_KEY));
    }, 750);
    return () => window.clearInterval(timer);
  }, []);

  const events = useMemo(() => {
    return [...(overview?.factory.activity.recent_events ?? [])].sort((a, b) => {
      return (parseTime(b.created_at) ?? 0) - (parseTime(a.created_at) ?? 0);
    });
  }, [overview]);

  const latestAgentEvents = useMemo(() => {
    const lookup = new Map<string, CortexEvent>();
    for (const event of events) {
      const key = String(event.payload?.agent_key || "").trim();
      if (key && !lookup.has(key)) lookup.set(key, event);
    }
    return lookup;
  }, [events]);

  const activeWorkEvent = useMemo(() => {
    return events.find((event) => {
      const type = normalized(event.event_type);
      const age = ageSeconds(event, now);
      return (
        age <= ACTIVE_WINDOW_SECONDS &&
        (type === "AGENT_STARTED" || type === "COMMITTEE_STARTED")
      );
    });
  }, [events, now]);

  const recentWorkEvent = useMemo(() => {
    return events.find((event) => {
      const type = normalized(event.event_type);
      const age = ageSeconds(event, now);
      return (
        age <= RECENT_WINDOW_SECONDS &&
        (type.includes("AGENT_") ||
          type.includes("COMMITTEE") ||
          type.includes("ORCHESTRATION") ||
          type.includes("RISK") ||
          type.includes("CAPITAL") ||
          type.includes("PAPER"))
      );
    });
  }, [events, now]);

  const objectiveCaseId =
    activeWorkEvent?.case_id ??
    recentWorkEvent?.case_id ??
    operations?.latest_deepened_case?.case_id ??
    operations?.observation.latest_promoted_case?.case_id ??
    selectedCaseId ??
    overview?.cases[0]?.case_id ??
    null;

  const objectiveCase =
    overview?.cases.find((row) => row.case_id === objectiveCaseId) ?? null;

  const objectiveTicker =
    objectiveCase?.ticker ??
    operations?.latest_deepened_case?.ticker ??
    operations?.observation.latest_promoted_case?.ticker ??
    caseTicker(selectedCaseId, overview?.cases ?? []) ??
    "NO CASE";

  const objectiveTopic =
    objectiveCase?.topic ??
    operations?.latest_deepened_case?.topic ??
    "Waiting for the next governed objective.";

  const workerOnline =
    normalized(operations?.observation.cadence_state) === "ON_CADENCE" ||
    normalized(operations?.paper_trading.cadence_state) === "ON_CADENCE";

  const systemOnline = connected && workerOnline;

  const agentStates = useMemo(() => {
    const result = new Map<string, NodeState>();
    for (const agent of AGENTS) {
      const event = latestAgentEvents.get(agent.key);
      if (!connected) {
        result.set(agent.key, "offline");
        continue;
      }
      if (!event) {
        result.set(agent.key, "idle");
        continue;
      }
      const type = normalized(event.event_type);
      const age = ageSeconds(event, now);
      if (type === "AGENT_STARTED" && age <= ACTIVE_WINDOW_SECONDS) {
        result.set(agent.key, "working");
      } else if (type.includes("FAILED") && age <= ACTIVE_WINDOW_SECONDS) {
        result.set(agent.key, "blocked");
      } else if (type === "AGENT_COMPLETE" && age <= RECENT_WINDOW_SECONDS) {
        result.set(agent.key, "recent");
      } else {
        result.set(agent.key, "idle");
      }
    }
    return result;
  }, [connected, latestAgentEvents, now]);

  const workingCount = [...agentStates.values()].filter(
    (state) => state === "working",
  ).length;
  const recentCount = [...agentStates.values()].filter(
    (state) => state === "recent",
  ).length;

  const committeeEvent = events.find((event) => {
    const type = normalized(event.event_type);
    return type.includes("COMMITTEE") || type.includes("ORCHESTRATION_COMPLETE");
  });
  const riskEvent = events.find((event) => normalized(event.event_type).includes("RISK"));
  const capitalEvent = events.find((event) => {
    const type = normalized(event.event_type);
    return (
      type.includes("CAPITAL") ||
      type.includes("POSITION_SIZ") ||
      type.includes("AUTHORIZATION")
    );
  });
  const paperEvent = events.find((event) => normalized(event.event_type).includes("PAPER"));

  const systemStates: Record<string, NodeState> = {
    committee: connected
      ? systemState(committeeEvent, now, objectiveCase?.committee)
      : "offline",
    risk: connected ? systemState(riskEvent, now, objectiveCase?.risk) : "offline",
    capital: connected
      ? systemState(capitalEvent, now, objectiveCase?.capital)
      : "offline",
    paper: connected
      ? systemState(paperEvent, now, objectiveCase?.paper_execution)
      : "offline",
  };

  const mode = !connected
    ? "OFFLINE"
    : workingCount > 0 || normalized(committeeEvent?.event_type) === "COMMITTEE_STARTED"
      ? "THINKING"
      : recentCount > 0 || recentWorkEvent
        ? "SIGNAL FLOW"
        : systemOnline
          ? "ENGINE IDLE"
          : "STANDBY";

  const nodeState = (key: string): NodeState => {
    if (key === "objective") return systemOnline ? "recent" : connected ? "idle" : "offline";
    return agentStates.get(key) ?? systemStates[key] ?? "idle";
  };

  const linkState = (link: LinkSpec): NodeState => {
    const from = nodeState(link.from);
    const to = nodeState(link.to);
    if (from === "blocked" || to === "blocked") return "blocked";
    if (from === "working" || to === "working") return "working";
    if (from === "recent" || to === "recent") return "recent";
    if (!connected) return "offline";
    return "idle";
  };

  const activityTape = events.filter((event) => ageSeconds(event, now) <= ACTIVE_WINDOW_SECONDS).slice(0, 5);

  return (
    <aside className={`fnc-shell ${open ? "open" : "closed"} mode-${mode.replaceAll(" ", "-").toLowerCase()}`}>
      <button
        type="button"
        className="fnc-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span>THE FAMILY NETWORK</span>
        <strong>{mode}</strong>
        <em>{open ? "HIDE CORTEX" : objectiveTicker}</em>
      </button>

      {open ? (
        <div className="fnc-panel">
          <header className="fnc-head">
            <div>
              <span>LIVE AGENT CORTEX · FAMILY BUSINESS</span>
              <h2>The Family Network</h2>
              <p>
                The motor breathes while IIOS is online. Bright signal packets only move when governed ledger activity says work is happening.
              </p>
            </div>
            <div className={`fnc-mode ${systemOnline ? "online" : "offline"}`}>
              <i />
              <strong>{mode}</strong>
              <span>{workingCount} WORKING · {recentCount} JUST FINISHED</span>
            </div>
          </header>

          <div className="fnc-objective-strip">
            <div>
              <span>CURRENT OBJECTIVE</span>
              <strong>{objectiveTicker}</strong>
              <em>{objectiveTopic}</em>
            </div>
            <div>
              <span>OPERATING CLOCK</span>
              <strong>{normalized(operations?.paper_trading.market_phase).replaceAll("_", " ")}</strong>
              <em>{operations?.paper_trading.paper_execution_window_open ? "PAPER WINDOW OPEN" : "PAPER WINDOW CLOSED"}</em>
            </div>
          </div>

          <div className="fnc-cortex-wrap">
            <svg
              className="fnc-cortex"
              viewBox="0 0 520 390"
              role="img"
              aria-label="Live IIOS agent network telemetry"
            >
              <defs>
                <filter id="fncGlow" x="-80%" y="-80%" width="260%" height="260%">
                  <feGaussianBlur stdDeviation="4" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <linearGradient id="fncBrainStroke" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#a77b42" />
                  <stop offset="45%" stopColor="#42d9e8" />
                  <stop offset="100%" stopColor="#713645" />
                </linearGradient>
              </defs>

              <path
                className={`fnc-brain-outline ${systemOnline ? "online" : "offline"}`}
                d="M252 33 C195 13 137 29 105 72 C51 79 34 124 57 161 C31 201 54 242 101 249 C107 302 157 324 207 298 C228 326 247 326 260 308 C273 326 292 326 313 298 C363 324 413 302 419 249 C466 242 489 201 463 161 C486 124 469 79 415 72 C383 29 325 13 268 33"
              />
              <path
                className={`fnc-brain-midline ${systemOnline ? "online" : "offline"}`}
                d="M260 40 C246 82 274 104 257 139 C244 167 270 188 257 218 C245 245 272 266 260 304"
              />

              {LINKS.map((link) => {
                const state = linkState(link);
                const moving = state === "working" || state === "recent";
                return (
                  <g key={link.id}>
                    <path className={`fnc-link ${state}`} d={link.d} />
                    {moving ? (
                      <circle className={`fnc-packet ${state}`} r={state === "working" ? 3.3 : 2.5}>
                        <animateMotion
                          dur={state === "working" ? "1.25s" : "2.6s"}
                          repeatCount="indefinite"
                          path={link.d}
                        />
                      </circle>
                    ) : null}
                  </g>
                );
              })}

              <g className={`fnc-objective-node ${nodeState("objective")}`} transform="translate(260 165)">
                <circle className="fnc-node-halo" r="50" />
                <circle className="fnc-node-core" r="38" />
                <circle className="fnc-rotor" r="45" />
                <text className="fnc-node-kicker" textAnchor="middle" y="-12">BOSS'S OFFICE</text>
                <text className="fnc-node-main" textAnchor="middle" y="5">{objectiveTicker}</text>
                <text className="fnc-node-sub" textAnchor="middle" y="21">OBJECTIVE HUB</text>
              </g>

              {AGENTS.map((agent) => {
                const state = agentStates.get(agent.key) ?? "idle";
                const latest = latestAgentEvents.get(agent.key);
                return (
                  <g
                    className={`fnc-agent-node ${state}`}
                    transform={`translate(${agent.x} ${agent.y})`}
                    key={agent.key}
                  >
                    <title>{agent.canonical} · {eventLabel(latest ?? {})}</title>
                    <circle className="fnc-node-halo" r="26" />
                    <circle className="fnc-node-core" r="19" />
                    <text className="fnc-agent-alias" textAnchor="middle" y="-2">{agent.alias}</text>
                    <text className="fnc-agent-state" textAnchor="middle" y="11">
                      {state === "working" ? "WORKING" : state === "recent" ? "DONE" : state === "blocked" ? "BLOCKED" : "ARMED"}
                    </text>
                  </g>
                );
              })}

              <g className={`fnc-system-node committee ${systemStates.committee}`} transform="translate(260 338)">
                <circle className="fnc-node-halo" r="26" />
                <circle className="fnc-node-core" r="19" />
                <text className="fnc-agent-alias" textAnchor="middle" y="-2">THE SIT-DOWN</text>
                <text className="fnc-agent-state" textAnchor="middle" y="11">COMMITTEE</text>
              </g>
              <g className={`fnc-system-node risk ${systemStates.risk}`} transform="translate(355 354)">
                <circle className="fnc-node-halo" r="24" />
                <circle className="fnc-node-core" r="17" />
                <text className="fnc-agent-alias" textAnchor="middle" y="-2">THE GATE</text>
                <text className="fnc-agent-state" textAnchor="middle" y="11">RISK</text>
              </g>
              <g className={`fnc-system-node capital ${systemStates.capital}`} transform="translate(430 338)">
                <circle className="fnc-node-halo" r="24" />
                <circle className="fnc-node-core" r="17" />
                <text className="fnc-agent-alias" textAnchor="middle" y="-2">THE VAULT</text>
                <text className="fnc-agent-state" textAnchor="middle" y="11">CAPITAL</text>
              </g>
              <g className={`fnc-system-node paper ${systemStates.paper}`} transform="translate(490 302)">
                <circle className="fnc-node-halo" r="22" />
                <circle className="fnc-node-core" r="15" />
                <text className="fnc-agent-alias" textAnchor="middle" y="-2">THE BOOK</text>
                <text className="fnc-agent-state" textAnchor="middle" y="11">PAPER</text>
              </g>
            </svg>

            <div className="fnc-legend">
              <span><i className="working" /> WORKING</span>
              <span><i className="recent" /> JUST FINISHED</span>
              <span><i className="blocked" /> BLOCK / VETO</span>
              <span><i className="idle" /> ARMED / IDLE</span>
            </div>
          </div>

          <div className="fnc-tape">
            <div className="fnc-tape-head">
              <span>FAMILY WIRE</span>
              <strong>{overview?.factory.activity.recent_event_count ?? 0} EVENTS / 5 MIN</strong>
            </div>
            <div className="fnc-tape-lines">
              {activityTape.map((event, index) => {
                const key = String(event.payload?.agent_key || "");
                const alias = AGENTS.find((agent) => agent.key === key)?.alias;
                const ticker = caseTicker(event.case_id ?? null, overview?.cases ?? []);
                return (
                  <div className="fnc-tape-row" key={`${event.created_at}-${index}`}>
                    <span>{event.created_at ? new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"}</span>
                    <strong>{alias ?? event.room ?? "SYSTEM"}</strong>
                    <em>{eventLabel(event)}</em>
                    <b>{ticker ?? "—"}</b>
                  </div>
                );
              })}
              {activityTape.length === 0 ? (
                <div className="fnc-tape-empty">
                  Engine online. No governed desk event has fired inside the current telemetry window.
                </div>
              ) : null}
            </div>
          </div>

          {error ? <div className="fnc-error">{error}</div> : null}

          <footer className="fnc-footer">
            <span>MOTION FOLLOWS LEDGER EVENTS · NO FAKE BUSY STATES</span>
            <strong>COMMITTEE · RISK · CAPITAL REMAIN AUTHORITATIVE</strong>
          </footer>
        </div>
      ) : null}
    </aside>
  );
}

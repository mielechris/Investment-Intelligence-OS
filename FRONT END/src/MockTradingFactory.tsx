import { useEffect, useMemo, useState } from "react";
import { AGENT_VISUAL_CONTRACTS } from "./agentVisualContracts";
import "./MockTradingFactory.css";

type MockStage = "RADAR" | "RESEARCH" | "COMMITTEE" | "RISK" | "PAPER" | "REVIEW";

type MockCase = {
  ticker: string;
  score: number;
  catalyst: string;
  stage: MockStage;
  decision: "WATCH" | "PROMOTE" | "NO TRADE" | "MOCK BUY" | "MOCK SELL";
  checks: Array<{ label: string; state: "PASS" | "WARN" | "FAIL" | "PENDING" }>;
};

const STAGES: MockStage[] = ["RADAR", "RESEARCH", "COMMITTEE", "RISK", "PAPER", "REVIEW"];
const CASES: MockCase[] = [
  {
    ticker: "NVDA",
    score: 86,
    catalyst: "Earnings / AI demand / abnormal volume",
    stage: "RADAR",
    decision: "WATCH",
    checks: [
      { label: "Catalyst", state: "PASS" },
      { label: "Volume", state: "PASS" },
      { label: "Breadth", state: "WARN" },
      { label: "Entry quality", state: "PENDING" },
    ],
  },
  {
    ticker: "AVGO",
    score: 78,
    catalyst: "Semiconductor read-through / policy conflict",
    stage: "RESEARCH",
    decision: "NO TRADE",
    checks: [
      { label: "Sector", state: "PASS" },
      { label: "Momentum", state: "PASS" },
      { label: "Policy risk", state: "WARN" },
      { label: "Risk gate", state: "FAIL" },
    ],
  },
  {
    ticker: "SPY",
    score: 74,
    catalyst: "Index strength / narrow leadership",
    stage: "COMMITTEE",
    decision: "PROMOTE",
    checks: [
      { label: "Price", state: "PASS" },
      { label: "Breadth", state: "WARN" },
      { label: "Regime", state: "PASS" },
      { label: "Committee", state: "PENDING" },
    ],
  },
  {
    ticker: "CRM",
    score: 72,
    catalyst: "Company-specific earnings catalyst",
    stage: "RISK",
    decision: "MOCK BUY",
    checks: [
      { label: "Catalyst", state: "PASS" },
      { label: "Evidence", state: "PASS" },
      { label: "Committee", state: "PASS" },
      { label: "Risk", state: "PASS" },
    ],
  },
];

function checkMark(state: MockCase["checks"][number]["state"]) {
  if (state === "PASS") return "✅";
  if (state === "WARN") return "⚠️";
  if (state === "FAIL") return "❌";
  return "⏳";
}

export default function MockTradingFactory() {
  const [tick, setTick] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const timer = window.setInterval(() => setTick((value) => value + 1), 2200);
    return () => window.clearInterval(timer);
  }, [paused]);

  const stageIndex = tick % STAGES.length;
  const movingCase = CASES[tick % CASES.length];
  const activeStage = STAGES[stageIndex];
  const activeAgent = AGENT_VISUAL_CONTRACTS[tick % AGENT_VISUAL_CONTRACTS.length];
  const mockNav = 10000 + ((tick % 9) - 3) * 11.5;
  const mockPnl = mockNav - 10000;

  const maxLine = useMemo(() => {
    const lines = [
      "MAX says: nobody touches real money. Keep the theater in its lane.",
      `MAX says: ${activeAgent.maxReaction}`,
      "MAX says: mock trades can be loud. Governance stays boring on purpose.",
      "MAX says: if the data is fake, the label better scream MOCK.",
    ];
    return lines[tick % lines.length];
  }, [activeAgent.maxReaction, tick]);

  return (
    <section className="mock-factory" aria-label="IIOS mock trading factory">
      <header className="mock-factory__header">
        <div>
          <span className="mock-factory__eyebrow">X3 · FACTORY THEATER</span>
          <h2>THE MOB FLOOR · MOCK TRADING MODE</h2>
          <p>Animated demonstration only. No mock event can enter the real ledger, Committee, Risk, paper portfolio, broker path, or learning history.</p>
        </div>
        <div className="mock-factory__lock">
          <strong>MOCK / DEMO</strong>
          <span>REAL ENGINE ISOLATED</span>
          <span>LIVE CAPITAL LOCKED</span>
        </div>
      </header>

      <div className="mock-factory__toolbar">
        <button type="button" onClick={() => setPaused((value) => !value)}>{paused ? "RESUME FLOOR" : "PAUSE FLOOR"}</button>
        <span>SCENE {tick + 1}</span>
        <span>ACTIVE ROOM · {activeStage}</span>
        <span>ACTIVE DESK · {activeAgent.floorTitle}</span>
      </div>

      <div className="mock-factory__grid">
        <aside className="mock-factory__max">
          <div className="mock-factory__portrait">MAX</div>
          <h3>MAX · FLOOR BOSS</h3>
          <p>{maxLine}</p>
          <div className="mock-factory__metrics">
            <span>MOCK NAV <b>${mockNav.toFixed(2)}</b></span>
            <span>MOCK P&L <b>{mockPnl >= 0 ? "+" : ""}${mockPnl.toFixed(2)}</b></span>
            <span>REAL ORDERS <b>0</b></span>
          </div>
        </aside>

        <main className="mock-factory__floor">
          <div className="mock-factory__rooms">
            {STAGES.map((stage) => (
              <div key={stage} className={`mock-room ${stage === activeStage ? "mock-room--active" : ""}`}>
                <span>{stage}</span>
                <small>{stage === activeStage ? `${movingCase.ticker} IN ROOM` : "STANDBY"}</small>
              </div>
            ))}
          </div>

          <div className="mock-factory__case-card">
            <div className="mock-factory__case-head">
              <div><span>CURRENT MOCK CASE</span><strong>{movingCase.ticker}</strong></div>
              <div><span>RADAR SCORE</span><strong>{movingCase.score}</strong></div>
              <div><span>DISPOSITION</span><strong>{movingCase.decision}</strong></div>
            </div>
            <p><b>WHY IT SURFACED:</b> {movingCase.catalyst}</p>
            <div className="mock-factory__checks">
              {movingCase.checks.map((item) => (
                <span key={item.label}>{checkMark(item.state)} {item.label}</span>
              ))}
            </div>
            <div className="mock-factory__handoff">MAX → {activeAgent.floorTitle} → {activeStage}</div>
          </div>

          <div className="mock-factory__desks">
            {AGENT_VISUAL_CONTRACTS.map((agent) => {
              const active = agent.key === activeAgent.key;
              return (
                <div key={agent.key} className={`mock-desk ${active ? "mock-desk--active" : ""}`}>
                  <strong>{agent.floorTitle}</strong>
                  <span>{agent.characterArchetype}</span>
                  <small>{active ? "WORKING MOCK CASE" : "WAITING"}</small>
                </div>
              );
            })}
          </div>
        </main>
      </div>

      <footer className="mock-factory__footer">
        <b>MOCK DATA NEVER BECOMES REAL TELEMETRY.</b>
        <span>The real IIOS engine continues separately in governed paper mode.</span>
      </footer>
    </section>
  );
}

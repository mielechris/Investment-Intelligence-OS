export type AgentVisualContract = {
  key: string;
  backendName: string;
  backendRoom: string;
  floorTitle: string;
  characterArchetype: string;
  visualProps: string[];
  activeBehavior: string;
  maxReaction: string;
};

export const AGENT_VISUAL_CONTRACTS: AgentVisualContract[] = [
  {
    key: "policy",
    backendName: "Policy Analyst",
    backendRoom: "Policy Floor",
    floorTitle: "POLICY DESK",
    characterArchetype: "The fixer who reads Washington before the room does.",
    visualProps: ["policy binders", "executive-order board", "tariff map", "government terminal"],
    activeBehavior: "Desk lamp turns on and policy documents populate only while real policy analysis is active.",
    maxReaction: "Washington moved. Read the fine print before you celebrate.",
  },
  {
    key: "macro",
    backendName: "Macro & Rates Analyst",
    backendRoom: "Macro Desk",
    floorTitle: "MACRO & RATES",
    characterArchetype: "The rates bookie who always knows what the market is pricing.",
    visualProps: ["yield curve wall", "Fed probability board", "dollar tape", "liquidity gauges"],
    activeBehavior: "Yield and regime panels illuminate only from current macro telemetry.",
    maxReaction: "Everybody's a genius until rates change the rules.",
  },
  {
    key: "fundamentals",
    backendName: "Fundamentals Analyst",
    backendRoom: "Fundamentals Lab",
    floorTitle: "FUNDAMENTALS LAB",
    characterArchetype: "The accountant with a baseball bat for bad assumptions.",
    visualProps: ["filing stacks", "margin bridge", "valuation board", "balance-sheet ledger"],
    activeBehavior: "Filings and valuation cards appear only when governed company evidence is present.",
    maxReaction: "Nice story. Show me the cash flow.",
  },
  {
    key: "market_structure",
    backendName: "Market Structure Analyst",
    backendRoom: "Tape & Positioning",
    floorTitle: "TAPE & POSITIONING",
    characterArchetype: "The street operator watching who is trapped, crowded, or late.",
    visualProps: ["tape wall", "positioning board", "volatility monitor", "flow blotter"],
    activeBehavior: "Tape and flow effects activate only when market-structure inputs exist.",
    maxReaction: "Great thesis. Shame everybody already owns it.",
  },
  {
    key: "commodities",
    backendName: "Commodities & Supply Chain Analyst",
    backendRoom: "Physical Markets",
    floorTitle: "PHYSICAL MARKETS",
    characterArchetype: "The procurement shark who cares where the actual stuff is.",
    visualProps: ["commodity board", "freight map", "inventory gauges", "seasonality calendar"],
    activeBehavior: "Physical-market indicators react to real supply, inventory, weather, freight, or commodity evidence.",
    maxReaction: "Paper says plenty. The warehouse says otherwise.",
  },
  {
    key: "geo_weather",
    backendName: "Geopolitics & Weather Analyst",
    backendRoom: "Global Events Room",
    floorTitle: "GLOBAL EVENTS",
    characterArchetype: "The crisis-room operator who separates real shocks from cable-news panic.",
    visualProps: ["world situation map", "weather radar", "shipping chokepoints", "event timeline"],
    activeBehavior: "Maps and alerts light only for confirmed governed events or explicit scenario states.",
    maxReaction: "Headline's loud. Evidence better be louder.",
  },
  {
    key: "skeptic",
    backendName: "Skeptic / Red Team",
    backendRoom: "Red Team",
    floorTitle: "SKEPTIC / RED ROOM",
    characterArchetype: "The consigliere whose job is to ruin the pitch before the market does.",
    visualProps: ["red dossier", "falsifier wall", "missing-evidence board", "contradiction file"],
    activeBehavior: "Red Room activates only when a real skeptic result, challenge, or evidence gap exists.",
    maxReaction: "You want applause, call your mother. I want the hole in the thesis.",
  },
  {
    key: "portfolio",
    backendName: "Portfolio Context Analyst",
    backendRoom: "Portfolio Control",
    floorTitle: "PORTFOLIO CONTROL",
    characterArchetype: "The boss at the door deciding whether a good idea belongs in this book.",
    visualProps: ["exposure board", "correlation map", "drawdown monitor", "opportunity-cost ledger"],
    activeBehavior: "Portfolio overlays appear only from real paper-portfolio context; no position is implied from an idea alone.",
    maxReaction: "Good trade isn't the same thing as a good seat at this table.",
  },
];

export function agentVisualContract(key: string) {
  return AGENT_VISUAL_CONTRACTS.find((contract) => contract.key === key) ?? null;
}

export type AgentVisualContract = {
  key: string;
  backendName: string;
  backendRoom: string;
  floorTitle: string;
  characterArchetype: string;
  visualProps: string[];
  activeBehavior: string;
  maxReaction: string;
  mobAlias?: string;
  crewRole?: string;
  workingLine?: string;
  warningLine?: string;
  clearedLine?: string;
};

export const AGENT_VISUAL_CONTRACTS: AgentVisualContract[] = [
  {
    key: "policy",
    backendName: "Policy Analyst",
    backendRoom: "Policy Floor",
    floorTitle: "POLICY DESK",
    mobAlias: "THE FIXER",
    crewRole: "Washington intelligence",
    characterArchetype: "The fixer who reads Washington before the room does.",
    visualProps: ["policy binders", "executive-order board", "tariff map", "government terminal"],
    activeBehavior: "Desk lamp turns on and policy documents populate only while real policy analysis is active.",
    maxReaction: "Washington moved. Read the fine print before you celebrate.",
    workingLine: "I got Washington on the phone. Nobody move until I read the fine print.",
    warningLine: "Headline sounds clean. The footnotes usually carry the knife.",
    clearedLine: "Policy angle checked. Send the file upstairs.",
  },
  {
    key: "macro",
    backendName: "Macro & Rates Analyst",
    backendRoom: "Macro Desk",
    floorTitle: "MACRO & RATES",
    mobAlias: "THE BOOKIE",
    crewRole: "Rates and liquidity",
    characterArchetype: "The rates bookie who always knows what the market is pricing.",
    visualProps: ["yield curve wall", "Fed probability board", "dollar tape", "liquidity gauges"],
    activeBehavior: "Yield and regime panels illuminate only from current macro telemetry.",
    maxReaction: "Everybody's a genius until rates change the rules.",
    workingLine: "The tape can lie. The price of money eventually collects.",
    warningLine: "Rates just changed the odds. Reprice the whole damn table.",
    clearedLine: "Macro book balanced. Move it.",
  },
  {
    key: "fundamentals",
    backendName: "Fundamentals Analyst",
    backendRoom: "Fundamentals Lab",
    floorTitle: "FUNDAMENTALS LAB",
    mobAlias: "THE ACCOUNTANT",
    crewRole: "Cash flow and valuation",
    characterArchetype: "The accountant with a baseball bat for bad assumptions.",
    visualProps: ["filing stacks", "margin bridge", "valuation board", "balance-sheet ledger"],
    activeBehavior: "Filings and valuation cards appear only when governed company evidence is present.",
    maxReaction: "Nice story. Show me the cash flow.",
    workingLine: "Bring me the filings. Stories don't pay invoices.",
    warningLine: "Somebody's valuation math smells like a trunk in July.",
    clearedLine: "Numbers reconcile. The story earned another room.",
  },
  {
    key: "market_structure",
    backendName: "Market Structure Analyst",
    backendRoom: "Tape & Positioning",
    floorTitle: "TAPE & POSITIONING",
    mobAlias: "THE TAPE MAN",
    crewRole: "Flow and positioning",
    characterArchetype: "The street operator watching who is trapped, crowded, or late.",
    visualProps: ["tape wall", "positioning board", "volatility monitor", "flow blotter"],
    activeBehavior: "Tape and flow effects activate only when market-structure inputs exist.",
    maxReaction: "Great thesis. Shame everybody already owns it.",
    workingLine: "I'm watching who is trapped, crowded, and about to puke.",
    warningLine: "Crowded trade. One bad print and everybody uses the same exit.",
    clearedLine: "Positioning is survivable. Pass it down the hall.",
  },
  {
    key: "commodities",
    backendName: "Commodities & Supply Chain Analyst",
    backendRoom: "Physical Markets",
    floorTitle: "PHYSICAL MARKETS",
    mobAlias: "THE SUPPLIER",
    crewRole: "Physical supply and commodities",
    characterArchetype: "The procurement shark who cares where the actual stuff is.",
    visualProps: ["commodity board", "freight map", "inventory gauges", "seasonality calendar"],
    activeBehavior: "Physical-market indicators react to real supply, inventory, weather, freight, or commodity evidence.",
    maxReaction: "Paper says plenty. The warehouse says otherwise.",
    workingLine: "Forget the spreadsheet. Tell me what's actually on the truck.",
    warningLine: "Supply says one thing. Price says another. Somebody's bluffing.",
    clearedLine: "Physical market checks out. Keep the file moving.",
  },
  {
    key: "geo_weather",
    backendName: "Geopolitics & Weather Analyst",
    backendRoom: "Global Events Room",
    floorTitle: "GLOBAL EVENTS",
    mobAlias: "THE SCOUT",
    crewRole: "Geopolitics and weather",
    characterArchetype: "The crisis-room operator who separates real shocks from cable-news panic.",
    visualProps: ["world situation map", "weather radar", "shipping chokepoints", "event timeline"],
    activeBehavior: "Maps and alerts light only for confirmed governed events or explicit scenario states.",
    maxReaction: "Headline's loud. Evidence better be louder.",
    workingLine: "I'm checking whether the world actually moved or cable TV just got excited.",
    warningLine: "Real shock. Chokepoint is live. Don't treat this like background noise.",
    clearedLine: "Event risk classified. Send it.",
  },
  {
    key: "skeptic",
    backendName: "Skeptic / Red Team",
    backendRoom: "Red Team",
    floorTitle: "SKEPTIC / RED ROOM",
    mobAlias: "THE CONSIGLIERE",
    crewRole: "Falsification and contradiction",
    characterArchetype: "The consigliere whose job is to ruin the pitch before the market does.",
    visualProps: ["red dossier", "falsifier wall", "missing-evidence board", "contradiction file"],
    activeBehavior: "Red Room activates only when a real skeptic result, challenge, or evidence gap exists.",
    maxReaction: "You want applause, call your mother. I want the hole in the thesis.",
    workingLine: "Everybody shut up. I'm trying to kill the idea before the market does.",
    warningLine: "Found the hole. It's not cute. Fix it or bury the trade.",
    clearedLine: "I tried to kill it. It survived. That's useful.",
  },
  {
    key: "portfolio",
    backendName: "Portfolio Context Analyst",
    backendRoom: "Portfolio Control",
    floorTitle: "PORTFOLIO CONTROL",
    mobAlias: "THE TREASURER",
    crewRole: "Exposure and capital fit",
    characterArchetype: "The boss at the door deciding whether a good idea belongs in this book.",
    visualProps: ["exposure board", "correlation map", "drawdown monitor", "opportunity-cost ledger"],
    activeBehavior: "Portfolio overlays appear only from real paper-portfolio context; no position is implied from an idea alone.",
    maxReaction: "Good trade isn't the same thing as a good seat at this table.",
    workingLine: "I don't care if it's good. I care whether it belongs in this book.",
    warningLine: "Nice idea. Wrong seat, wrong size, wrong time.",
    clearedLine: "Capital fit is clean. Let the bosses decide.",
  },
];

export function agentVisualContract(key: string) {
  return AGENT_VISUAL_CONTRACTS.find((contract) => contract.key === key) ?? null;
}

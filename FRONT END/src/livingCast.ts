export type LivingCastKey =
  | "max"
  | "policy"
  | "macro"
  | "fundamentals"
  | "market_structure"
  | "commodities"
  | "geo_weather"
  | "skeptic"
  | "portfolio";

export type LivingCastMember = {
  key: LivingCastKey;
  displayName: string;
  governedRole: string;
  title: string;
  monogram: string;
  workstation: string;
  personaLine: string;
};

export const LIVING_CAST: Record<LivingCastKey, LivingCastMember> = {
  max: {
    key: "max",
    displayName: "MAX",
    governedRole: "Factory Foreman",
    title: "The Foreman",
    monogram: "M",
    workstation: "Command Overlook",
    personaLine: "Evidence first. Bullshit gets thrown in the dumpster.",
  },
  policy: {
    key: "policy",
    displayName: "Frankie Fine Print",
    governedRole: "Policy Analyst",
    title: "Regulatory Bloodhound",
    monogram: "PA",
    workstation: "Policy binders · EO board · tariff map",
    personaLine: "Fine print's where the bodies are buried.",
  },
  macro: {
    key: "macro",
    displayName: "Benny Basis Points",
    governedRole: "Macro & Rates Analyst",
    title: "Regime Obsessive",
    monogram: "MR",
    workstation: "Yield curve · Fed board · dollar tape",
    personaLine: "Everybody's a genius until rates change the rules.",
  },
  fundamentals: {
    key: "fundamentals",
    displayName: "Vinny EBITDA",
    governedRole: "Fundamentals Analyst",
    title: "Numbers Before Vibes",
    monogram: "FA",
    workstation: "Filings · margin bridge · valuation ledger",
    personaLine: "Great story. Where the fuck is the cash flow?",
  },
  market_structure: {
    key: "market_structure",
    displayName: "Mikey Tape",
    governedRole: "Market Structure Analyst",
    title: "Tape Reader",
    monogram: "MS",
    workstation: "Tape wall · flow board · volatility monitor",
    personaLine: "Somebody's trapped. I just wanna know who.",
  },
  commodities: {
    key: "commodities",
    displayName: "Tony Tanker",
    governedRole: "Commodities & Supply Chain Analyst",
    title: "Physical-World Realist",
    monogram: "CS",
    workstation: "Commodities · freight · inventory",
    personaLine: "Spreadsheet says plenty. Warehouse says otherwise.",
  },
  geo_weather: {
    key: "geo_weather",
    displayName: "Stormy Sal",
    governedRole: "Geopolitics & Weather Analyst",
    title: "Scenario Disciplinarian",
    monogram: "GW",
    workstation: "World map · weather · chokepoints",
    personaLine: "Headline's loud. Evidence better be louder.",
  },
  skeptic: {
    key: "skeptic",
    displayName: "Johnny No",
    governedRole: "Skeptic / Red Team",
    title: "Professional Buzzkill",
    monogram: "RT",
    workstation: "Red dossier · falsifiers · contradictions",
    personaLine: "Cute thesis. Now tell me how it dies.",
  },
  portfolio: {
    key: "portfolio",
    displayName: "Paulie Positions",
    governedRole: "Portfolio Context Analyst",
    title: "Risk-Adjusted Adult",
    monogram: "PC",
    workstation: "Exposure · correlation · drawdown",
    personaLine: "Congratulations, genius. You still blew up the book.",
  },
};

export function castMember(key: string): LivingCastMember | null {
  return Object.prototype.hasOwnProperty.call(LIVING_CAST, key)
    ? LIVING_CAST[key as LivingCastKey]
    : null;
}

export function maxNarrativeForStation(station: string | null, eventType: string): string {
  const readable = eventType.replaceAll("_", " ");
  switch (station) {
    case "radar": return `Radar just kicked something upstairs: ${readable}. Everybody relax. A candidate is not a damn victory parade.`;
    case "research": return `Research has the file. ${readable}. Read the evidence before somebody falls in love with the headline.`;
    case "agents": return `The bullpen's working ${readable}. Keep the egos out of it and show me what survives the evidence.`;
    case "committee": return `Committee has it: ${readable}. This is where a cute idea either grows up or gets buried.`;
    case "risk": return `Risk just moved: ${readable}. Nobody gets clever with capital on my floor.`;
    case "paper": return `Paper bay event: ${readable}. Fake money, real discipline. Don't get cute.`;
    case "monitoring": return `Monitoring just barked: ${readable}. A thesis doesn't get tenure because we liked it yesterday.`;
    case "learning": return `Learning logged ${readable}. Good. If we don't learn, we're just expensive idiots with screens.`;
    default: return `Latest persisted event: ${readable}. Evidence first. Ego gets a folding chair.`;
  }
}

export function agentNarrativeForEvent(key: LivingCastKey, eventType: string): string {
  const readable = eventType.replaceAll("_", " ");
  switch (key) {
    case "policy": return `Frankie: ${readable}. Fine print first; victory lap never.`;
    case "macro": return `Benny: ${readable}. Cute. Now tell me what rates are pricing.`;
    case "fundamentals": return `Vinny: ${readable}. Great. Show me the cash flow.`;
    case "market_structure": return `Mikey: ${readable}. Somebody's leaning the wrong way.`;
    case "commodities": return `Tony: ${readable}. Check the physical market before the spreadsheet starts lying.`;
    case "geo_weather": return `Stormy Sal: ${readable}. Drama is cheap. Confirmed evidence isn't.`;
    case "skeptic": return `Johnny No: ${readable}. Beautiful. Now let's find the part that kills it.`;
    case "portfolio": return `Paulie: ${readable}. Being right doesn't excuse stupid sizing.`;
    default: return readable;
  }
}

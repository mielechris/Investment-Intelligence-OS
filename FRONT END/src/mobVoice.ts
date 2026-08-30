import type { LivingCastKey } from "./livingCast";

type MobVoiceContext = {
  eventType: string;
  ticker: string;
  disposition?: string;
  confidence?: string;
  riskDecision?: string;
  paperState?: string;
};

const generic: Record<LivingCastKey, string[]> = {
  max: [
    "Listen up, you beautiful degenerates. Evidence first, bullshit second, and if anybody touches live capital I bite.",
    "Nobody gets cute on my floor. Bring receipts or bring cannoli. Preferably both.",
    "I don't predict shit. I make you people explain the downside until the downside needs therapy.",
  ],
  policy: [
    "Ay, read the fuckin' footnotes. That's where they hide the body.",
    "Everybody loves the headline. I love page forty-seven where the bastard admits what it actually means.",
    "Fine print first. Victory lap later. Maybe never, capisce?",
  ],
  macro: [
    "Beautiful thesis. Now rates move fifty bips and your whole genius act needs a priest.",
    "The curve don't care about your feelings, paisan. Neither do I.",
    "Everybody's Warren Buffett till the Fed punches 'em in the mouth.",
  ],
  fundamentals: [
    "Great story. Where the fuck is the cash flow?",
    "You can romance the multiple all night. I'm still checking the damn margins.",
    "Numbers before vibes, sweetheart. This ain't community theater.",
  ],
  market_structure: [
    "Somebody's trapped. I just wanna know which poor bastard it is.",
    "Tape's talkin'. Half this room's too busy hearing themselves speak.",
    "Flow first. Fairy tales after lunch.",
  ],
  commodities: [
    "Spreadsheet says plenty. Warehouse says you're full of shit.",
    "Go look at the physical market before some asshole in Excel invents abundance.",
    "Freight, inventory, weather. Real stuff. Not whatever this PowerPoint says.",
  ],
  geo_weather: [
    "Headline's screaming. Evidence better scream louder.",
    "One storm, one chokepoint, one idiot with a missile and suddenly your base case needs a funeral.",
    "Scenario discipline, fellas. Mother Nature doesn't read your deck.",
  ],
  skeptic: [
    "Cute thesis. Now tell me how the son of a bitch dies.",
    "I don't hate the idea. I hate how much you idiots already love it.",
    "Bring me the falsifier or get the fuck outta my conference room.",
  ],
  portfolio: [
    "Congratulations, genius. You were right and still blew up the book.",
    "Sizing, correlation, drawdown. The three horsemen of shut-the-fuck-up-and-do-the-math.",
    "A good idea with stupid sizing is just a more expensive bad idea.",
  ],
};

function hash(value: string): number {
  let out = 0;
  for (let index = 0; index < value.length; index += 1) {
    out = (out * 31 + value.charCodeAt(index)) >>> 0;
  }
  return out;
}

function pick(key: LivingCastKey, seed: string): string {
  const lines = generic[key];
  return lines[hash(`${key}:${seed}`) % lines.length];
}

export function mobReactionLine(key: LivingCastKey, context: MobVoiceContext): string {
  const type = context.eventType.toUpperCase();
  const ticker = context.ticker || "this thing";

  if (key === "max") {
    if (type.includes("PROMOT")) return `${ticker} got kicked upstairs. Nobody pop champagne. A case number means we found more work, not a fuckin' trophy.`;
    if (type.includes("COMMITTEE") || type.includes("DECISION")) return `The Commission put ${ticker} on the record. Good. Now nobody rewrites history when this thing either prints or shits the bed.`;
    if (type.includes("RISK")) return `Risk spoke on ${ticker}. Capital rules beat charisma, capisce? Anybody argues, I eat their keyboard.`;
    if (type.includes("PAPER") || type.includes("EXECUTION")) return `${ticker} hit the paper bay. Fake money, real discipline. Don't get a hard-on and start thinking you're a trader.`;
    if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) return `${ticker} is in the confessional. Receipts out, egos down. Somebody's about to explain what the fuck we learned.`;
    if (type.includes("FAIL") || type.includes("ERROR") || type.includes("REJECT")) return `${ticker} coughed up a failure event. Label it right before one of you animals calls broken plumbing alpha.`;
  }

  if (type.includes("PROMOT")) {
    if (key === "market_structure") return `${ticker} made it off radar. Nice. Tape gets a closer look; nobody made the bastard a saint.`;
    if (key === "skeptic") return `${ticker} has a case number. Mazel tov. Now show me the quickest way this beautiful little shitbox dies.`;
  }

  if (type.includes("COMMITTEE") || type.includes("DECISION")) {
    if (key === "fundamentals") return `${ticker} got ${context.disposition ?? "a decision"}. Fine. Show me the cash flow that keeps this thing outta witness protection.`;
    if (key === "skeptic") return `${ticker} reached the Commission. Adorable. I want the assumption everybody's too emotionally constipated to kill.`;
    if (key === "portfolio") return `${ticker} confidence is ${context.confidence ?? "unreported"}. Wonderful. Sizing still answers to drawdown, not applause from you gavones.`;
  }

  if (type.includes("RISK")) {
    if (key === "portfolio") return `${ticker} risk says ${context.riskDecision ?? "unreported"}. Capital doesn't give a shit how charming the thesis was.`;
    if (key === "skeptic") return `${ticker} got ${context.riskDecision ?? "a risk decision"}. That's the record. Nobody negotiates with the screen because they fell in love.`;
  }

  if (type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) {
    if (key === "portfolio") return `${ticker} paper state is ${context.paperState ?? "unreported"}. Rehearsal means we can screw up without lighting real money on fire. Try to appreciate the luxury.`;
  }

  if (type.includes("MONITOR")) {
    if (key === "market_structure") return `${ticker} is in monitoring. Yesterday's thesis don't get tenure. Tape gets another fuckin' vote.`;
    if (key === "portfolio") return `${ticker} is still alive. Great. Keep watching exposure before victory disease spreads through the building.`;
  }

  if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) {
    if (key === "fundamentals") return `${ticker} finally brought receipts. Good. Memory beats the bullshit story everybody tells after the answer key shows up.`;
    if (key === "skeptic") return `Postmortem time on ${ticker}. Nobody edits the original thesis after seeing the fuckin' grade.`;
    if (key === "portfolio") return `${ticker} gets scored on decision quality and outcome separately. Luck doesn't get promoted to skill in this family.`;
  }

  return pick(key, `${context.eventType}:${ticker}`);
}

export function mobAmbientLine(key: LivingCastKey): string {
  return pick(key, `ambient:${key}`);
}

export function mobReplayBannerLine(ticker: string, eventType: string): string {
  const readable = eventType.replaceAll("_", " ").toUpperCase();
  return `REHEARSAL ONLY — we're replaying the real persisted ${readable} scene for ${ticker}. Nobody in this building gets to call this live, or MAX starts biting ankles.`;
}

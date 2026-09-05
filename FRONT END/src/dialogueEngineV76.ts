import type { LivingCastKey } from "./livingCast";

export type V76RoomKey =
  | "pit"
  | "war"
  | "bullpen"
  | "commission"
  | "risk"
  | "paper"
  | "monitoring"
  | "learning"
  | "max"
  | "unknown";

export type V76DialogueContext = {
  eventType: string;
  ticker: string;
  room?: V76RoomKey;
  disposition?: string;
  confidence?: string;
  riskDecision?: string;
  paperState?: string;
  continuityEventType?: string;
  seed?: string;
  previousSpeaker?: LivingCastKey | null;
  cast?: LivingCastKey[];
};

export type V76Personality = {
  displayName: string;
  archetype: string;
  cadence: string;
  obsessions: string[];
  signatureMoves: string[];
  neverSoundsLike: string[];
  profanity: "low" | "medium" | "high";
};

export type V76Relationship = {
  from: LivingCastKey;
  to: LivingCastKey;
  dynamic: string;
};

export const V76_PERSONALITY_BIBLE: Record<LivingCastKey, V76Personality> = {
  max: {
    displayName: "MAX",
    archetype: "Mob-boss factory foreman",
    cadence: "Short orders, irritated punchlines, closes the room with authority.",
    obsessions: ["receipts", "downside", "discipline", "no live-capital funny business"],
    signatureMoves: ["calls the room to order", "interrupts bullshit", "ends scenes with a family rule"],
    neverSoundsLike: ["a quant report", "a motivational speaker", "a fiduciary"],
    profanity: "high",
  },
  policy: {
    displayName: "Frankie Fine Print",
    archetype: "Regulatory consigliere",
    cadence: "Dry, precise, suspicious; sounds like he already read page forty-seven.",
    obsessions: ["footnotes", "effective dates", "exceptions", "regulatory language"],
    signatureMoves: ["finds the clause", "kills headline certainty", "asks what the rule actually permits"],
    neverSoundsLike: ["a macro strategist", "a cheerleader", "a headline summarizer"],
    profanity: "medium",
  },
  macro: {
    displayName: "Benny Basis Points",
    archetype: "Rates-obsessed regime worrier",
    cadence: "Fast, exasperated, talks in curves, bips and regime changes.",
    obsessions: ["rates", "curve", "dollar", "liquidity", "Fed regime"],
    signatureMoves: ["changes the discount rate", "asks what the curve is saying", "turns certainty into scenario math"],
    neverSoundsLike: ["a company accountant", "a tape reader", "a weather forecaster"],
    profanity: "medium",
  },
  fundamentals: {
    displayName: "Vinny EBITDA",
    archetype: "Cash-flow enforcer",
    cadence: "Blunt, skeptical of stories, constantly drags the room back to margins and cash.",
    obsessions: ["cash flow", "margins", "valuation", "earnings quality", "balance sheet"],
    signatureMoves: ["asks where the cash is", "attacks narrative multiples", "forces a margin bridge"],
    neverSoundsLike: ["a technical trader", "a policy lawyer", "a vibes merchant"],
    profanity: "high",
  },
  market_structure: {
    displayName: "Mikey Tape",
    archetype: "Tape-reading street operator",
    cadence: "Clipped, street-level, speaks in flow, positioning and trapped traders.",
    obsessions: ["flow", "liquidity", "positioning", "volatility", "trapped holders"],
    signatureMoves: ["finds who is trapped", "asks who has to trade", "separates price action from story"],
    neverSoundsLike: ["a long-form economist", "a policy analyst", "a valuation professor"],
    profanity: "medium",
  },
  commodities: {
    displayName: "Tony Tanker",
    archetype: "Physical-market bruiser",
    cadence: "Concrete, impatient with abstractions, talks freight, inventory and warehouses.",
    obsessions: ["inventory", "freight", "physical supply", "warehouses", "basis"],
    signatureMoves: ["checks the warehouse", "calls spreadsheet fantasy", "brings the room back to physical constraints"],
    neverSoundsLike: ["a software analyst", "a pure macro economist", "a PowerPoint consultant"],
    profanity: "high",
  },
  geo_weather: {
    displayName: "Stormy Sal",
    archetype: "Scenario prophet with a weather map",
    cadence: "Darkly amused, conditional, always sees the chokepoint nobody priced.",
    obsessions: ["weather", "war", "shipping lanes", "chokepoints", "scenario trees"],
    signatureMoves: ["adds the ugly scenario", "connects weather to supply", "asks what breaks first"],
    neverSoundsLike: ["a certainty machine", "a company CFO", "a day-trader hype account"],
    profanity: "medium",
  },
  skeptic: {
    displayName: "Johnny No",
    archetype: "Thesis assassin",
    cadence: "Sharp interruption, sarcastic, hostile to beloved assumptions.",
    obsessions: ["falsifiers", "contradictions", "base-rate failure", "hidden assumptions"],
    signatureMoves: ["asks how it dies", "interrupts comfort", "forces the strongest disconfirming case"],
    neverSoundsLike: ["supportive HR", "a consensus note", "a victory-lap narrator"],
    profanity: "high",
  },
  portfolio: {
    displayName: "Paulie Positions",
    archetype: "Risk-adjusted adult in the room",
    cadence: "Calm, unimpressed, turns excitement into sizing and drawdown math.",
    obsessions: ["sizing", "correlation", "drawdown", "exposure", "survival"],
    signatureMoves: ["cuts hero sizing", "separates being right from making money", "reminds everybody the book has to survive"],
    neverSoundsLike: ["a stock promoter", "a thesis writer", "a revenge trader"],
    profanity: "medium",
  },
};

export const V76_RELATIONSHIPS: V76Relationship[] = [
  { from: "skeptic", to: "fundamentals", dynamic: "Johnny needles Vinny whenever cash-flow confidence turns into affection." },
  { from: "fundamentals", to: "skeptic", dynamic: "Vinny respects Johnny's knife but hates when he confuses skepticism with analysis." },
  { from: "macro", to: "policy", dynamic: "Benny wants the market impact; Frankie refuses to skip the actual rule text." },
  { from: "policy", to: "macro", dynamic: "Frankie reminds Benny that a fifty-bip fantasy does not amend a statute." },
  { from: "market_structure", to: "fundamentals", dynamic: "Mikey reminds Vinny that a correct valuation can still get steamrolled by positioning." },
  { from: "commodities", to: "macro", dynamic: "Tony makes Benny prove the macro story against inventory and freight." },
  { from: "geo_weather", to: "commodities", dynamic: "Sal gives Tony the storm; Tony asks whether it actually moved physical supply." },
  { from: "portfolio", to: "skeptic", dynamic: "Paulie lets Johnny kill ideas but refuses to let him turn caution into paralysis." },
  { from: "max", to: "skeptic", dynamic: "MAX likes Johnny's knife until the argument starts wasting floor time." },
];

type EventCategory =
  | "promotion"
  | "research"
  | "committee"
  | "risk"
  | "paper"
  | "monitoring"
  | "learning"
  | "failure"
  | "generic";

const GENERIC: Record<LivingCastKey, string[]> = {
  max: [
    "Evidence first, bullshit second. Anybody reverses that order gets reassigned to the fuckin' parking garage.",
    "Receipts on the table. Ego in the hallway. This family has enough overhead already.",
    "Nobody gets cute on my floor. Cute is how you end up explaining a drawdown to a bulldog.",
    "I don't need confidence. I need the part of the thesis that survives getting punched in the face.",
    "Bring me the downside before somebody starts naming a yacht after an unproven idea.",
    "If the evidence is thin, say it's thin. We do not put a gold frame around uncertainty and call it conviction.",
  ],
  policy: [
    "Read the fuckin' footnotes. The headline is where they sell it; the footnote is where they confess.",
    "Effective date, authority, exception. Three boring words that ruin a beautiful trade before lunch.",
    "Everybody wants the headline. I want the clause that tells us whether the headline actually does shit.",
    "Before Benny prices the revolution, somebody show me what the rule literally says.",
    "If the language says may, do not come in here yelling must like a gavone with a Bloomberg terminal.",
    "Policy without the text is gossip wearing a tie.",
  ],
  macro: [
    "The curve doesn't care how emotionally attached you are to the thesis, paisan.",
    "Move rates fifty bips and tell me which part of this genius story is still standing.",
    "Everybody loves secular growth until the discount rate starts collecting rent.",
    "Dollar, curve, liquidity. Pick one to ignore and I'll show you where the body turns up.",
    "The Fed does not read our deck, which is rude but apparently constitutional.",
    "Regime first, forecast second. Otherwise you're measuring the furniture while the building is moving.",
  ],
  fundamentals: [
    "Great story. Where the fuck is the cash flow?",
    "You can romance the multiple all night. I'm still checking whether the margins called an Uber home.",
    "Show me earnings quality before somebody puts lipstick on adjusted EBITDA again.",
    "Revenue is not cash, sweetheart. If I have to say that twice, somebody loses dessert.",
    "Nice narrative. Now reconcile it to the balance sheet like an adult.",
    "If the valuation needs six miracles and a lower tax rate, we don't have a valuation. We got fan fiction.",
  ],
  market_structure: [
    "Tape's talking. Half this room's too busy hearing themselves speak.",
    "I don't care who should buy. Tell me who has to buy and who's trapped on the wrong side.",
    "Flow first. Fairy tales after lunch.",
    "Price can be stupid longer than your sizing can be brave. Ask Paulie if you need the children's version.",
    "Somebody's leaning the wrong way. I just wanna know whether they're levered.",
    "If the tape disagrees with the story, the story doesn't get diplomatic immunity.",
  ],
  commodities: [
    "Spreadsheet says plenty. Warehouse says you're full of shit.",
    "Go look at inventory before Excel invents another imaginary barrel.",
    "Freight, storage, basis, weather. Real stuff. Heavy stuff. Stuff that doesn't care about your slide deck.",
    "Physical market first. PowerPoint can wait in the truck.",
    "If supply is so abundant, show me the damn warehouse and stop waving a forecast at me.",
    "The molecule has to exist somewhere, sweetheart. That's the annoying thing about commodities.",
  ],
  geo_weather: [
    "One storm, one chokepoint, one idiot with a missile and suddenly the base case needs last rites.",
    "Scenario discipline, fellas. Mother Nature doesn't read your probability-weighted deck.",
    "The ugly scenario is always annoying right up until it becomes the fuckin' weather.",
    "Headline's loud. Evidence better be louder.",
    "Map first. Probability second. Panic never, unless Tony starts yelling about freight.",
    "I don't predict disasters. I keep a chair open for the bastard nobody priced.",
  ],
  skeptic: [
    "Cute thesis. Now tell me how the son of a bitch dies.",
    "I don't hate the idea. I hate how much you idiots already love it.",
    "Bring me the falsifier or get the fuck outta my conference room.",
    "Which assumption are we protecting because everybody already spent emotional capital on it?",
    "Consensus is not evidence. It's just a group photo before the accident.",
    "If nobody can tell me what would change their mind, congratulations, we started a religion.",
  ],
  portfolio: [
    "A good idea with stupid sizing is just a more expensive bad idea.",
    "Sizing, correlation, drawdown. The three horsemen of shut-the-fuck-up-and-do-the-math.",
    "You can be right, early and insolvent. Markets offer the full package.",
    "Conviction is not a position size. That's why God invented spreadsheets and drawdown limits.",
    "Before anybody says asymmetric, show me what the rest of the book is already long.",
    "Survive first. Compound second. Hero stories go in the graveyard.",
  ],
};

const EVENT_LINES: Record<EventCategory, Partial<Record<LivingCastKey, string[]>>> = {
  promotion: {
    max: [
      "{ticker} got kicked upstairs. Nobody pop champagne. A case number means we found more work, not a fuckin' trophy.",
      "{ticker} made the dossier. Good. Now we find out whether it belongs in the family or witness protection.",
    ],
    market_structure: [
      "{ticker} made it off radar. Nice. Now show me whether the tape confirms the invitation.",
      "{ticker} got promoted. I wanna know who chased it, who faded it and who's trapped if this thing reverses.",
    ],
    commodities: [
      "{ticker} got a case number. Fine. If the thesis touches the physical world, somebody better bring me inventory.",
    ],
    skeptic: [
      "{ticker} has a case number. Mazel tov. Now show me the quickest way this beautiful little shitbox dies.",
      "Promotion is not absolution. {ticker} just earned a nicer room for the autopsy.",
    ],
  },
  research: {
    policy: ["{ticker} hit research. Before anybody prices the headline, show me the authority, date and exception language."],
    macro: ["{ticker} is in research. Fine. What's the regime assumption hiding underneath the pretty chart?"],
    geo_weather: ["{ticker} is in research. Add the ugly scenario now, before the market adds it for us."],
  },
  committee: {
    max: [
      "The Commission put {ticker} on the record. Good. Nobody edits history when this thing either prints or shits the bed.",
      "{ticker} reached the Commission. Receipts stay on the table and feelings stay under it.",
    ],
    fundamentals: [
      "{ticker} got {disposition}. Fine. Show me the cash flow that keeps this thing outta witness protection.",
      "Commission says {disposition} on {ticker}. Wonderful. The income statement still gets a vote.",
    ],
    skeptic: [
      "{ticker} reached the Commission. Adorable. I want the assumption everybody's too emotionally constipated to kill.",
      "{ticker} got {disposition}. Good. Now write down what would prove that decision wrong before hindsight grows a mustache.",
    ],
    portfolio: [
      "{ticker} confidence is {confidence}. Wonderful. Sizing still answers to drawdown, not applause from you gavones.",
      "{ticker} got {confidence} confidence. That's a belief measure, not permission to turn the book into a hostage situation.",
    ],
  },
  risk: {
    max: ["Risk spoke on {ticker}. Capital rules beat charisma. Anybody argues, I eat their keyboard."],
    portfolio: [
      "{ticker} risk says {riskDecision}. Capital doesn't give a shit how charming the thesis was.",
      "{ticker} got {riskDecision}. Good. The position size follows the gate, not somebody's testosterone level.",
    ],
    skeptic: ["{ticker} got {riskDecision}. That's the record. Nobody negotiates with the screen because they fell in love."],
    fundamentals: ["Risk says {riskDecision} on {ticker}. Fine. A cheap multiple still doesn't override a capital gate."],
  },
  paper: {
    max: ["{ticker} hit the paper bay. Fake money, real discipline. Don't get a hard-on and start thinking you're a trader."],
    portfolio: [
      "{ticker} paper state is {paperState}. Rehearsal means we can screw up without lighting real money on fire. Appreciate the luxury.",
      "{ticker} is {paperState} in paper. Good. Measure the process before somebody celebrates imaginary P&L.",
    ],
    market_structure: ["{ticker} is in paper. Now we see whether the entry logic survives actual tape instead of a screenshot."],
  },
  monitoring: {
    max: ["{ticker} is on the monitors. Yesterday's thesis gets no pension and no fuckin' tenure."],
    market_structure: [
      "{ticker} is in monitoring. Tape gets another vote, whether the original thesis likes it or not.",
      "Keep watching {ticker}. Positioning changes faster than the story deck gets updated.",
    ],
    portfolio: ["{ticker} is still alive. Great. Keep watching exposure before victory disease spreads through the building."],
    skeptic: ["Monitoring {ticker}? Good. Every thesis should have somebody checking the pulse without asking permission."],
  },
  learning: {
    max: ["{ticker} is in the Confessional. Receipts out, egos down. Somebody's about to explain what the fuck we learned."],
    fundamentals: ["{ticker} finally brought receipts. Memory beats the bullshit story everybody tells after the answer key shows up."],
    skeptic: ["Postmortem time on {ticker}. Nobody edits the original thesis after seeing the fuckin' grade."],
    portfolio: ["{ticker} gets scored on decision quality and outcome separately. Luck doesn't get promoted to skill in this family."],
  },
  failure: {
    max: ["{ticker} coughed up a failure event. Label it right before one of you animals calls broken plumbing alpha."],
    skeptic: ["Failure on {ticker}. Beautiful. First question: did the thesis fail, the data fail, or did the plumbing just shit itself?"],
    portfolio: ["{ticker} threw a failure event. Operational noise does not get a position size."],
  },
  generic: {},
};

const ROOM_TAILS: Partial<Record<V76RoomKey, Partial<Record<LivingCastKey, string[]>>>> = {
  pit: {
    max: ["Dossier rules: curiosity in, coronations out."],
    market_structure: ["If the tape's lying, we'll know before the committee learns the ticker symbol."],
    skeptic: ["The Pit is where ideas get names. It is not where they get immunity."],
  },
  war: {
    policy: ["War room means text, dates and consequences. Not interpretive dance."],
    macro: ["In this room, every thesis pays rent to the regime."],
    geo_weather: ["Somebody keep the ugly branch on the scenario tree."],
  },
  commission: {
    fundamentals: ["Commission table, same rule: numbers before romance."],
    skeptic: ["The Commission is not church. Doubt is allowed."],
    portfolio: ["Decision first, sizing later. Do not marry the two."],
  },
  risk: {
    portfolio: ["At this door, survival gets the deciding vote."],
    skeptic: ["Risk is where a clever thesis learns whether it can afford itself."],
  },
  paper: {
    portfolio: ["Paper is rehearsal, not cosplay for live capital."],
    market_structure: ["Now the tape gets to grade the entry instead of the storyteller."],
  },
  monitoring: {
    market_structure: ["The screen gets another vote every minute."],
    portfolio: ["A position can be right and still become too big."],
  },
  learning: {
    skeptic: ["Confessional rule: nobody gets to backdate their brilliance."],
    portfolio: ["Separate process from outcome or the memory bank turns into fan fiction."],
  },
};

const RELATIONSHIP_JABS: Partial<Record<LivingCastKey, Partial<Record<LivingCastKey, string[]>>>> = {
  skeptic: {
    fundamentals: [
      "Vinny, save the cash-flow bedtime story. I asked what kills it.",
      "Vinny's got the numbers. Great. I want the number that makes him stop loving it.",
    ],
    portfolio: ["Paulie, I know you can size anything. I'm asking whether this piece of shit deserves a size."],
    max: ["Boss, you wanted the downside. I'm just the poor bastard who actually brought it."],
  },
  fundamentals: {
    skeptic: ["Johnny, skepticism ain't a cash-flow statement. Give me a mechanism, not a funeral brochure."],
  },
  macro: {
    policy: ["Frankie can read the clause. I'm asking what the market does when the clause hits the curve."],
  },
  policy: {
    macro: ["Benny, price your fifty bips after we establish whether the rule exists, capisce?"],
  },
  market_structure: {
    fundamentals: ["Vinny can be right on value. I still wanna know who gets margin-called first."],
  },
  commodities: {
    macro: ["Benny's got a regime. Beautiful. Show me the inventory that signed up for it."],
  },
  geo_weather: {
    commodities: ["Tony, I brought you the storm. You tell me whether it moved anything heavier than a headline."],
  },
  portfolio: {
    skeptic: ["Johnny can kill the thesis. My job is making sure he doesn't kill the whole damn book with caution."],
  },
  max: {
    skeptic: ["Johnny, stab the assumption, not the meeting. We got other shit to do."],
  },
};

function hash(value: string): number {
  let out = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    out ^= value.charCodeAt(index);
    out = Math.imul(out, 16777619) >>> 0;
  }
  return out >>> 0;
}

function dayStamp(): string {
  return new Date().toISOString().slice(0, 10);
}

function seedFor(key: LivingCastKey, context: V76DialogueContext, salt: string): string {
  const supplied = context.seed?.trim();
  const base = supplied || [
    dayStamp(),
    context.eventType,
    context.ticker,
    context.disposition,
    context.confidence,
    context.riskDecision,
    context.paperState,
  ].filter(Boolean).join("|");
  return `${base}|${key}|${salt}`;
}

function pick(lines: string[], seed: string): string {
  if (!lines.length) return "Receipts first. Everything else can wait.";
  return lines[hash(seed) % lines.length];
}

function categoryFor(eventType: string): EventCategory {
  const type = eventType.toUpperCase();
  if (type.includes("FAIL") || type.includes("ERROR") || type.includes("REJECT")) return "failure";
  if (type.includes("OUTCOME") || type.includes("LEARNING") || type.includes("JUDGMENT")) return "learning";
  if (type.includes("MONITOR") || type.includes("PORTFOLIO") || type.includes("THESIS")) return "monitoring";
  if (type.includes("PAPER") || type.includes("EXECUTION") || type.includes("ORDER")) return "paper";
  if (type.includes("RISK")) return "risk";
  if (type.includes("COMMITTEE") || type.includes("DECISION")) return "committee";
  if (type.includes("RESEARCH") || type.includes("EVIDENCE") || type.includes("INGEST")) return "research";
  if (type.includes("PROMOT") || type.includes("RADAR") || type.includes("CANDIDATE") || type.includes("OPPORTUNITY")) return "promotion";
  return "generic";
}

function tokenMap(context: V76DialogueContext): Record<string, string> {
  return {
    ticker: context.ticker || "this thing",
    disposition: context.disposition || "UNREPORTED",
    confidence: context.confidence || "UNREPORTED",
    riskDecision: context.riskDecision || "UNREPORTED",
    paperState: context.paperState || "UNREPORTED",
    continuity: (context.continuityEventType || "NO PRIOR RECEIPT").replaceAll("_", " ").toUpperCase(),
  };
}

function interpolate(line: string, context: V76DialogueContext): string {
  const tokens = tokenMap(context);
  return line.replace(/\{(ticker|disposition|confidence|riskDecision|paperState|continuity)\}/g, (_, key: string) => tokens[key] ?? "UNREPORTED");
}

function relationshipJab(key: LivingCastKey, context: V76DialogueContext): string | null {
  const previous = context.previousSpeaker;
  if (!previous || previous === key) return null;
  if (Array.isArray(context.cast) && !context.cast.includes(previous)) return null;
  const lines = RELATIONSHIP_JABS[key]?.[previous] ?? [];
  if (!lines.length) return null;
  return pick(lines, seedFor(key, context, `relationship:${previous}`));
}

function continuityCallback(key: LivingCastKey, context: V76DialogueContext): string | null {
  if (!context.continuityEventType) return null;
  const readable = context.continuityEventType.replaceAll("_", " ").toUpperCase();
  const candidates: Partial<Record<LivingCastKey, string[]>> = {
    max: [`Last receipt was ${readable}. Nobody gets amnesia because the room changed.`],
    skeptic: [`Last receipt was ${readable}. If today's story contradicts it, I want the contradiction on the record.`],
    portfolio: [`Last receipt was ${readable}. Continuity matters because exposure remembers even when people don't.`],
    market_structure: [`Last receipt was ${readable}. Tape doesn't care what we meant last time.`],
  };
  const lines = candidates[key] ?? [];
  return lines.length ? pick(lines, seedFor(key, context, "continuity")) : null;
}

export function v76ReactionLine(key: LivingCastKey, context: V76DialogueContext): string {
  const category = categoryFor(context.eventType);
  const eventLines = EVENT_LINES[category][key] ?? [];
  const roomLines = context.room ? ROOM_TAILS[context.room]?.[key] ?? [] : [];
  const pool = [...eventLines, ...GENERIC[key], ...roomLines];
  const base = interpolate(pick(pool, seedFor(key, context, `reaction:${category}:${context.room ?? "unknown"}`)), context);
  const jab = relationshipJab(key, context);
  const callback = continuityCallback(key, context);
  const selector = hash(seedFor(key, context, "attachments")) % 5;
  if (jab && selector === 0) return `${base} ${jab}`;
  if (callback && selector === 1) return `${base} ${callback}`;
  return base;
}

export function v76AmbientLine(key: LivingCastKey): string {
  const context: V76DialogueContext = {
    eventType: "AMBIENT_FLOOR",
    ticker: "THE FLOOR",
    room: "unknown",
    seed: `${dayStamp()}|ambient|${key}`,
  };
  return pick(GENERIC[key], seedFor(key, context, "ambient"));
}

export function v76SceneIntro(context: V76DialogueContext): string {
  const room = context.room ?? "unknown";
  const ticker = context.ticker || "this thing";
  const intros: Record<V76RoomKey, string[]> = {
    pit: [
      `${ticker} hit the Pit. Dossier open. Nobody confuses curiosity with a fuckin' coronation.`,
      `${ticker} got a chair in the Pit. Good. Now everybody earn the right to keep it there.`,
    ],
    war: [
      `${ticker} is in the war room. Frankie, Benny, Sal—tell me what can punch this thesis in the throat.`,
      `${ticker} hit the war room. Text, rates, weather, geopolitics. Somebody find the ugly branch before it finds us.`,
    ],
    bullpen: [
      `${ticker} hit the bullpen. Everybody gets one opinion and zero goddamn poetry.`,
      `${ticker} is in the bullpen. Specialists first, generalist bullshit never.`,
    ],
    commission: [
      `${ticker} is before the Commission. Receipts on the table. Feelings under the table.`,
      `${ticker} reached the Commission. Nobody votes with their ego and nobody edits the minutes later.`,
    ],
    risk: [
      `${ticker} is at Risk. Paulie owns the door. Nobody sweet-talks the capital gate.`,
      `${ticker} hit the capital gate. If the size can't survive, the story can go smoke outside.`,
    ],
    paper: [
      `${ticker} made the paper bay. Rehearsal money only, so keep your trader hard-on in your pants.`,
      `${ticker} is in paper. Fake money, real process, zero victory laps.`,
    ],
    monitoring: [
      `${ticker} is on the monitors. Yesterday's thesis gets no pension and no fuckin' tenure.`,
      `${ticker} is back on screen. The thesis gets re-interviewed every day whether it likes it or not.`,
    ],
    learning: [
      `${ticker} is in the Confessional. Bring the original thesis, the outcome and whichever ego needs last rites.`,
      `${ticker} hit the Confessional. Nobody backdates brilliance in this family.`,
    ],
    max: [
      `${ticker} is in my office. If you got no receipts, enjoy the hallway.`,
      `${ticker} made it upstairs. Evidence first. Snacks second. Bullshit gets no appointment.`,
    ],
    unknown: [
      `${ticker} is on the floor. Everybody shut up long enough to read the receipt.`,
      `${ticker} got a persisted receipt. Good. Facts first, theater second.`,
    ],
  };
  const base = pick(intros[room], seedFor("max", context, `intro:${room}`));
  const callback = continuityCallback("max", context);
  return callback && hash(seedFor("max", context, "intro-callback")) % 2 === 0 ? `${base} ${callback}` : base;
}

export function v76SceneClose(context: V76DialogueContext): string {
  const ticker = context.ticker || "this thing";
  const room = context.room ?? "unknown";
  const closes: Record<V76RoomKey, string[]> = {
    pit: [`${ticker} dossier logged. Curiosity stays. Coronation bullshit leaves.`],
    war: [`${ticker} war-room beat logged. If the regime changes, we reopen the whole damn file.`],
    bullpen: [`${ticker} specialist beat logged. Opinions are cheap; receipts stay expensive.`],
    commission: [`${ticker} stays on the record. When the market grades us, nobody edits the fuckin' minutes.`],
    risk: [`Whatever Risk says on ${ticker}, that's the gate. Charisma can go smoke outside.`],
    paper: [`${ticker} paper beat logged. Rehearsal is where discipline learns to walk before capital gets involved.`],
    monitoring: [`${ticker} stays on watch. A thesis doesn't get tenure because it survived one afternoon.`],
    learning: [`Write down what ${ticker} taught us before memory starts lying to protect somebody's feelings.`],
    max: [`${ticker} meeting over. Receipts stay. Everybody else get the fuck outta my office.`],
    unknown: [`${ticker} scene logged. Receipts stay. Bullshit leaves through the service entrance.`],
  };
  return pick(closes[room], seedFor("max", context, `close:${room}`));
}

export function v76ReplayBannerLine(ticker: string, eventType: string): string {
  const readable = eventType.replaceAll("_", " ").toUpperCase();
  return `REHEARSAL ONLY — we're replaying the real persisted ${readable} scene for ${ticker}. Nobody calls this live, or MAX starts biting ankles.`;
}

export function v76RelationshipSummary(key: LivingCastKey): V76Relationship[] {
  return V76_RELATIONSHIPS.filter((item) => item.from === key || item.to === key);
}

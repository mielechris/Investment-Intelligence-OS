import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { AGENT_VISUAL_CONTRACTS } from "./agentVisualContracts";
import "./MockTradingFactory.css";

type MockStage = "RADAR" | "RESEARCH" | "COMMITTEE" | "RISK" | "PAPER" | "REVIEW";
type CheckState = "PASS" | "WARN" | "FAIL" | "PENDING";
type MaxMood = "WATCHING" | "WORKING" | "SUSPICIOUS" | "PISSED" | "APPROVING" | "REVIEWING";
type MockCase = {
  ticker:string;
  score:number;
  catalyst:string;
  decision:"WATCH"|"PROMOTE"|"NO TRADE"|"MOCK BUY"|"MOCK SELL";
  checks:Array<{label:string;state:CheckState}>;
  tape:number[];
};

const STAGES:MockStage[]=["RADAR","RESEARCH","COMMITTEE","RISK","PAPER","REVIEW"];
const CASES:MockCase[]=[
 {ticker:"NVDA",score:86,catalyst:"Earnings / AI demand / abnormal volume",decision:"WATCH",checks:[{label:"Catalyst",state:"PASS"},{label:"Volume",state:"PASS"},{label:"Breadth",state:"WARN"},{label:"Entry quality",state:"PENDING"}],tape:[181.4,183.1,184.8,183.9,186.2,187.1]},
 {ticker:"AVGO",score:78,catalyst:"Semiconductor read-through / policy conflict",decision:"NO TRADE",checks:[{label:"Sector",state:"PASS"},{label:"Momentum",state:"PASS"},{label:"Policy risk",state:"WARN"},{label:"Risk gate",state:"FAIL"}],tape:[356.2,358.0,357.1,355.4,356.8,354.9]},
 {ticker:"SPY",score:74,catalyst:"Index strength / narrow leadership",decision:"PROMOTE",checks:[{label:"Price",state:"PASS"},{label:"Breadth",state:"WARN"},{label:"Regime",state:"PASS"},{label:"Committee",state:"PENDING"}],tape:[651.1,651.8,652.0,651.6,652.4,652.8]},
 {ticker:"CRM",score:72,catalyst:"Company-specific earnings catalyst",decision:"MOCK BUY",checks:[{label:"Catalyst",state:"PASS"},{label:"Evidence",state:"PASS"},{label:"Committee",state:"PASS"},{label:"Risk",state:"PASS"}],tape:[241.2,242.0,243.4,242.8,244.1,245.0]},
];

const ROOM_COPY:Record<MockStage,string>={
 RADAR:"9A spots movement in the street.",
 RESEARCH:"The crew checks the story before believing it.",
 COMMITTEE:"Everybody sits down. Nobody gets a free pass.",
 RISK:"Risk checks whether the trade deserves to leave the room.",
 PAPER:"Mock ticket only. Real capital stays locked.",
 REVIEW:"After Action grades the call with hindsight separated from process.",
};

const MAX_MOOD_BY_STAGE:Record<MockStage,MaxMood>={
 RADAR:"WATCHING",
 RESEARCH:"WORKING",
 COMMITTEE:"SUSPICIOUS",
 RISK:"PISSED",
 PAPER:"APPROVING",
 REVIEW:"REVIEWING",
};

const MAX_MOOD_COPY:Record<MaxMood,string>={
 WATCHING:"Eyes on the street",
 WORKING:"Crew is digging",
 SUSPICIOUS:"Convince me",
 PISSED:"Risk found something",
 APPROVING:"Mock ticket cleared",
 REVIEWING:"Bring the file back",
};

function mark(s:CheckState){return s==="PASS"?"✅":s==="WARN"?"⚠️":s==="FAIL"?"❌":"⏳"}

export default function MockTradingFactory(){
 const[tick,setTick]=useState(0);
 const[paused,setPaused]=useState(false);
 const[showBubble,setShowBubble]=useState(true);
 useEffect(()=>{if(paused)return;const timer=window.setInterval(()=>setTick(v=>v+1),2200);return()=>window.clearInterval(timer)},[paused]);

 const stageIndex=tick%STAGES.length;
 const activeStage=STAGES[stageIndex];
 const movingCase=CASES[Math.floor(tick/STAGES.length)%CASES.length];
 const activeAgentIndex=tick%AGENT_VISUAL_CONTRACTS.length;
 const activeAgent=AGENT_VISUAL_CONTRACTS[activeAgentIndex];
 const supportAgent=AGENT_VISUAL_CONTRACTS[(activeAgentIndex+1)%AGENT_VISUAL_CONTRACTS.length];
 const maxMood=MAX_MOOD_BY_STAGE[activeStage];
 const mockNav=10000+((tick%11)-4)*13.25;
 const mockPnl=mockNav-10000;
 const price=movingCase.tape[tick%movingCase.tape.length];
 const afterAction=activeStage==="REVIEW";
 const hasFailure=movingCase.checks.some(c=>c.state==="FAIL");
 const progressPct=(stageIndex/(STAGES.length-1))*100;

 const maxLine=useMemo(()=>{
  const roomLines:Record<MockStage,string>={
   RADAR:`I see ${movingCase.ticker}. Nobody falls in love with a ticker in the hallway.`,
   RESEARCH:`${activeAgent.mobAlias||activeAgent.floorTitle} has the file. Dig until the story either earns respect or dies.`,
   COMMITTEE:`Everybody at the table. If the thesis needs applause to survive, bury it.`,
   RISK:hasFailure?`Stop. Something in ${movingCase.ticker} stinks. Risk gets the last word before the mock ticket.`:`Risk room is open. Size the downside before you count the upside.`,
   PAPER:`Mock ticket only. Real money stays in the vault.`,
   REVIEW:`Bring ${movingCase.ticker} back in. We grade the decision, not the ego.`,
  };
  return roomLines[activeStage];
 },[activeAgent.floorTitle,activeAgent.mobAlias,activeStage,hasFailure,movingCase.ticker]);

 const trailStyle={"--stage-index":stageIndex,"--progress":`${progressPct}%`} as CSSProperties;

 return <section className="mock-factory" aria-label="IIOS mock trading factory">
  <header className="mock-factory__header">
   <div><span className="mock-factory__eyebrow">BATCH 10A · X3 FACTORY THEATER</span><h2>THE MOB FLOOR · MOCK TRADING MODE</h2><p>Living demonstration only. Mock activity cannot enter governed telemetry, Committee, Risk, the real paper portfolio, learning history, broker paths, or live capital.</p></div>
   <div className="mock-factory__lock"><strong>MOCK / DEMO</strong><span>REAL ENGINE ISOLATED</span><span>LIVE CAPITAL LOCKED</span></div>
  </header>

  <div className="mock-market-tape"><b>MOCK STREET TAPE</b>{CASES.map((c,i)=><span key={c.ticker}>{c.ticker} {c.tape[(tick+i)%c.tape.length].toFixed(2)} <em>{i%2?"▼":"▲"}</em></span>)}<strong>NO REAL QUOTES</strong></div>

  <div className="mock-factory__toolbar">
   <button type="button" onClick={()=>setPaused(v=>!v)}>{paused?"RESUME FLOOR":"PAUSE FLOOR"}</button>
   <button type="button" onClick={()=>setShowBubble(v=>!v)}>{showBubble?"MUTE MOB":"SHOW MOB"}</button>
   <span>SCENE {tick+1}</span><span>ACTIVE ROOM · {activeStage}</span><span>ACTIVE DESK · {activeAgent.mobAlias||activeAgent.floorTitle}</span>
  </div>

  <div className="mock-factory__grid">
   <aside className={`mock-factory__max max-mood--${maxMood.toLowerCase()}`}>
    <div className={`mock-factory__portrait ${activeStage==="RISK"?"alarm":""}`}>
     <div className="max-status-ring"><span className="max-dog">MAX</span></div>
     <small>FLOOR BOSS</small>
     <b className="max-mood-badge">{maxMood}</b>
    </div>
    <h3>MAX · THE BOSS</h3>
    <div className="max-mood-copy">{MAX_MOOD_COPY[maxMood]}</div>
    {showBubble?<div className="mob-bubble">“{maxLine}”</div>:null}
    <div className="max-command-strip"><span>CASE</span><b>{movingCase.ticker}</b><span>ROOM</span><b>{activeStage}</b></div>
    <div className="mock-factory__metrics"><span>MOCK NAV <b>${mockNav.toFixed(2)}</b></span><span>MOCK P&L <b>{mockPnl>=0?"+":""}${mockPnl.toFixed(2)}</b></span><span>REAL ORDERS <b>0</b></span></div>
   </aside>

   <main className="mock-factory__floor">
    <div className="mock-factory__rooms">{STAGES.map((stage,i)=><div key={stage} className={`mock-room ${stage===activeStage?"mock-room--active":""} ${stage==="COMMITTEE"&&stage===activeStage?"committee-light":""} ${stage==="RISK"&&stage===activeStage?"risk-light":""} ${i<stageIndex?"mock-room--cleared":""}`}><span>{stage}</span><small>{stage===activeStage?`${movingCase.ticker} IN ROOM`:i<stageIndex?"CLEARED":"STANDBY"}</small></div>)}</div>

    <div className="case-transit" style={trailStyle}>
     <div className="case-transit__rail"><div className="case-transit__progress" /></div>
     {STAGES.map((stage,i)=><i key={stage} className={`case-transit__node ${i<stageIndex?"done":""} ${i===stageIndex?"active":""}`}><span>{i+1}</span></i>)}
     <div className="case-runner"><b>{movingCase.ticker}</b><small>{activeStage} FILE</small></div>
     <div className="handoff-flash">{activeAgent.mobAlias||activeAgent.floorTitle} → {activeStage}</div>
    </div>

    <div className="mock-factory__case-card">
     <div className="mock-factory__case-head"><div><span>CURRENT MOCK CASE</span><strong>{movingCase.ticker}</strong></div><div><span>MOCK PRICE</span><strong>${price.toFixed(2)}</strong></div><div><span>RADAR SCORE</span><strong>{movingCase.score}</strong></div><div><span>DISPOSITION</span><strong>{movingCase.decision}</strong></div></div>
     <p><b>WHY IT SURFACED:</b> {movingCase.catalyst}</p>
     <p className="room-narration"><b>ROOM:</b> {ROOM_COPY[activeStage]}</p>
     <div className="mock-factory__checks">{movingCase.checks.map(item=><span key={item.label}>{mark(item.state)} {item.label}</span>)}</div>
     <div className="mock-factory__handoff"><b>HANDOFF</b> · MAX → {activeAgent.mobAlias||activeAgent.floorTitle} → {activeStage}</div>
    </div>

    <div className="crew-header"><span>THE EIGHT DESKS</span><strong>EVERYBODY HAS A JOB. EGO IS NOT ONE.</strong></div>
    <div className="mock-factory__desks">{AGENT_VISUAL_CONTRACTS.map((agent,index)=>{
      const active=index===activeAgentIndex;
      const supporting=agent.key===supportAgent.key&&!active;
      const warning=active&&(activeStage==="RISK"||hasFailure);
      const status=active?(warning?"BLOCKING / CHALLENGING":"WORKING MOCK CASE"):supporting?"ON DECK":"WAITING";
      const line=warning?(agent.warningLine||agent.maxReaction):active?(agent.workingLine||agent.maxReaction):supporting?"Standing by for the handoff.":agent.clearedLine||"Waiting for a case.";
      return <div key={agent.key} className={`mock-desk ${active?"mock-desk--active":""} ${supporting?"mock-desk--support":""} ${warning?"mock-desk--warning":""}`}>
       <div className="mob-avatar"><span>{agent.mobAlias?.split(" ").pop()?.slice(0,2)||agent.floorTitle.slice(0,2)}</span></div>
       <div className="desk-title"><small>{agent.mobAlias||"CREW"}</small><strong>{agent.floorTitle}</strong></div>
       <span>{agent.crewRole||agent.characterArchetype}</span>
       <em>{status}</em>
       {showBubble&&(active||supporting)?<i>“{line}”</i>:null}
      </div>
    })}</div>

    {afterAction?<section className="after-action-room"><div><span>AFTER ACTION ROOM</span><h3>{movingCase.ticker} GETS CALLED BACK INTO THE OFFICE</h3></div><div className="aar-grid"><b>PROCESS GRADE · {movingCase.decision==="NO TRADE"?"A":"B+"}</b><span>Thesis discipline: PASS</span><span>Risk discipline: {hasFailure?"VETO VALUABLE":"PASS"}</span><span>Hindsight contamination: BLOCKED</span><span>Lesson: recorded in MOCK memory only</span></div></section>:null}
   </main>
  </div>

  <footer className="mock-factory__footer"><b>MOCK DATA NEVER BECOMES REAL TELEMETRY.</b><span>The governed IIOS engine continues separately in paper mode.</span></footer>
 </section>
}

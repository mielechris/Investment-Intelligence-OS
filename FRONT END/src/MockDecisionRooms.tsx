import "./MockTradingFactoryPolish.css";

type CheckState = "PASS" | "WARN" | "FAIL" | "PENDING";

type Check = { label:string; state:CheckState };

type CommonProps = {
  ticker:string;
  score:number;
  decision:string;
  checks:Check[];
};

function mark(state:CheckState){
  return state === "PASS" ? "✅" : state === "WARN" ? "⚠️" : state === "FAIL" ? "❌" : "⏳";
}

export function MockCommitteeRoom({ticker,score,decision,checks}:CommonProps){
  const pass=checks.filter(item=>item.state==="PASS").length;
  const warn=checks.filter(item=>item.state==="WARN"||item.state==="PENDING").length;
  const fail=checks.filter(item=>item.state==="FAIL").length;
  const noTrade=decision==="NO TRADE"||fail>0;
  return <section className={`decision-room committee-chamber ${noTrade?"decision-room--blocked":""}`}>
    <header><div><span>THE SIT-DOWN</span><h3>INVESTMENT COMMITTEE · {ticker}</h3></div><strong>{noTrade?"NO TRADE PRESSURE":"DEBATE IN SESSION"}</strong></header>
    <div className="committee-table">
      <div><span>SUPPORT</span><b>{pass}</b><small>passed checks</small></div>
      <div><span>QUESTIONS</span><b>{warn}</b><small>open / uncertain</small></div>
      <div><span>OBJECTIONS</span><b>{fail}</b><small>failed checks</small></div>
      <div><span>RADAR SCORE</span><b>{score}</b><small>mock observation</small></div>
    </div>
    <p>Everybody gets a chair. Nobody gets a free pass. The room debates the evidence before the case can approach Risk.</p>
    <footer><b>MOCK COMMITTEE ONLY</b><span>No governed committee record is created.</span></footer>
  </section>
}

export function MockRiskRoom({ticker,decision,checks}:CommonProps){
  const failures=checks.filter(item=>item.state==="FAIL");
  const warnings=checks.filter(item=>item.state==="WARN"||item.state==="PENDING");
  const veto=decision==="NO TRADE"||failures.length>0;
  return <section className={`decision-room risk-chamber ${veto?"risk-chamber--veto":"risk-chamber--clear"}`}>
    <header><div><span>THE GATE</span><h3>RISK INSPECTION · {ticker}</h3></div><strong>{veto?"VETO / HOLD":"MOCK CLEAR"}</strong></header>
    <div className="risk-lock"><div className="risk-lock__core">{veto?"LOCKED":"CLEAR"}</div><div className="risk-lock__rings"><i/><i/><i/></div></div>
    <div className="risk-reasons">
      {(failures.length?failures:warnings).slice(0,4).map(item=><span key={item.label}>{mark(item.state)} {item.label}</span>)}
      {!failures.length&&!warnings.length?<span>✅ No mock blocker identified</span>:null}
    </div>
    <p>{veto?"The case does not leave this room clean. Mock capital remains untouched.":"The mock case clears this inspection, but real capital authority remains locked."}</p>
    <footer><b>REAL CAPITAL LOCKED</b><span>Risk theater has zero real authority.</span></footer>
  </section>
}

export function MockWhyDrawer({ticker,decision,checks,catalyst,open,onToggle}:{ticker:string;decision:string;checks:Check[];catalyst:string;open:boolean;onToggle:()=>void}){
  const passed=checks.filter(item=>item.state==="PASS");
  const failed=checks.filter(item=>item.state==="FAIL");
  const waiting=checks.filter(item=>item.state==="WARN"||item.state==="PENDING");
  return <section className={`why-drawer ${open?"why-drawer--open":""}`}>
    <button type="button" onClick={onToggle}><span>{decision==="NO TRADE"?"WHY NOT?":"WHY?"}</span><strong>{ticker} · EXPLAIN THIS MOCK DECISION</strong><em>{open?"CLOSE":"OPEN"}</em></button>
    {open?<div className="why-drawer__body">
      <div><span>WHAT IT SAW</span><p>{catalyst}</p></div>
      <div><span>WHAT PASSED</span>{passed.length?passed.map(item=><p key={item.label}>✅ {item.label}</p>):<p>None yet.</p>}</div>
      <div><span>WHAT FAILED</span>{failed.length?failed.map(item=><p key={item.label}>❌ {item.label}</p>):<p>No hard failure recorded.</p>}</div>
      <div><span>WHAT IT'S WAITING FOR</span>{waiting.length?waiting.map(item=><p key={item.label}>{mark(item.state)} {item.label}</p>):<p>Nothing outstanding.</p>}</div>
      <div className="why-drawer__decision"><span>FINAL MOCK DISPOSITION</span><strong>{decision}</strong><small>Mock theater only. No ledger write.</small></div>
    </div>:null}
  </section>
}

export function MockAfterActionRoom({ticker,decision,checks,score}:{ticker:string;decision:string;checks:Check[];score:number}){
  const failed=checks.filter(item=>item.state==="FAIL").length;
  const warnings=checks.filter(item=>item.state==="WARN"||item.state==="PENDING").length;
  const grade=decision==="NO TRADE"&&failed>0?"A":failed===0&&warnings<=1?"A-":"B+";
  return <section className="after-action-room after-action-room--v2">
    <header><div><span>AFTER ACTION ROOM</span><h3>{ticker} GETS CALLED BACK INTO THE OFFICE</h3></div><strong>PROCESS GRADE · {grade}</strong></header>
    <div className="aar-scoreboard">
      <div><span>ORIGINAL SCORE</span><b>{score}</b></div>
      <div><span>DISPOSITION</span><b>{decision}</b></div>
      <div><span>RISK DISCIPLINE</span><b>{failed?"VETO TESTED":"PASS"}</b></div>
      <div><span>HINDSIGHT</span><b>BLOCKED</b></div>
    </div>
    <div className="aar-office-note"><span>LESSON</span><p>{failed?"A flashy setup can still deserve a locked door when a hard check fails.":warnings?"The case earned attention, but uncertainty must stay visible instead of being painted green.":"Clean process. The mock result can be measured later without rewriting the original decision."}</p></div>
    <footer><b>MOCK MEMORY ONLY</b><span>Nothing here trains or mutates the governed engine.</span></footer>
  </section>
}

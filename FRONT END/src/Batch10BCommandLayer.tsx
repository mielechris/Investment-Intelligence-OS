import { useEffect, useMemo, useState } from "react";
import "./Batch10BCommandLayer.css";

const API = import.meta.env.VITE_IIOS_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8002";

type Worker = {
  availability?: string;
  cadence_minutes?: number;
  last_completed_at?: string | null;
  cadence_state?: string;
  market_phase?: string | null;
};

type CaseResult = {
  case_id?: string | null;
  ticker?: string | null;
  stage?: string | null;
  committee_disposition?: string | null;
  committee_confidence?: number | null;
  capital_stage?: string | null;
  capital_decision?: string | null;
  sizing_decision?: string | null;
  failed_checks?: string[];
  unmet_requirements?: string[];
  execution_id?: string | null;
};

type Operations = {
  generated_at?: string;
  portfolio?: {
    nav?: number | null;
    cash?: number | null;
    position_count?: number | null;
    transaction_count?: number | null;
  };
  observation?: Worker & {
    last_scan_status?: string | null;
    last_scan_count?: number | null;
    last_queue_count?: number | null;
    promoted_case_count?: number | null;
    latest_promoted_case?: {
      case_id?: string | null;
      ticker?: string | null;
      score?: number | null;
    } | null;
  };
  paper_trading?: Worker & {
    case_count_inspected?: number | null;
    gap_hunts_run?: number | null;
    paper_executions_created?: number | null;
    case_results?: CaseResult[];
    funnel?: {
      inspected?: number;
      research_blocked_or_waiting?: number;
      capital_or_authorization_path?: number;
      waiting_for_regular_session?: number;
      paper_positions_opened?: number;
      errors_or_fail_closed?: number;
    };
  };
  safety?: {
    paper_mode?: boolean;
    broker_connected?: boolean;
    live_capital_locked?: boolean;
    live_execution?: boolean;
  };
};

type ModelState = {
  id?: string;
  label?: string;
  provider?: string;
  availability?: string;
  configured?: boolean | null;
  observation_status?: string;
  latency_ms?: number | null;
};

type Overview = {
  generated_at?: string;
  data_state?: string;
  source_availability?: Record<string, { availability?: string; error_type?: string | null }>;
  council?: { models?: ModelState[] };
  safety?: { paper_mode?: boolean; live_capital_locked?: boolean };
};

type HealthTone = "good" | "warn" | "bad" | "unknown";
type HealthItem = { key:string; label:string; tone:HealthTone; state:string; detail:string };

type RadarRow = {
  key:string;
  ticker:string;
  score:number | null;
  stage:string;
  committee:string;
  why:string[];
  waiting:string[];
  caseId:string | null;
};

async function getJson<T>(path:string):Promise<T>{
  const response = await fetch(`${API}${path}`, { headers:{ Accept:"application/json" } });
  if(!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

function ageSeconds(value?:string|null):number|null{
  if(!value) return null;
  const time = new Date(value).getTime();
  if(Number.isNaN(time)) return null;
  return Math.max(0,(Date.now()-time)/1000);
}

function workerHealth(label:string, worker:Worker|undefined, endpointOk:boolean):HealthItem{
  if(!endpointOk) return {key:label,label,tone:"bad",state:"OFFLINE",detail:"Operations endpoint unavailable"};
  if(!worker) return {key:label,label,tone:"unknown",state:"UNKNOWN",detail:"No worker state exposed"};
  const cadence = Math.max(1, Number(worker.cadence_minutes ?? 15));
  const age = ageSeconds(worker.last_completed_at);
  const cadenceState = String(worker.cadence_state ?? "UNKNOWN").toUpperCase();
  const availability = String(worker.availability ?? "UNKNOWN").toUpperCase();
  if(availability.includes("OFFLINE") || availability.includes("ERROR") || cadenceState.includes("ERROR")){
    return {key:label,label,tone:"bad",state:"OFFLINE",detail:`${availability} · ${cadenceState}`};
  }
  if(age !== null && age > cadence*60*2){
    return {key:label,label,tone:"warn",state:"STALE",detail:`Last complete ${Math.round(age/60)}m ago`};
  }
  if(cadenceState.includes("ON_CADENCE") || cadenceState.includes("READY") || cadenceState.includes("ACTIVE")){
    return {key:label,label,tone:"good",state:"HEALTHY",detail:age===null?cadenceState:`Last complete ${Math.max(0,Math.round(age/60))}m ago`};
  }
  return {key:label,label,tone:"warn",state:cadenceState || "UNKNOWN",detail:availability};
}

function modelHealth(label:string, model:ModelState|undefined, overviewOk:boolean):HealthItem{
  if(!overviewOk) return {key:label,label,tone:"bad",state:"OFFLINE",detail:"Factory overview unavailable"};
  if(!model) return {key:label,label,tone:"unknown",state:"UNKNOWN",detail:"Telemetry not exposed by current real feed"};
  const availability=String(model.availability??"UNKNOWN").toUpperCase();
  const observation=String(model.observation_status??"UNKNOWN").toUpperCase();
  if(availability.includes("OFFLINE") || availability.includes("UNAVAILABLE")) return {key:label,label,tone:"bad",state:"OFFLINE",detail:observation};
  if(availability.includes("READY") || observation.includes("AVAILABLE") || observation.includes("COMPLETE")) return {key:label,label,tone:"good",state:"HEALTHY",detail:`${availability} · ${observation}`};
  if(availability.includes("CONFIGURED")) return {key:label,label,tone:"warn",state:"WAITING",detail:`${availability} · ${observation}`};
  return {key:label,label,tone:"unknown",state:availability,detail:observation};
}

function sourceHealth(label:string, source:{availability?:string;error_type?:string|null}|undefined, overviewOk:boolean):HealthItem{
  if(!overviewOk) return {key:label,label,tone:"bad",state:"OFFLINE",detail:"Factory overview unavailable"};
  if(!source) return {key:label,label,tone:"unknown",state:"UNKNOWN",detail:"Dedicated health source not exposed"};
  const state=String(source.availability??"UNKNOWN").toUpperCase();
  if(state==="AVAILABLE") return {key:label,label,tone:"good",state:"HEALTHY",detail:"Real backend source available"};
  if(state.includes("OFFLINE")) return {key:label,label,tone:"bad",state:"OFFLINE",detail:source.error_type??state};
  return {key:label,label,tone:"warn",state,detail:source.error_type??"Source state incomplete"};
}

function display(value?:string|null){return String(value??"UNKNOWN").replaceAll("_"," ");}

export default function Batch10BCommandLayer(){
  const [open,setOpen]=useState(true);
  const [operations,setOperations]=useState<Operations|null>(null);
  const [overview,setOverview]=useState<Overview|null>(null);
  const [opsError,setOpsError]=useState<string|null>(null);
  const [overviewError,setOverviewError]=useState<string|null>(null);
  const [expanded,setExpanded]=useState<string|null>(null);
  const [,setClock]=useState(0);

  useEffect(()=>{
    let disposed=false;
    const load=async()=>{try{const value=await getJson<Operations>("/paper-fund/operations");if(!disposed){setOperations(value);setOpsError(null)}}catch(error){if(!disposed)setOpsError(error instanceof Error?error.message:"operations unavailable")}};
    void load(); const timer=window.setInterval(()=>void load(),5000); return()=>{disposed=true;window.clearInterval(timer)};
  },[]);
  useEffect(()=>{
    let disposed=false;
    const load=async()=>{try{const value=await getJson<Overview>("/experience/factory-intelligence/overview");if(!disposed){setOverview(value);setOverviewError(null)}}catch(error){if(!disposed)setOverviewError(error instanceof Error?error.message:"overview unavailable")}};
    void load(); const timer=window.setInterval(()=>void load(),10000); return()=>{disposed=true;window.clearInterval(timer)};
  },[]);
  useEffect(()=>{const timer=window.setInterval(()=>setClock(v=>v+1),1000);return()=>window.clearInterval(timer)},[]);

  const models=overview?.council?.models??[];
  const findModel=(...needles:string[])=>models.find(model=>needles.some(n=>`${model.id??""} ${model.label??""} ${model.provider??""}`.toUpperCase().includes(n)));
  const opsOk=!opsError&&!!operations;
  const overviewOk=!overviewError&&!!overview;
  const factorySource=overview?.source_availability?.factory;
  const councilSource=overview?.source_availability?.council;

  const health:HealthItem[]=[
    modelHealth("GPT",findModel("OPENAI","GPT"),overviewOk),
    modelHealth("GROK",findModel("GROK","XAI"),overviewOk),
    modelHealth("GEMINI",findModel("GEMINI","GOOGLE"),overviewOk),
    workerHealth("9A",operations?.observation,opsOk),
    workerHealth("9B",operations?.paper_trading,opsOk),
    sourceHealth("COMMITTEE",councilSource??factorySource,overviewOk),
    sourceHealth("RISK",factorySource,overviewOk),
    operations?.safety?.paper_mode===true && operations?.safety?.live_execution===false
      ? {key:"PAPER FUND",label:"PAPER FUND",tone:"good",state:"HEALTHY",detail:`NAV ${operations?.portfolio?.nav?.toFixed(2)??"—"} · live locked`}
      : {key:"PAPER FUND",label:"PAPER FUND",tone:opsOk?"warn":"bad",state:opsOk?"CHECK":"OFFLINE",detail:opsOk?"Paper/live safety state incomplete":"Operations endpoint unavailable"},
    {key:"STORAGE",label:"STORAGE",tone:"unknown",state:"UNKNOWN",detail:"Dedicated storage heartbeat not exposed yet"},
    {key:"LEDGER",label:"LEDGER",tone:"unknown",state:"UNKNOWN",detail:"Dedicated ledger heartbeat not exposed yet"},
  ];

  const radar=useMemo<RadarRow[]>(()=>{
    const rows=new Map<string,RadarRow>();
    const promoted=operations?.observation?.latest_promoted_case;
    if(promoted?.ticker || promoted?.case_id){
      const key=promoted.case_id??promoted.ticker??"promotion";
      rows.set(key,{key,ticker:promoted.ticker??"NO TICKER",score:promoted.score??null,stage:"PROMOTED",committee:"PENDING / UNKNOWN",why:["9A promoted this case in the real observation feed."],waiting:["Detailed surfacing reason is not exposed by the current operations feed."],caseId:promoted.case_id??null});
    }
    for(const [index,row] of (operations?.paper_trading?.case_results??[]).entries()){
      const key=row.case_id??`${row.ticker??"case"}-${index}`;
      const failed=row.failed_checks??[];
      const unmet=row.unmet_requirements??[];
      const existing=rows.get(key);
      rows.set(key,{
        key,
        ticker:row.ticker??existing?.ticker??"NO TICKER",
        score:existing?.score??null,
        stage:display(row.stage??existing?.stage??"UNKNOWN"),
        committee:display(row.committee_disposition??"UNKNOWN"),
        why:failed.length||unmet.length?[...failed.map(v=>`Failed: ${display(v)}`),...unmet.map(v=>`Unmet: ${display(v)}`)]:existing?.why??["Current real feed does not expose a surfacing reason for this case."],
        waiting:unmet.length?unmet.map(display):failed.length?failed.map(display):["No additional requirement detail exposed."],
        caseId:row.case_id??existing?.caseId??null,
      });
    }
    return [...rows.values()].slice(0,10);
  },[operations]);

  const funnel=[
    ["UNIVERSE","—","not exposed by current feed"],
    ["SCANNED",operations?.observation?.last_scan_count??"—","latest 9A scan"],
    ["QUEUED",operations?.observation?.last_queue_count??"—","latest 9A queue"],
    ["PROMOTED",operations?.observation?.promoted_case_count??"—","9A promotions"],
    ["DEEP RESEARCH",operations?.paper_trading?.gap_hunts_run??"—","9B deepening"],
    ["COMMITTEE","—","exact count not exposed"],
    ["RISK","—","exact count not exposed"],
    ["PAPER",operations?.paper_trading?.paper_executions_created??"—","paper executions"],
  ] as const;

  return <section className={`b10b-command ${open?"open":"closed"}`}>
    <button className="b10b-command__toggle" type="button" onClick={()=>setOpen(v=>!v)}>
      <span>BATCH 10B · REAL COMMAND</span><strong>IIOS HEARTBEAT + LIVE RADAR</strong><em>{open?"COLLAPSE":"EXPAND"}</em>
    </button>
    {open?<div className="b10b-command__body">
      <header className="b10b-head"><div><span>GOVERNED TELEMETRY ONLY</span><h2>Real Intelligence Command Layer</h2><p>Health and activity are intentionally separate. Unknown stays unknown; no mock state is allowed here.</p></div><div className="b10b-safety"><strong>{operations?.safety?.live_capital_locked===true?"LIVE CAPITAL LOCKED":"LIVE STATE UNKNOWN"}</strong><span>BROKER {operations?.safety?.broker_connected===false?"FALSE":"UNKNOWN"} · PAPER {operations?.safety?.paper_mode===true?"TRUE":"UNKNOWN"}</span></div></header>

      {(opsError||overviewError)?<div className="b10b-errors">{opsError?<span>OPERATIONS: {opsError}</span>:null}{overviewError?<span>OVERVIEW: {overviewError}</span>:null}</div>:null}

      <div className="b10b-health">{health.map(item=><div className={`b10b-health__item ${item.tone}`} key={item.key} title={item.detail}><i/><span>{item.label}</span><strong>{item.state}</strong><small>{item.detail}</small></div>)}</div>

      <div className="b10b-activity"><div><span>9A ACTIVITY</span><strong>{operations?.observation?.last_scan_count??"—"} scanned · {operations?.observation?.last_queue_count??"—"} queued · {operations?.observation?.promoted_case_count??"—"} promoted</strong></div><div><span>9B ACTIVITY</span><strong>{operations?.paper_trading?.case_count_inspected??"—"} cases · {operations?.paper_trading?.gap_hunts_run??"—"} deepened · {operations?.paper_trading?.paper_executions_created??"—"} orders</strong></div></div>

      <div className="b10b-grid">
        <section className="b10b-panel"><header><div><span>REAL 9A / 9B CASES</span><h3>Live Radar</h3></div><strong>{radar.length} visible</strong></header><div className="b10b-radar">{radar.length?radar.map(row=><article key={row.key} className="b10b-radar__row"><button type="button" onClick={()=>setExpanded(expanded===row.key?null:row.key)}><div><strong>{row.ticker}</strong><span>{row.caseId??"NO CASE ID"}</span></div><b>{row.score??"—"}</b><em>{row.stage}</em><i>{row.committee}</i><u>{expanded===row.key?"CLOSE":"WHY / WHY NOT"}</u></button>{expanded===row.key?<div className="b10b-explain"><div><span>WHAT THE REAL FEED SAYS</span>{row.why.map((text,i)=><p key={i}>{text}</p>)}</div><div><span>WAITING / BLOCKERS</span>{row.waiting.map((text,i)=><p key={i}>{text}</p>)}</div><div><span>COMMITTEE</span><strong>{row.committee}</strong><small>No missing reason is inferred.</small></div></div>:null}</article>):<div className="b10b-empty">No real radar/case rows are exposed yet.</div>}</div></section>

        <section className="b10b-panel"><header><div><span>REAL COUNTS ONLY</span><h3>Governed Funnel</h3></div><strong>UNKNOWN ≠ ZERO</strong></header><div className="b10b-funnel">{funnel.map(([label,value,detail],index)=><div key={label} className="b10b-funnel__step"><span>{label}</span><strong>{value}</strong><small>{detail}</small>{index<funnel.length-1?<i>↓</i>:null}</div>)}</div></section>
      </div>

      <footer className="b10b-footer"><span>OPS UPDATED · {operations?.generated_at?new Date(operations.generated_at).toLocaleTimeString():"UNKNOWN"}</span><span>OVERVIEW UPDATED · {overview?.generated_at?new Date(overview.generated_at).toLocaleTimeString():"UNKNOWN"}</span><strong>NO FAKE GREEN LIGHTS · NO MOCK TELEMETRY</strong></footer>
    </div>:null}
  </section>;
}

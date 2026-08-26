import { useEffect, useMemo, useState } from "react";
import { getActiveCaseId, subscribeActiveCase } from "./activeCaseStore";

const API = "http://127.0.0.1:8002";

type DashboardCase = { case_id:string; topic:string; ticker?:string; health?:string; committee_disposition?:string; committee_confidence?:number; evidence_quality?:number; latest_evidence_count?:number; latest_action?:string; monitoring_enabled?:boolean; interval_minutes?:number; };
type History = { signal_ladder?: { current_stage?:string; next_requirements?:string[] } };
function pct(value?:number){return value===undefined||value===null?"—":`${Math.round(value*100)}%`;}
function label(value?:string){return String(value||"UNKNOWN").replaceAll("_"," ");}

export default function CasesCommandCard(){
  const[caseId,setCaseId]=useState<string|null>(()=>getActiveCaseId());
  const[cases,setCases]=useState<DashboardCase[]>([]);const[history,setHistory]=useState<History|null>(null);const[online,setOnline]=useState(false);
  useEffect(()=>subscribeActiveCase(setCaseId),[]);
  useEffect(()=>{let active=true;const load=async()=>{try{const dashboard=await fetch(`${API}/monitoring/dashboard`).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.json();}) as {cases?:DashboardCase[]};let nextHistory:History|null=null;if(caseId){const response=await fetch(`${API}/history/${caseId}`);if(response.ok)nextHistory=await response.json() as History;}if(!active)return;setCases(dashboard.cases||[]);setHistory(nextHistory);setOnline(true);}catch{if(active)setOnline(false);}};void load();const timer=window.setInterval(()=>void load(),15000);return()=>{active=false;window.clearInterval(timer);};},[caseId]);
  const activeCase=useMemo(()=>cases.find(item=>item.case_id===caseId)??null,[cases,caseId]);const nextAction=history?.signal_ladder?.next_requirements?.[0]||activeCase?.latest_action||"Continue governed monitoring";
  return <section className="cases-command-card"><div className="cases-command-head"><div><div className="cases-command-eyebrow">ACTIVE UNDERWRITING COMMAND</div><h2>{activeCase?.ticker||"NO CASE"} · {activeCase?label(activeCase.health):"SELECT A CASE"}</h2><p>{activeCase?.topic||"Select a case from Surveillance to load the governed underwriting state."}</p></div><div className={online?"cases-command-live":"cases-command-offline"}>{online?"LIVE CASE STATE":"STATE OFFLINE"}</div></div><div className="cases-command-metrics"><div><span>Committee</span><strong>{label(activeCase?.committee_disposition)}</strong></div><div><span>Confidence</span><strong>{pct(activeCase?.committee_confidence)}</strong></div><div><span>Evidence</span><strong>{pct(activeCase?.evidence_quality)}{activeCase?.latest_evidence_count!==undefined?` · ${activeCase.latest_evidence_count}`:""}</strong></div><div><span>Signal Stage</span><strong>{label(history?.signal_ladder?.current_stage)}</strong></div><div><span>Watch</span><strong>{activeCase?.monitoring_enabled?`${activeCase.interval_minutes??"—"}m ARMED`:"OFF"}</strong></div></div><div className="cases-command-next"><span>NEXT GOVERNED ACTION</span><strong>{nextAction}</strong></div></section>;
}

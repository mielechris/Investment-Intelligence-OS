import { useEffect, useState } from "react";
const API = "http://127.0.0.1:8002";
export default function JesseIntelligencePanel() {
  const [data,setData]=useState<any>({});
  useEffect(()=>{let active=true; const load=async()=>{try{
    const [s,f,t,d]=await Promise.all([
      fetch(`${API}/intelligence/institutional-research/sector-sentiment`).then(r=>r.json()),
      fetch(`${API}/intelligence/monetary-policy/status`).then(r=>r.json()),
      fetch(`${API}/intelligence/tariff-transmission/status`).then(r=>r.json()),
      fetch(`${API}/intelligence/dislocation/status`).then(r=>r.json())
    ]); if(active)setData({s,f,t,d});
  }catch{}}; void load(); const timer=window.setInterval(()=>void load(),15000); return()=>{active=false;window.clearInterval(timer)}},[]);
  const card={border:"1px solid #2b3742",borderRadius:"10px",background:"#080d12",padding:"15px"} as const;
  return <section style={{maxWidth:"1110px",margin:"0 auto 28px",padding:"22px",border:"1px solid #4e4731",borderRadius:"14px",background:"rgba(8,12,17,.96)",color:"#eef2f5"}}>
    <div style={{fontSize:"10px",letterSpacing:"2px",color:"#a88a46"}}>JESSE INTELLIGENCE FLOOR - CONTEXT ONLY - PAPER / SHADOW</div>
    <h2 style={{margin:"8px 0 4px"}}>Institutional - Fed - Tariffs - Dislocations</h2>
    <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(260px,1fr))",gap:"12px",marginTop:"18px"}}>
      <div style={card}><b>Institutional sector sentiment</b><div>{data.s?.report_count ?? 0} normalized report(s)</div>
        {(data.s?.sectors||[]).slice(0,4).map((x:any)=><div key={x.sector}>{x.sector}: {x.sentiment}</div>)}</div>
      <div style={card}><b>Monetary policy probability</b><div>{data.f?.latest_snapshot?.most_likely_scenario || "NO SNAPSHOT"}</div>
        <div>Historical reactions: {data.f?.reaction_count ?? 0}</div></div>
      <div style={card}><b>Tariff transmission</b><div>{data.t?.latest_snapshot?.event_count ?? 0} event(s)</div>
        {(data.t?.latest_snapshot?.sector_impacts||[]).slice(0,4).map((x:any)=><div key={x.sector}>{x.sector}: {x.direction}</div>)}</div>
      <div style={card}><b>Daily dislocation scanner</b><div>{data.d?.latest_scan?.loser_count ?? 0} loser(s) reviewed</div>
        {(data.d?.latest_scan?.top_three||[]).map((x:any)=><div key={x.ticker}>{x.ticker} - {x.recommendation} - strength {x.financial_strength_score}</div>)}</div>
    </div>
  </section>
}

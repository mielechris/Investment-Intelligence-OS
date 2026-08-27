import "./previewApiBridge8G";
import { useEffect, useMemo, useState } from "react";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import JesseStrategyPanel from "./JesseStrategyPanel";
import SpecialistDeskFloor from "./SpecialistDeskFloor";
import MockTradingFactory from "./MockTradingFactory";
import ThesisIntegrityCommand from "./ThesisIntegrityCommand";
import ThesisCapitalConsequenceMatrix from "./ThesisCapitalConsequenceMatrix";
import PortfolioThesisWarRoom from "./PortfolioThesisWarRoom";
import JudgmentBankWorkspace from "./JudgmentBankWorkspace";
import JudgmentLibraryBrowser from "./JudgmentLibraryBrowser";
import ExecutiveShowcase from "./ExecutiveShowcase";
import { ACTIVE_CASE_EVENT, ACTIVE_CASE_KEY } from "./activeCaseStore";
import "./stateLanguage.css";
import "./deepIntelligence.css";
import "./warRoomExperience.css";
import "./executiveShowcase.css";
import "./FactoryIntelligenceExperienceShell.css";

type DeepRoom = "factory" | "thesis" | "judgment" | "executive";
type FactoryMode = "REAL" | "MOCK";
type CaseMeta = { case_id:string; ticker?:string|null; topic?:string|null };

const API="http://127.0.0.1:8002";
const ROOMS: Array<{ key: DeepRoom; label: string; detail: string }> = [
  { key: "factory", label: "Factory Theater", detail: "Mob / neon / MAX" },
  { key: "thesis", label: "Thesis War Room", detail: "Integrity → capital" },
  { key: "judgment", label: "Judgment Library", detail: "Human calibration" },
  { key: "executive", label: "Executive View", detail: "Boardroom briefing" },
];

export default function FactoryIntelligenceExperienceShell() {
  const [open, setOpen] = useState(false);
  const [room, setRoom] = useState<DeepRoom>("factory");
  const [factoryMode, setFactoryMode] = useState<FactoryMode>("REAL");
  const [activeCaseId,setActiveCaseId]=useState<string|null>(()=>window.localStorage.getItem(ACTIVE_CASE_KEY));
  const [cases,setCases]=useState<CaseMeta[]>([]);

  // Batch 8G owns active-case selection. It writes localStorage directly in the
  // same tab, which does not emit the browser `storage` event. This bridge emits
  // the X0-X6 synchronization event only when the 8G-selected case actually
  // changes. It does not select, create, or mutate a case.
  useEffect(() => {
    let previous = window.localStorage.getItem(ACTIVE_CASE_KEY);
    const timer = window.setInterval(() => {
      const current = window.localStorage.getItem(ACTIVE_CASE_KEY);
      if (current === previous) return;
      previous = current;
      setActiveCaseId(current);
      window.dispatchEvent(
        new CustomEvent(ACTIVE_CASE_EVENT, { detail: { caseId: current } }),
      );
    }, 500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(()=>{
    let live=true;
    const load=async()=>{try{const response=await fetch(`${API}/experience/factory-intelligence/overview`);if(!response.ok)return;const payload=await response.json() as{cases?:CaseMeta[]};if(live)setCases(payload.cases||[]);}catch{/* visible case ID remains available even if label lookup fails */}};
    const initial=window.setTimeout(()=>void load(),0);
    const timer=window.setInterval(()=>void load(),10000);
    return()=>{live=false;window.clearTimeout(initial);window.clearInterval(timer);};
  },[]);

  const activeCase=useMemo(()=>cases.find(item=>item.case_id===activeCaseId)??null,[cases,activeCaseId]);
  const activeCaseLabel=activeCase?.ticker||activeCaseId?.slice(-8)||"NONE";

  return (
    <div className="fi-x-shell">
      <FactoryIntelligenceUI />
      <JesseStrategyPanel />

      <div className={`fi-x-dock ${open ? "open" : ""}`}>
        <button
          type="button"
          className="fi-x-master-toggle"
          onClick={() => setOpen((value) => !value)}
        >
          <span>X0–X6</span>
          <strong>{open ? "CLOSE DEEP LAYER" : "OPEN DEEP INTELLIGENCE"}</strong>
        </button>
        {open ? (
          <div className="fi-x-dock-rooms">
            {ROOMS.map((item) => (
              <button
                type="button"
                key={item.key}
                className={room === item.key ? "active" : ""}
                onClick={() => setRoom(item.key)}
              >
                <strong>{item.label}</strong>
                <span>{item.detail}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {open ? (
        <aside className="fi-x-layer" aria-label="IIOS X0-X6 deep intelligence layer">
          <header className="fi-x-layer-head">
            <div>
              <span>IIOS · X0–X6 DEEP INTELLIGENCE</span>
              <h2>{ROOMS.find((item) => item.key === room)?.label}</h2>
              <p>Batch 8G remains the authoritative operating shell. The mock theater is a separate browser-only experience and never writes into governed telemetry, learning, paper execution, or live-capital paths.</p>
            </div>
            <div className="fi-x-layer-safety">
              <span className="fi-x-layer-case">ACTIVE CASE · {activeCaseLabel}</span>
              <span>{factoryMode === "MOCK" && room === "factory" ? "MOCK / DEMO" : "PAPER / SHADOW"}</span>
              <strong>LIVE CAPITAL LOCKED</strong>
            </div>
          </header>

          <div className={`fi-x-layer-body fi-x-layer-body--${room}`}>
            {room === "factory" ? (
              <>
                <div className="fi-x-section-note">
                  <span>X3 · FACTORY THEATER</span>
                  <strong>{factoryMode === "REAL" ? "Real telemetry. No fake busy state." : "Mob theater alive. Mock data isolated from the brain."}</strong>
                </div>
                <div style={{display:"flex",gap:8,marginBottom:10,fontFamily:"ui-monospace, SFMono-Regular, Menlo, monospace"}}>
                  <button
                    type="button"
                    onClick={()=>setFactoryMode("REAL")}
                    style={{border:"1px solid #6f481d",background:factoryMode==="REAL"?"#1b130a":"#070604",color:factoryMode==="REAL"?"#67df75":"#8a795c",padding:"7px 11px",cursor:"pointer"}}
                  >REAL TELEMETRY</button>
                  <button
                    type="button"
                    onClick={()=>setFactoryMode("MOCK")}
                    style={{border:"1px solid #6f481d",background:factoryMode==="MOCK"?"#1b130a":"#070604",color:factoryMode==="MOCK"?"#f2b95e":"#8a795c",padding:"7px 11px",cursor:"pointer"}}
                  >MOCK TRADING THEATER</button>
                  <span style={{alignSelf:"center",fontSize:9,color:factoryMode==="MOCK"?"#f05454":"#67df75"}}>{factoryMode === "MOCK" ? "DEMO ISOLATION ON" : "GOVERNED SOURCE OF TRUTH"}</span>
                </div>
                {factoryMode === "REAL" ? <SpecialistDeskFloor /> : <MockTradingFactory />}
              </>
            ) : null}

            {room === "thesis" ? (
              <>
                <ThesisIntegrityCommand />
                <ThesisCapitalConsequenceMatrix />
                <PortfolioThesisWarRoom />
              </>
            ) : null}

            {room === "judgment" ? (
              <>
                <JudgmentBankWorkspace />
                <JudgmentLibraryBrowser />
              </>
            ) : null}

            {room === "executive" ? <ExecutiveShowcase /> : null}
          </div>
        </aside>
      ) : null}
    </div>
  );
}

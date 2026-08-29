import { useState } from "react";
import AgentPerformanceLeague from "./AgentPerformanceLeague";
import CharacterStoryEngine from "./CharacterStoryEngine";
import ChiefIntelligenceOffice from "./ChiefIntelligenceOffice";
import ChiefIntelligenceOfficeV2 from "./ChiefIntelligenceOfficeV2";
import DailyFactoryEpisode from "./DailyFactoryEpisode";
import DataExpansionFactory from "./DataExpansionFactory";
import ExperimentABLaboratory from "./ExperimentABLaboratory";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import HistoricalEventReconstruction from "./HistoricalEventReconstruction";
import HistoricalMacroRegimeLibrary from "./HistoricalMacroRegimeLibrary";
import HistoricalMarketIntelligence from "./HistoricalMarketIntelligence";
import InteractiveCaseTheater from "./InteractiveCaseTheater";
import LivingFactoryExperience from "./LivingFactoryExperience";
import LivingFactoryFloorV2 from "./LivingFactoryFloorV2";
import MarketRegimeIntelligence from "./MarketRegimeIntelligence";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import MeasurementHealthSuperbatch from "./MeasurementHealthSuperbatch";
import OperatingSuperbatch from "./OperatingSuperbatch";
import QualificationWatch from "./QualificationWatch";
import ReadinessSuperbatch from "./ReadinessSuperbatch";
import "./LiveFactoryBrowser.css";
import "./Batch9MVisualSeal.css";

type BrowserView = "floor" | "control";

export default function LiveFactoryBrowser() {
  const [view, setView] = useState<BrowserView>("floor");

  return (
    <div className="lfb-shell">
      <div className="lfb-preview-banner">
        <div>
          <span>BATCH 9L-V2 · LIVING FACTORY FLOOR</span>
          <strong>Spatial floor · persisted case packets · MAX + eight specialist desks · live event tape</strong>
        </div>
        <div>
          <span>10L–10M + ALL PRESERVED FACTORY SYSTEMS · BACKEND 8002 UNCHANGED</span>
          <strong>LIVE EXECUTION FALSE</strong>
        </div>
      </div>

      <nav className="lfb-viewbar" aria-label="Investment factory browser view">
        <div className="lfb-viewbar-copy">
          <span>IIOS EXPERIENCE</span>
          <strong>{view === "floor" ? "Factory Floor" : "Control Room"}</strong>
        </div>
        <div className="lfb-view-switch">
          <button
            className={`lfb-view-button ${view === "floor" ? "is-active" : ""}`}
            onClick={() => setView("floor")}
            type="button"
          >
            <span>01</span>
            <strong>FACTORY FLOOR</strong>
            <em>living spatial view</em>
          </button>
          <button
            className={`lfb-view-button ${view === "control" ? "is-active" : ""}`}
            onClick={() => setView("control")}
            type="button"
          >
            <span>02</span>
            <strong>CONTROL ROOM</strong>
            <em>traceability + diagnostics</em>
          </button>
        </div>
        <div className="lfb-view-truth">
          <i aria-hidden="true" />
          <span>AMBIENT MOTION IS UI ONLY · PERSISTED STATE DRIVES SUBSTANTIVE ACTIVITY</span>
        </div>
      </nav>

      {view === "floor" ? (
        <LivingFactoryFloorV2 />
      ) : (
        <div className="lfb-control-stack">
          <LivingFactoryExperience />
          <div className="lfb-divider"><span>9M CHARACTER & STORY ENGINE · PERSISTED EVENTS ONLY</span></div><CharacterStoryEngine />
          <div className="lfb-divider"><span>9N INTERACTIVE CASE THEATER · REPLAY DOES NOT EXECUTE</span></div><InteractiveCaseTheater />
          <div className="lfb-divider"><span>9O DAILY FACTORY EPISODE · REPORT ONLY</span></div><DailyFactoryEpisode />
          <div className="lfb-divider"><span>9P CHIEF INTELLIGENCE OFFICE V1 · PRESERVED</span></div><ChiefIntelligenceOffice />
          <div className="lfb-divider"><span>9Q EXPERIMENT & A/B LABORATORY · SHADOW ONLY</span></div><ExperimentABLaboratory />
          <div className="lfb-divider"><span>9R DATA EXPANSION FACTORY · RESEARCH + SHADOW ONLY</span></div><DataExpansionFactory />
          <div className="lfb-divider"><span>9S AGENT PERFORMANCE LEAGUE · SCOREBOARD ONLY</span></div><AgentPerformanceLeague />
          <div className="lfb-divider"><span>9T MARKET REGIME INTELLIGENCE · CLASSIFICATION ONLY</span></div><MarketRegimeIntelligence />
          <div className="lfb-divider"><span>10A–10C UNIFIED OPERATING SUPERBATCH · PAPER ONLY</span></div><OperatingSuperbatch />
          <div className="lfb-divider"><span>10D–10F CAPITAL PRESERVATION / READINESS / FIRM OS</span></div><ReadinessSuperbatch />
          <div className="lfb-divider"><span>10G PAPER QUALIFICATION CAMPAIGN · WATCH ONLY</span></div><QualificationWatch />
          <div className="lfb-divider"><span>10H HISTORICAL MARKET INTELLIGENCE · 24/7 READ-ONLY RESEARCH</span></div><HistoricalMarketIntelligence />
          <div className="lfb-divider"><span>10I CHIEF INTELLIGENCE OFFICE V2 · WHOLE-STACK ADVISORY</span></div><ChiefIntelligenceOfficeV2 />
          <div className="lfb-divider"><span>10J HISTORICAL EVENT RECONSTRUCTION · ASSOCIATION ≠ CAUSATION</span></div><HistoricalEventReconstruction />
          <div className="lfb-divider"><span>10K HISTORICAL MACRO + REGIME · DIRECT TREASURY + CBOE NORMALIZATION</span></div><HistoricalMacroRegimeLibrary />
          <div className="lfb-divider"><span>10L–10M BENCHMARK ATTRIBUTION + DATA HEALTH · MEASUREMENT / OBSERVABILITY ONLY</span></div><MeasurementHealthSuperbatch />
          <div className="lfb-divider"><span>9K VALIDATION STACK · PRESERVED</span></div><MarketValidationStackPanel />
          <div className="lfb-divider"><span>EXISTING FACTORY INTELLIGENCE UI · PRESERVED</span></div><FactoryIntelligenceUI />
        </div>
      )}
    </div>
  );
}

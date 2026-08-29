import AgentPerformanceLeague from "./AgentPerformanceLeague";
import CharacterStoryEngine from "./CharacterStoryEngine";
import ChiefIntelligenceOffice from "./ChiefIntelligenceOffice";
import DailyFactoryEpisode from "./DailyFactoryEpisode";
import DataExpansionFactory from "./DataExpansionFactory";
import ExperimentABLaboratory from "./ExperimentABLaboratory";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import InteractiveCaseTheater from "./InteractiveCaseTheater";
import LivingFactoryExperience from "./LivingFactoryExperience";
import MarketRegimeIntelligence from "./MarketRegimeIntelligence";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import OperatingSuperbatch from "./OperatingSuperbatch";
import ReadinessSuperbatch from "./ReadinessSuperbatch";
import "./LiveFactoryBrowser.css";
import "./Batch9MVisualSeal.css";

export default function LiveFactoryBrowser() {
  return (
    <div className="lfb-shell">
      <div className="lfb-preview-banner">
        <div><span>BATCH 10D–10F · READINESS SUPERBATCH</span><strong>Capital preservation · governed readiness · institutional firm OS</strong></div>
        <div><span>10A–10C OPERATING SUPERBATCH PRESERVED · BACKEND 8002 UNCHANGED</span><strong>LIVE EXECUTION FALSE</strong></div>
      </div>
      <LivingFactoryExperience />
      <div className="lfb-divider"><span>9M CHARACTER & STORY ENGINE · PERSISTED EVENTS ONLY</span></div><CharacterStoryEngine />
      <div className="lfb-divider"><span>9N INTERACTIVE CASE THEATER · REPLAY DOES NOT EXECUTE</span></div><InteractiveCaseTheater />
      <div className="lfb-divider"><span>9O DAILY FACTORY EPISODE · REPORT ONLY</span></div><DailyFactoryEpisode />
      <div className="lfb-divider"><span>9P CHIEF INTELLIGENCE OFFICE · ADVISORY ONLY</span></div><ChiefIntelligenceOffice />
      <div className="lfb-divider"><span>9Q EXPERIMENT & A/B LABORATORY · SHADOW ONLY</span></div><ExperimentABLaboratory />
      <div className="lfb-divider"><span>9R DATA EXPANSION FACTORY · RESEARCH + SHADOW ONLY</span></div><DataExpansionFactory />
      <div className="lfb-divider"><span>9S AGENT PERFORMANCE LEAGUE · SCOREBOARD ONLY</span></div><AgentPerformanceLeague />
      <div className="lfb-divider"><span>9T MARKET REGIME INTELLIGENCE · CLASSIFICATION ONLY</span></div><MarketRegimeIntelligence />
      <div className="lfb-divider"><span>10A–10C UNIFIED OPERATING SUPERBATCH · PAPER ONLY</span></div><OperatingSuperbatch />
      <div className="lfb-divider"><span>10D–10F CAPITAL PRESERVATION / READINESS / FIRM OS</span></div><ReadinessSuperbatch />
      <div className="lfb-divider"><span>9K VALIDATION STACK · PRESERVED</span></div><MarketValidationStackPanel />
      <div className="lfb-divider"><span>EXISTING FACTORY INTELLIGENCE UI · PRESERVED</span></div><FactoryIntelligenceUI />
    </div>
  );
}

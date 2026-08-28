import CharacterStoryEngine from "./CharacterStoryEngine";
import DailyFactoryEpisode from "./DailyFactoryEpisode";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import InteractiveCaseTheater from "./InteractiveCaseTheater";
import LivingFactoryExperience from "./LivingFactoryExperience";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import "./LiveFactoryBrowser.css";
import "./Batch9MVisualSeal.css";

export default function LiveFactoryBrowser() {
  return (
    <div className="lfb-shell">
      <div className="lfb-preview-banner">
        <div>
          <span>BATCH 9O · DAILY FACTORY EPISODE</span>
          <strong>Evidence-backed daily close · measured calls, misses, saves and learning</strong>
        </div>
        <div>
          <span>9N CASE THEATER PRESERVED · BACKEND 8002 UNCHANGED</span>
          <strong>LIVE EXECUTION FALSE</strong>
        </div>
      </div>
      <LivingFactoryExperience />
      <div className="lfb-divider">
        <span>9M CHARACTER & STORY ENGINE · PERSISTED EVENTS ONLY</span>
      </div>
      <CharacterStoryEngine />
      <div className="lfb-divider">
        <span>9N INTERACTIVE CASE THEATER · REPLAY DOES NOT EXECUTE</span>
      </div>
      <InteractiveCaseTheater />
      <div className="lfb-divider">
        <span>9O DAILY FACTORY EPISODE · REPORT ONLY</span>
      </div>
      <DailyFactoryEpisode />
      <div className="lfb-divider">
        <span>9K VALIDATION STACK · PRESERVED</span>
      </div>
      <MarketValidationStackPanel />
      <div className="lfb-divider">
        <span>EXISTING FACTORY INTELLIGENCE UI · PRESERVED</span>
      </div>
      <FactoryIntelligenceUI />
    </div>
  );
}

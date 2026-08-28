import CharacterStoryEngine from "./CharacterStoryEngine";
import DailyFactoryEpisode from "./DailyFactoryEpisode";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import InteractiveCaseTheater from "./InteractiveCaseTheater";
import LivingFactoryExperience from "./LivingFactoryExperience";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import "./LiveFactoryBrowser.css";

export default function LiveFactoryBrowser() {
  return (
    <div className="lfb-shell">
      <div className="lfb-preview-banner">
        <div>
          <span>BATCH 9O · DAILY FACTORY EPISODE</span>
          <strong>Persisted daily story · best calls · misses · saves · dumb calls · paper performance · learning</strong>
        </div>
        <div>
          <span>9L PROVENANCE + 9M STORY + 9N REPLAY PRESERVED · BACKEND 8002 UNCHANGED</span>
          <strong>LIVE EXECUTION FALSE</strong>
        </div>
      </div>
      <LivingFactoryExperience />
      <div className="lfb-divider">
        <span>9M CHARACTER & STORY ENGINE · PERSISTED EVENTS ONLY</span>
      </div>
      <CharacterStoryEngine />
      <div className="lfb-divider">
        <span>9N INTERACTIVE CASE THEATER · REPLAY CURSOR ONLY</span>
      </div>
      <InteractiveCaseTheater />
      <div className="lfb-divider">
        <span>9O DAILY FACTORY EPISODE · READ-ONLY REPORT</span>
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

import CharacterStoryEngine from "./CharacterStoryEngine";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import LivingFactoryExperience from "./LivingFactoryExperience";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import "./LiveFactoryBrowser.css";

export default function LiveFactoryBrowser() {
  return (
    <div className="lfb-shell">
      <div className="lfb-preview-banner">
        <div>
          <span>BATCH 9M · CHARACTER & STORY ENGINE</span>
          <strong>Persistent personalities · event-bound debate · dark/adult factory commentary</strong>
        </div>
        <div>
          <span>9L PROVENANCE PRESERVED · BACKEND 8002 UNCHANGED</span>
          <strong>LIVE EXECUTION FALSE</strong>
        </div>
      </div>
      <LivingFactoryExperience />
      <div className="lfb-divider">
        <span>9M CHARACTER & STORY ENGINE · PERSISTED EVENTS ONLY</span>
      </div>
      <CharacterStoryEngine />
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

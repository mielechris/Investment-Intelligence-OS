import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import LivingFactoryExperience from "./LivingFactoryExperience";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import "./LiveFactoryBrowser.css";

export default function LiveFactoryBrowser() {
  return (
    <div className="lfb-shell">
      <div className="lfb-preview-banner">
        <div>
          <span>BATCH 9L · LIVING FACTORY / PROVENANCE</span>
          <strong>Event-driven characters · traceable signal lineage · 9G/9H/9I/9J inside the floor</strong>
        </div>
        <div>
          <span>BACKEND 8002 UNCHANGED · GET-ONLY SIDECAR</span>
          <strong>LIVE EXECUTION FALSE</strong>
        </div>
      </div>
      <LivingFactoryExperience />
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

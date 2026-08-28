import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import "./LiveFactoryBrowser.css";

export default function LiveFactoryBrowser() {
  return (
    <div className="lfb-shell">
      <div className="lfb-preview-banner">
        <div>
          <span>BATCH 9K · READ-ONLY PREVIEW</span>
          <strong>Live market stack above · Existing factory intelligence below</strong>
        </div>
        <div>
          <span>BACKEND 8002 UNCHANGED</span>
          <strong>LIVE EXECUTION FALSE</strong>
        </div>
      </div>
      <MarketValidationStackPanel />
      <div className="lfb-divider">
        <span>LIVE FACTORY INTELLIGENCE UI</span>
      </div>
      <FactoryIntelligenceUI />
    </div>
  );
}

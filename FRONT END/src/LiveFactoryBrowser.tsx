import { useState, type ReactNode } from "react";
import AgentPerformanceLeague from "./AgentPerformanceLeague";
import CharacterStoryEngine from "./CharacterStoryEngine";
import ChiefIntelligenceOffice from "./ChiefIntelligenceOffice";
import ChiefIntelligenceOfficeV2 from "./ChiefIntelligenceOfficeV2";
import CinematicFactoryCommandDeck from "./CinematicFactoryCommandDeck";
import CinematicFactorySceneStrip from "./CinematicFactorySceneStrip";
import DailyFactoryEpisode from "./DailyFactoryEpisode";
import DataExpansionFactory from "./DataExpansionFactory";
import ExperimentABLaboratory from "./ExperimentABLaboratory";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI";
import HistoricalEventReconstruction from "./HistoricalEventReconstruction";
import HistoricalMacroRegimeLibrary from "./HistoricalMacroRegimeLibrary";
import HistoricalMarketIntelligence from "./HistoricalMarketIntelligence";
import InteractiveCaseTheater from "./InteractiveCaseTheater";
import LivingCharacterDirectorV7 from "./LivingCharacterDirectorV7";
import LivingFactoryExperience from "./LivingFactoryExperience";
import LivingFactorySpatialFloor from "./LivingFactorySpatialFloor";
import MarketRegimeIntelligence from "./MarketRegimeIntelligence";
import MarketValidationStackPanel from "./MarketValidationStackPanel";
import MeasurementHealthSuperbatch from "./MeasurementHealthSuperbatch";
import OperatingSuperbatch from "./OperatingSuperbatch";
import QualificationWatch from "./QualificationWatch";
import ReadinessSuperbatch from "./ReadinessSuperbatch";
import "./LiveFactoryBrowser.css";
import "./Batch9MVisualSeal.css";
import "./LivingFactorySpatialFloorV21.css";
import "./LivingFactorySpatialFloorV22.css";
import "./LivingFactorySpatialFloorV23.css";
import "./LivingFactorySpatialFloorV24.css";
import "./LivingFactorySpatialFloorV24Cast.css";
import "./LivingFactorySpatialFloorV25.css";
import "./CinematicFactoryThemeV6.css";
import "./CinematicAvatarPortraitsV6.css";
import "./CinematicFactoryFidelityV6.css";
import "./CinematicPortraitIntegrationV6.css";
import "./CinematicFactoryFinalPolishV6.css";

type BrowserView = "floor" | "control";

type ControlModule = {
  id: string;
  code: string;
  title: string;
  subtitle: string;
  truth: string;
  render: () => ReactNode;
};

const CONTROL_MODULES: ControlModule[] = [
  {
    id: "factory-provenance",
    code: "9L",
    title: "Living Factory & Signal Provenance",
    subtitle: "Traceability, source lineage, persisted movement, and read-only factory state.",
    truth: "PERSISTED EVENTS ONLY",
    render: () => <LivingFactoryExperience />,
  },
  {
    id: "character-story",
    code: "9M",
    title: "Character & Story Engine",
    subtitle: "The recurring cast narrates real events without replacing raw model output.",
    truth: "NARRATIVE ≠ MODEL OUTPUT",
    render: () => <CharacterStoryEngine />,
  },
  {
    id: "case-theater",
    code: "9N",
    title: "Interactive Case Theater",
    subtitle: "Replay a governed case chain without creating orders or altering state.",
    truth: "REPLAY DOES NOT EXECUTE",
    render: () => <InteractiveCaseTheater />,
  },
  {
    id: "daily-episode",
    code: "9O",
    title: "Daily Factory Episode",
    subtitle: "A report-only account of what the factory actually persisted.",
    truth: "REPORT ONLY",
    render: () => <DailyFactoryEpisode />,
  },
  {
    id: "chief-office-v1",
    code: "9P",
    title: "Chief Intelligence Office I",
    subtitle: "Preserved whole-factory advisory and operating summary.",
    truth: "ADVISORY ONLY",
    render: () => <ChiefIntelligenceOffice />,
  },
  {
    id: "experiment-lab",
    code: "9Q",
    title: "Experiment & A/B Laboratory",
    subtitle: "Counterfactual comparison and shadow experiments outside capital authority.",
    truth: "SHADOW ONLY",
    render: () => <ExperimentABLaboratory />,
  },
  {
    id: "data-expansion",
    code: "9R",
    title: "Data Expansion Factory",
    subtitle: "Research-source growth, coverage, and governed enrichment.",
    truth: "RESEARCH + SHADOW",
    render: () => <DataExpansionFactory />,
  },
  {
    id: "agent-league",
    code: "9S",
    title: "Agent Performance League",
    subtitle: "Calibration and scorekeeping without changing agent authority.",
    truth: "SCOREBOARD ONLY",
    render: () => <AgentPerformanceLeague />,
  },
  {
    id: "market-regime",
    code: "9T",
    title: "Market Regime Intelligence",
    subtitle: "Current regime classification, context, and historical comparison.",
    truth: "CLASSIFICATION ONLY",
    render: () => <MarketRegimeIntelligence />,
  },
  {
    id: "operating-superbatch",
    code: "10A–C",
    title: "Unified Operating Superbatch",
    subtitle: "Operating cadence, paper-capital controls, and governed supervision.",
    truth: "PAPER ONLY",
    render: () => <OperatingSuperbatch />,
  },
  {
    id: "readiness-superbatch",
    code: "10D–F",
    title: "Capital Preservation & Readiness",
    subtitle: "Stress controls, release gates, institutional readiness, and firm operating discipline.",
    truth: "CAPITAL GATES PRESERVED",
    render: () => <ReadinessSuperbatch />,
  },
  {
    id: "qualification-watch",
    code: "10G",
    title: "Paper Qualification Campaign",
    subtitle: "Qualification evidence and readiness observation before any capital escalation.",
    truth: "WATCH ONLY",
    render: () => <QualificationWatch />,
  },
  {
    id: "historical-intelligence",
    code: "10H",
    title: "Historical Market Intelligence",
    subtitle: "Read-only historical research operating around the clock.",
    truth: "24/7 READ ONLY",
    render: () => <HistoricalMarketIntelligence />,
  },
  {
    id: "chief-office-v2",
    code: "10I",
    title: "Chief Intelligence Office II",
    subtitle: "Whole-stack advisory view across cases, evidence, risk, portfolio, and learning.",
    truth: "ADVISORY ONLY",
    render: () => <ChiefIntelligenceOfficeV2 />,
  },
  {
    id: "event-reconstruction",
    code: "10J",
    title: "Historical Event Reconstruction",
    subtitle: "Reconstruct market sequences while preserving the line between association and causation.",
    truth: "ASSOCIATION ≠ CAUSATION",
    render: () => <HistoricalEventReconstruction />,
  },
  {
    id: "macro-library",
    code: "10K",
    title: "Historical Macro & Regime Library",
    subtitle: "Normalized Treasury, volatility, macro, and regime history.",
    truth: "DIRECT-SOURCE NORMALIZATION",
    render: () => <HistoricalMacroRegimeLibrary />,
  },
  {
    id: "measurement-health",
    code: "10L–M",
    title: "Measurement & Data Health",
    subtitle: "Attribution, freshness, consumption, cost, and observability controls.",
    truth: "MEASUREMENT ONLY",
    render: () => <MeasurementHealthSuperbatch />,
  },
  {
    id: "validation-stack",
    code: "9K",
    title: "Market Validation Stack",
    subtitle: "Independent grading, shadow strategy, outcome learning, and telemetry validation.",
    truth: "VALIDATION PRESERVED",
    render: () => <MarketValidationStackPanel />,
  },
  {
    id: "factory-intelligence",
    code: "8G",
    title: "Factory Intelligence UI",
    subtitle: "The preserved operational intelligence surface beneath the cinematic shell.",
    truth: "SOURCE SYSTEM PRESERVED",
    render: () => <FactoryIntelligenceUI />,
  },
];

export default function LiveFactoryBrowser() {
  const [view, setView] = useState<BrowserView>("floor");

  return (
    <div className="lfb-shell cinematic-v6 cinematic-v7">
      <div className="lfb-preview-banner">
        <div>
          <span>BATCH 9L-V7 · LIVING CHARACTER FACTORY</span>
          <strong>Frozen V6 cinematic headquarters · event-bound cast director · persisted IIOS state remains authoritative</strong>
        </div>
        <div>
          <span>V6 VISUAL BASE PRESERVED · BACKEND 8002 UNCHANGED</span>
          <strong>LIVE EXECUTION FALSE</strong>
        </div>
      </div>

      <nav className="lfb-viewbar" aria-label="Investment factory browser view">
        <div className="lfb-viewbar-copy">
          <span>IIOS EXPERIENCE</span>
          <strong>{view === "floor" ? "The Living Operations Floor" : "The Living Control Room"}</strong>
        </div>
        <div className="lfb-view-switch">
          <button
            className={`lfb-view-button ${view === "floor" ? "is-active" : ""}`}
            onClick={() => setView("floor")}
            type="button"
          >
            <span>01</span>
            <strong>FACTORY FLOOR</strong>
            <em>living cast · physical rooms · routed cases</em>
          </button>
          <button
            className={`lfb-view-button ${view === "control" ? "is-active" : ""}`}
            onClick={() => setView("control")}
            type="button"
          >
            <span>02</span>
            <strong>CONTROL ROOM</strong>
            <em>every preserved system · same cinematic headquarters</em>
          </button>
        </div>
        <div className="lfb-view-truth">
          <i aria-hidden="true" />
          <span>NARRATIVE ≠ RAW MODEL OUTPUT · CHARACTER MOTION IS PRESENTATION ONLY · PERSISTED STATE REMAINS AUTHORITATIVE</span>
        </div>
      </nav>

      <CinematicFactoryCommandDeck view={view} />
      <CinematicFactorySceneStrip view={view} />
      <LivingCharacterDirectorV7 view={view} />

      {view === "floor" ? (
        <div className="cinematic-floor-stage">
          <LivingFactorySpatialFloor />
        </div>
      ) : (
        <section className="cinematic-control-room" aria-label="Cinematic IIOS Control Room">
          <header className="cinematic-control-room__masthead">
            <div>
              <span>THE BOSS'S COMMAND SUITE · EVERY PRESERVED SYSTEM</span>
              <h2>THE CONTROL ROOM</h2>
            </div>
            <p>
              Same factory. Same truth boundaries. Every diagnostic, paper-capital,
              research, validation, committee, risk, monitoring, and learning surface
              now lives inside one visual world.
            </p>
          </header>

          <nav className="cinematic-control-index" aria-label="Control Room module index">
            {CONTROL_MODULES.map((module) => (
              <a href={`#${module.id}`} key={module.id}>
                <strong>{module.code}</strong>{module.title}
              </a>
            ))}
          </nav>

          <div className="lfb-control-stack">
            {CONTROL_MODULES.map((module) => (
              <section className="cinematic-control-module" id={module.id} key={module.id}>
                <header className="cinematic-control-module__header">
                  <div className="cinematic-control-module__code">{module.code}</div>
                  <div className="cinematic-control-module__title">
                    <strong>{module.title}</strong>
                    <span>{module.subtitle}</span>
                  </div>
                  <div className="cinematic-control-module__truth">{module.truth}</div>
                </header>
                <div className="cinematic-control-module__body">{module.render()}</div>
              </section>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

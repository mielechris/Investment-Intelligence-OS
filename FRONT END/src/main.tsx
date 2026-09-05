import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import PaperFundOperationsShell from "./PaperFundOperationsShell.tsx";
import ExpansionWing from "./ExpansionWing.tsx";
import LiveFactoryBrowser from "./LiveFactoryBrowser.tsx";
import { ExpansionWingSnapshotProvider } from "./ExpansionWingSnapshotProvider.tsx";

const expansionApp = import.meta.env.VITE_EXPANSION_WING_APP === "1";
const unifiedFactory = import.meta.env.VITE_UNIFIED_LIVING_FACTORY === "1";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ExpansionWingSnapshotProvider>
      {unifiedFactory
        ? <LiveFactoryBrowser />
        : expansionApp
          ? <ExpansionWing />
          : <PaperFundOperationsShell />}
    </ExpansionWingSnapshotProvider>
  </StrictMode>,
);

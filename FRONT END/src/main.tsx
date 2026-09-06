import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import SelectedApp from "virtual:iios-selected-app";
import { ExpansionWingSnapshotProvider } from "./ExpansionWingSnapshotProvider.tsx";

// vite.config validates VITE_EXPANSION_WING_APP and selects exactly one build graph.

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ExpansionWingSnapshotProvider>
      <SelectedApp />
    </ExpansionWingSnapshotProvider>
  </StrictMode>,
);

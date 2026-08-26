import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import FactoryIntelligenceExperienceShell from "./FactoryIntelligenceExperienceShell.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <FactoryIntelligenceExperienceShell />
  </StrictMode>,
);

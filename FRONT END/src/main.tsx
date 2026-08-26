import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import FactoryIntelligenceUI from "./FactoryIntelligenceUI.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <FactoryIntelligenceUI />
  </StrictMode>,
);

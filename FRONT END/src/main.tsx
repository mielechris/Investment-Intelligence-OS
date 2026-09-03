import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import PaperFundOperationsShell from "./PaperFundOperationsShell.tsx";
import ExpansionWing from "./ExpansionWing.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {import.meta.env.VITE_EXPANSION_WING_FIXTURE === "1"
      ? <ExpansionWing />
      : <PaperFundOperationsShell />}
  </StrictMode>,
);

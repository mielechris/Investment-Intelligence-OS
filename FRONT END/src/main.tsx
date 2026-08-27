import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import PaperFundOperationsShell from "./PaperFundOperationsShell.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PaperFundOperationsShell />
  </StrictMode>,
);

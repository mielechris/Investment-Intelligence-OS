import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import LivingWallApp from "./LivingWallApp.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LivingWallApp />
  </StrictMode>,
);

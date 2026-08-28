import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import LiveFactoryBrowser from "./LiveFactoryBrowser.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LiveFactoryBrowser />
  </StrictMode>,
);

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import DecisionHistoryPanel from './DecisionHistoryPanel.tsx'
import EvidenceGapHunterPanel from './EvidenceGapHunterPanel.tsx'
import HardDataPanel from './HardDataPanel.tsx'
import InterviewPortalPanel from './InterviewPortalPanel.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <DecisionHistoryPanel />
    <EvidenceGapHunterPanel />
    <HardDataPanel />
    <InterviewPortalPanel />
  </StrictMode>,
)

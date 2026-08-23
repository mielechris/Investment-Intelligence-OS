import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import DecisionHistoryPanel from './DecisionHistoryPanel.tsx'
import EvidenceGapHunterPanel from './EvidenceGapHunterPanel.tsx'
import HardDataPanel from './HardDataPanel.tsx'
import InsiderOwnershipPanel from './InsiderOwnershipPanel.tsx'
import InstitutionalIntelligencePanel from './InstitutionalIntelligencePanel.tsx'
import PrimaryEvidencePanel from './PrimaryEvidencePanel.tsx'
import InterviewPortalPanel from './InterviewPortalPanel.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <DecisionHistoryPanel />
    <EvidenceGapHunterPanel />
    <HardDataPanel />
    <InsiderOwnershipPanel />
    <InstitutionalIntelligencePanel />
    <PrimaryEvidencePanel />
    <InterviewPortalPanel />
  </StrictMode>,
)

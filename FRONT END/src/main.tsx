import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import DecisionHistoryPanel from './DecisionHistoryPanel.tsx'
import EvidenceGapHunterPanel from './EvidenceGapHunterPanel.tsx'
import HardDataPanel from './HardDataPanel.tsx'
import InsiderOwnershipPanel from './InsiderOwnershipPanel.tsx'
import InstitutionalIntelligencePanel from './InstitutionalIntelligencePanel.tsx'
import CaseAwarePrimaryEvidencePanel from './CaseAwarePrimaryEvidencePanel.tsx'
import ConsensusVerificationPanel from './ConsensusVerificationPanel.tsx'
import ShortInterestVerificationPanel from './ShortInterestVerificationPanel.tsx'
import OptionsPositioningVerificationPanel from './OptionsPositioningVerificationPanel.tsx'
import PortfolioContextPanel from './PortfolioContextPanel.tsx'
import InterviewPortalPanel from './InterviewPortalPanel.tsx'
import JesseIntelligencePanel from './JesseIntelligencePanel.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <DecisionHistoryPanel />
    <EvidenceGapHunterPanel />
    <HardDataPanel />
    <InsiderOwnershipPanel />
    <InstitutionalIntelligencePanel />
    <CaseAwarePrimaryEvidencePanel />
    <ConsensusVerificationPanel />
    <ShortInterestVerificationPanel />
    <OptionsPositioningVerificationPanel />
    <PortfolioContextPanel />
    <JesseIntelligencePanel />
    <InterviewPortalPanel />
  </StrictMode>,
)

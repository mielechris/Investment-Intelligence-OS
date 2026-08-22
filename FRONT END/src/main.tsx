import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import CouncilPanel from './CouncilPanel.tsx'
import FactoryPanel from './FactoryPanel.tsx'
import OperationsPanel from './OperationsPanel.tsx'
import PaperExecutionPanel from './PaperExecutionPanel.tsx'
import PaperPortfolioPanel from './PaperPortfolioPanel.tsx'
import PostmortemPanel from './PostmortemPanel.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div
      style={{
        minHeight: '100vh',
        background: '#040506',
      }}
    >
      <div style={{ padding: '32px 32px 0' }}>
        <OperationsPanel />
        <CouncilPanel />
        <PaperExecutionPanel />
        <PaperPortfolioPanel />
        <PostmortemPanel />
        <FactoryPanel />
      </div>
      <App />
    </div>
  </StrictMode>,
)

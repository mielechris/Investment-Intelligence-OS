import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import FactoryPanel from './FactoryPanel.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div
      style={{
        minHeight: '100vh',
        background: '#040506',
      }}
    >
      <div style={{ padding: '32px 32px 0' }}>
        <FactoryPanel />
      </div>
      <App />
    </div>
  </StrictMode>,
)

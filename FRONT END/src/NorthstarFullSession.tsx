import { createRoot } from 'react-dom/client';
import { NorthstarSessionProvider } from './NorthstarSessionContext';
import { NorthstarLivingWall } from './LivingWallApp';
import './NorthstarFullSession.css';

// Dedicated graph: the permanent polling provider is never mounted here.
createRoot(document.getElementById('root')!).render(
  new URLSearchParams(window.location.search).get('fullSession') === '1'
    ? <NorthstarSessionProvider><NorthstarLivingWall /></NorthstarSessionProvider>
    : <main><h1>FULL SESSION CONTEXT REQUIRED</h1><p>No request was made. Use ?fullSession=1.</p></main>,
);

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import 'ag-grid-community/styles/ag-grid.css'
import App from './App.tsx'
import { UITweakProvider } from './contexts/UITweakContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <UITweakProvider>
      <App />
    </UITweakProvider>
  </StrictMode>,
)

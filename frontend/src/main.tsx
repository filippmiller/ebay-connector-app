import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

import App from './App.tsx'
import { UITweakProvider } from './contexts/UITweakContext'

// ============================================
// Load AI Chat Widget
// ============================================
function loadChatWidget() {
  const widgetUrl = import.meta.env.VITE_CHAT_WIDGET_BASE_URL;

  if (!widgetUrl) {
    console.warn('AI Chat Widget: VITE_CHAT_WIDGET_BASE_URL not configured');
    return;
  }

  const script = document.createElement('script');
  script.src = `${widgetUrl}/widget/widget.js`;
  script.setAttribute('data-api', widgetUrl + '/api');
  script.setAttribute('data-title', 'eBay Connector Assistant');
  script.setAttribute('data-greeting', 'Привет! 👋 Я ассистент eBay Connector. Задавай вопросы голосом или текстом.');
  script.setAttribute('data-position', 'bottom-right');
  script.setAttribute('data-theme', 'light');

  script.onerror = () => {
    console.error('AI Chat Widget: Failed to load widget script from', widgetUrl);
  };

  script.onload = () => {
    console.log('AI Chat Widget: Loaded successfully from', widgetUrl);
  };

  document.body.appendChild(script);
}

// Load widget after a short delay to ensure DOM is ready
setTimeout(loadChatWidget, 500);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <UITweakProvider>
      <App />
    </UITweakProvider>
  </StrictMode>,
)

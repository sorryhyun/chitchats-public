import { createRoot } from 'react-dom/client'
import { Suspense } from 'react'
import './styles/index.css'
import './i18n'  // Initialize i18n
import App from './App.tsx'
import { AuthProvider } from './contexts/AuthContext'
import { ToastProvider } from './contexts/ToastContext'

createRoot(document.getElementById('root')!).render(
  <Suspense fallback={<div className="h-screen flex items-center justify-center">Loading...</div>}>
    <AuthProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </AuthProvider>
  </Suspense>
)

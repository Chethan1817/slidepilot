import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from './components/Toasts'
import { HowItWorksPage } from './pages/HowItWorks'
import { LibraryPage } from './pages/Library'
import { NotFoundPage } from './pages/NotFound'
import { SettingsPage } from './pages/Settings'

// The live room pulls in the LiveKit client, so it loads only when a deck is opened.
const PresentPage = lazy(() => import('./pages/Present').then((m) => ({ default: m.PresentPage })))

export function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="flex h-dvh items-center justify-center text-sm text-ink-3">Loading…</div>}>
          <Routes>
            <Route path="/" element={<LibraryPage />} />
            <Route path="/how-it-works" element={<HowItWorksPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/present/:deckId" element={<PresentPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ToastProvider>
  )
}

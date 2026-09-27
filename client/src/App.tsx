import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { AppLayout } from './layout/AppLayout'
import { SetupGate } from './layout/SetupGate'
import CatalogPage from './pages/CatalogPage'
import HomePage from './pages/HomePage'
import JobPage from './pages/JobPage'
import SetupPage from './pages/SetupPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/setup" element={<SetupPage />} />
        <Route
          element={
            <SetupGate>
              <AppLayout />
            </SetupGate>
          }
        >
          <Route path="/" element={<HomePage />} />
          <Route path="/dialogues" element={<Navigate to="/catalog/peers" replace />} />
          <Route path="/jobs/:jobId" element={<JobPage />} />
          <Route path="/jobs" element={<Navigate to="/" replace />} />
          <Route path="/catalog" element={<Navigate to="/catalog/peers" replace />} />
          <Route path="/catalog/:kind" element={<CatalogPage />} />
          <Route path="/graph" element={null} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

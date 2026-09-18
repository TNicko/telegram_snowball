import { useEffect, useState, type ReactNode } from 'react'
import { Navigate } from 'react-router'
import { api, type AppStatus } from '../lib/api'
import { AppStatusContext } from './statusContext'

export function SetupGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .status()
      .then(setStatus)
      .catch((err: Error) => setError(err.message))
  }, [])

  if (error) {
    return (
      <div className="setupWrap">
        <h1 className="pageTitle">Cannot reach the API</h1>
        <p className="lede">
          Run <code>docker compose up</code> from the repo root, then open the
          UI again. {error}
        </p>
      </div>
    )
  }
  if (!status) return <div className="setupWrap muted">Loading…</div>
  if (!status.has_session) return <Navigate to="/setup" replace />
  return <AppStatusContext.Provider value={status}>{children}</AppStatusContext.Provider>
}

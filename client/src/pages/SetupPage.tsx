import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { api, wsUrl } from '../lib/api'

type Step = 'credentials' | 'phone' | 'code' | 'password'

export default function SetupPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('credentials')
  const [ready, setReady] = useState(false)
  const [apiId, setApiId] = useState('')
  const [apiHash, setApiHash] = useState('')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [socket, setSocket] = useState<WebSocket | null>(null)

  useEffect(() => {
    api
      .status()
      .then((status) => {
        if (status.setup_phone) setPhone(status.setup_phone)
        if (status.has_credentials && !status.has_session) setStep('phone')
      })
      .catch(() => undefined)
      .finally(() => setReady(true))
  }, [])

  const saveCredentials = async () => {
    setError(null)
    setBusy(true)
    try {
      await api.saveCredentials(Number(apiId), apiHash.trim())
      setStep('phone')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save credentials')
    } finally {
      setBusy(false)
    }
  }

  const startSession = () => {
    if (busy || !phone.trim()) return
    setError(null)
    setBusy(true)
    socket?.close()
    const ws = new WebSocket(wsUrl('/api/setup/session'))
    setSocket(ws)
    ws.onopen = () => {
      ws.send(JSON.stringify({ phone_number: phone.trim() }))
    }
    ws.onmessage = (event) => {
      const payload = JSON.parse(String(event.data)) as { message?: string; error?: string }
      if (payload.error) {
        setError(payload.error)
        setBusy(false)
        return
      }
      if (payload.message === 'Enter code') {
        setBusy(false)
        setStep('code')
      }
      if (payload.message?.includes('2FA')) {
        setBusy(false)
        setStep('password')
      }
      if (payload.message === 'ok') {
        ws.close()
        navigate('/')
      }
    }
    ws.onerror = () => {
      setError('WebSocket error during Telegram sign-in')
      setBusy(false)
    }
  }

  const sendCode = () => {
    if (busy || !code.trim()) return
    setError(null)
    setBusy(true)
    socket?.send(JSON.stringify({ code: code.trim() }))
  }

  const sendPassword = () => {
    if (busy || !password) return
    setError(null)
    setBusy(true)
    socket?.send(JSON.stringify({ password }))
  }

  if (!ready) return <div className="setupWrap muted">Loading…</div>

  return (
    <div className="setupWrap">
      <p className="steps">First-run setup · one Telegram session</p>
      <h1 className="pageTitle">Connect Telegram</h1>
      {step === 'credentials' && (
        <>
          <p className="lede">
            Telegram requires an API app. Open{' '}
            <a href="https://my.telegram.org" target="_blank" rel="noreferrer">
              my.telegram.org
            </a>
            , sign in, go to API development tools, create an app, then paste the id and hash here.
            Platform: Desktop. URL can be left blank.
          </p>
          <div className="field">
            <label htmlFor="api_id">api_id</label>
            <input id="api_id" value={apiId} onChange={(e) => setApiId(e.target.value)} inputMode="numeric" />
          </div>
          <div className="field">
            <label htmlFor="api_hash">api_hash</label>
            <input id="api_hash" value={apiHash} onChange={(e) => setApiHash(e.target.value)} />
          </div>
          <button className="btn btnPrimary" disabled={busy || !apiId || !apiHash} onClick={() => void saveCredentials()}>
            Continue
          </button>
        </>
      )}
      {step === 'phone' && (
        <>
          <p className="lede">Sign in with the phone number on this Telegram account.</p>
          <div className="field">
            <label htmlFor="phone">Phone</label>
            <input
              id="phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+4477…"
              disabled={busy}
            />
          </div>
          <SubmitButton
            busy={busy}
            disabled={!phone.trim()}
            idleLabel="Send code"
            busyLabel="Sending code"
            onClick={startSession}
          />
        </>
      )}
      {step === 'code' && (
        <>
          <p className="lede">Enter the login code Telegram just sent.</p>
          <div className="field">
            <label htmlFor="code">Code</label>
            <input
              id="code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={busy}
            />
          </div>
          <SubmitButton
            busy={busy}
            disabled={!code.trim()}
            idleLabel="Verify"
            busyLabel="Verifying"
            onClick={sendCode}
          />
        </>
      )}
      {step === 'password' && (
        <>
          <p className="lede">Two-factor authentication is enabled on this account.</p>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
            />
          </div>
          <SubmitButton
            busy={busy}
            disabled={!password}
            idleLabel="Continue"
            busyLabel="Signing in"
            onClick={sendPassword}
          />
        </>
      )}
      {error ? <p className="error">{error}</p> : null}
    </div>
  )
}

function SubmitButton({
  busy,
  disabled,
  idleLabel,
  busyLabel,
  onClick,
}: {
  busy: boolean
  disabled: boolean
  idleLabel: string
  busyLabel: string
  onClick: () => void
}) {
  return (
    <button
      className={`btn btnPrimary${busy ? ' btnLoading' : ''}`}
      onClick={onClick}
      disabled={busy || disabled}
    >
      {busy ? (
        <span className="btnBusy">
          <span className="spinner" aria-hidden />
          {busyLabel}
        </span>
      ) : (
        idleLabel
      )}
    </button>
  )
}

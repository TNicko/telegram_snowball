import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { AccountAvatar } from '../components/AccountAvatar'
import { CatalogSearchBar } from '../components/CatalogSearchBar'
import { LoadingText } from '../components/LoadingText'
import { PeerAvatar } from '../components/PeerAvatar'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { accountDisplayName, formatAccountPhone } from '../lib/account'
import { api, type AppStatus, type Peer } from '../lib/api'
import { peerTypeLabel } from '../lib/peer'
import { useAppStatus } from '../layout/statusContext'
import h from './HomePage.module.css'

export default function HomePage() {
  const navigate = useNavigate()
  const sharedStatus = useAppStatus()
  const [status, setStatus] = useState<AppStatus | null>(sharedStatus)
  const [query, setQuery] = useState('')
  const [hit, setHit] = useState<Peer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [embedImages, setEmbedImages] = useState(true)
  const [embedText, setEmbedText] = useState(true)
  const [images, setImages] = useState(true)
  const [videos, setVideos] = useState(true)
  const [participants, setParticipants] = useState(false)
  const [restrictRange, setRestrictRange] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [maxDepth, setMaxDepth] = useState('')
  const [maxBytes, setMaxBytes] = useState('')
  const [busy, setBusy] = useState(false)
  const [searching, setSearching] = useState(false)

  const { running: dialoguesRunning, loaded: dialoguesLoaded } = useDialogueSync()

  useEffect(() => {
    api.status().then(setStatus).catch((err: Error) => setError(err.message))
  }, [])

  const account = status?.account ?? null
  const accountName = account ? accountDisplayName(account) : null
  const accountPhone = formatAccountPhone(account?.phone)

  const imageReady = status?.models.image.ready ?? false
  const textReady = status?.models.text.ready ?? false
  const gate = useMemo(() => {
    const missing: string[] = []
    if (embedImages && !imageReady) missing.push('image embeddings (SigLIP)')
    if (embedText && !textReady) missing.push('text embeddings (BGE-M3)')
    return missing
  }, [embedImages, embedText, imageReady, textReady])

  const search = async (value = query) => {
    const q = value.trim()
    if (!q || searching) return
    setError(null)
    setHit(null)
    setSearching(true)
    try {
      const result = await api.resolveSeed(q)
      setHit(result.peer)
    } catch (err) {
      setHit(null)
      setError(err instanceof Error ? err.message : 'Resolve failed')
    } finally {
      setSearching(false)
    }
  }

  const startSnowball = async () => {
    if (!hit) return
    setBusy(true)
    setError(null)
    try {
      const job = await api.createJob('forward_snowball', {
        seed_external_id: hit.external_id,
        images,
        videos,
        participants,
        embed_images: embedImages,
        embed_text: embedText,
        restrict_date_range: restrictRange,
        max_depth: maxDepth ? Number(maxDepth) : null,
        max_media_bytes: maxBytes ? Number(maxBytes) : null,
      })
      setModalOpen(false)
      navigate(`/jobs/${job.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start snowball')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="homeOverview">
        <section className="homeCol">
          <h2 className="sectionTitle">Telegram Account</h2>
          {account ? (
            <div className="card accountCard">
              <AccountAvatar
                photoUrl={account.photo_url}
                mediaKind={account.photo_media_kind}
                name={accountName ?? 'Account'}
                size="md"
              />
              <div className="accountMeta">
                <div className="accountName">{accountName}</div>
                {account.username ? <div className="muted">@{account.username}</div> : null}
                {accountPhone ? <div className="muted">{accountPhone}</div> : null}
              </div>
            </div>
          ) : (
            <div className="card accountCard">
              <p className="muted">No account connected.</p>
            </div>
          )}
        </section>
        <section className="homeCol">
          <h2 className="sectionTitle">Models</h2>
          <div className="modelCards">
            <ModelCard title="SigLIP2 images" ready={imageReady} />
            <ModelCard title="BGE-M3 text" ready={textReady} />
            <ModelCard title="BLIP captions" ready={status?.models.caption.ready ?? false} optional />
          </div>
        </section>
      </div>

      <section className={h.crawl}>
        <h1 className={h.crawlTitle}>Begin Telegram Crawling</h1>
        {dialoguesRunning ? (
          <p>
            <LoadingText>
              {dialoguesLoaded > 0
                ? `Loading dialogues · ${dialoguesLoaded} so far`
                : 'Loading dialogues'}
            </LoadingText>
          </p>
        ) : null}
        {status?.active_job ? (
          <p className="muted">
            Active job: {status.active_job.task_type} ({status.active_job.status}){' '}
            <Link to={`/jobs/${status.active_job.id}`}>Open</Link>
          </p>
        ) : null}
        <div className={h.crawlSearch}>
          <CatalogSearchBar
            query={query}
            onQueryChange={(value) => {
              setQuery(value)
              if (hit) setHit(null)
            }}
            onSearch={(value) => void search(value)}
            isLoading={searching}
            placeholder="Search by @username or peer id"
            ariaLabel="Search seed peer"
            flush
            results={
              hit ? (
                <button
                  className={h.hit}
                  type="button"
                  role="option"
                  aria-selected="true"
                  onClick={() => setModalOpen(true)}
                >
                  <PeerAvatar peer={hit} />
                  <span className={h.hitBody}>
                    <span className={h.hitTitle}>
                      {hit.title ?? (hit.username ? `@${hit.username}` : String(hit.external_id))}
                    </span>
                    <span className={h.hitMeta}>
                      {peerTypeLabel(hit.peer_type)}
                      {hit.username ? ` · @${hit.username}` : ''}
                    </span>
                  </span>
                </button>
              ) : null
            }
          />
        </div>
        {error ? <p className="error">{error}</p> : null}
        <aside className={h.note}>
          A forward snowball starts at one <strong>source peer</strong> — a channel, group, or user
          this account can already see. It scrapes that peer’s messages, then follows native Telegram
          forward metadata into the communities those posts came from, and keeps expanding from
          there. Image and text embedding stay on unless you turn them off; those models must be
          ready to start.
        </aside>
      </section>

      {modalOpen && hit ? (
        <div className="modalScrim" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 className={h.modalTitle}>Begin snowballing</h3>
            <div className={h.seed}>
              <PeerAvatar peer={hit} />
              <span className={h.hitBody}>
                <span className={h.hitTitle}>
                  {(hit.title ?? '').trim() ||
                    (hit.username ? `@${hit.username}` : String(hit.external_id))}
                </span>
                <span className={h.hitMeta}>
                  {peerTypeLabel(hit.peer_type)}
                  {hit.username ? ` · @${hit.username}` : ''}
                </span>
              </span>
            </div>
            <p className="muted">
              First/last message probe (created date, latest message id) will land in the next pass.
              Messages are always scraped.
            </p>
            <label className="toggle">
              <input type="checkbox" checked={restrictRange} onChange={(e) => setRestrictRange(e.target.checked)} />
              Restrict scrape to a date window (also skips forward sources only seen outside it)
            </label>
            <label className="toggle">
              <input type="checkbox" checked={images} onChange={(e) => setImages(e.target.checked)} />
              Scrape images
            </label>
            <label className="toggle">
              <input type="checkbox" checked={videos} onChange={(e) => setVideos(e.target.checked)} />
              Scrape videos
            </label>
            <label className="toggle">
              <input type="checkbox" checked={participants} onChange={(e) => setParticipants(e.target.checked)} />
              Scrape participants
            </label>
            <hr style={{ border: 0, borderTop: '1px solid var(--border)' }} />
            <label className="toggle">
              <input type="checkbox" checked={embedImages} onChange={(e) => setEmbedImages(e.target.checked)} />
              Embed images (default on)
            </label>
            <label className="toggle">
              <input type="checkbox" checked={embedText} onChange={(e) => setEmbedText(e.target.checked)} />
              Embed message text (default on)
            </label>
            {gate.length > 0 ? (
              <p className="error">
                Cannot start: {gate.join(' and ')} not ready. Finish model setup or turn the toggle
                off.
              </p>
            ) : (
              <p className="ok">Embedding gate clear.</p>
            )}
            <button className="btn" onClick={() => setAdvanced((v) => !v)}>
              {advanced ? 'Hide advanced' : 'Advanced'}
            </button>
            {advanced ? (
              <>
                <div className="field">
                  <label htmlFor="depth">Max depth (empty = unlimited)</label>
                  <input id="depth" value={maxDepth} onChange={(e) => setMaxDepth(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="bytes">Max media bytes</label>
                  <input id="bytes" value={maxBytes} onChange={(e) => setMaxBytes(e.target.value)} />
                </div>
              </>
            ) : null}
            <div className="row" style={{ marginTop: '1rem' }}>
              <button
                className="btn btnPrimary"
                disabled={busy || gate.length > 0}
                onClick={() => void startSnowball()}
              >
                Start snowball
              </button>
              <button className="btn" onClick={() => setModalOpen(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function ModelCard({ title, ready, optional }: { title: string; ready: boolean; optional?: boolean }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <span className={`pill ${ready ? 'ok' : 'warn'}`}>{ready ? 'Ready' : 'Not ready'}</span>
      {optional && !ready ? <p className="muted">Optional for v1 snowball gate.</p> : null}
    </div>
  )
}

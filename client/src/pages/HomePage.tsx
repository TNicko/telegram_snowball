import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { AccountAvatar } from '../components/AccountAvatar'
import { AccountCardMenu } from '../components/AccountCardMenu'
import { CatalogSearchBar } from '../components/CatalogSearchBar'
import { isLiveJob, JobCard, JobList } from '../components/HomeJobs'
import { LoadingText } from '../components/LoadingText'
import { PeerAvatar } from '../components/PeerAvatar'
import { ModelSetupModal } from '../components/ModelSetupModal'
import { SnowballConfigModal } from '../components/SnowballConfigModal'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { useSnowballJobs } from '../hooks/useSnowballJobs'
import { accountDisplayName, formatAccountPhone, syncingChatsLabel } from '../lib/account'
import { api, type AppStatus, type Job, type ModelCatalog, type ModelSlot, type Peer } from '../lib/api'
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
  const { jobs, setJobs } = useSnowballJobs()
  const [modalOpen, setModalOpen] = useState(false)
  const [modelSlot, setModelSlot] = useState<ModelSlot | null>(null)
  const [models, setModels] = useState<ModelCatalog | null>(null)
  const [modelError, setModelError] = useState<string | null>(null)
  const [modelBusy, setModelBusy] = useState(false)
  const [busy, setBusy] = useState(false)
  const [searching, setSearching] = useState(false)

  const { running: dialoguesRunning, loaded: dialoguesLoaded } = useDialogueSync()

  useEffect(() => {
    api.status().then(setStatus).catch((err: Error) => setError(err.message))
    api.models().then(setModels).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!models?.download) return
    const timer = window.setInterval(() => {
      void api.models().then(setModels).catch(() => undefined)
      void api.status().then(setStatus).catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [models?.download])

  const account = status?.account ?? null
  const accountName = account ? accountDisplayName(account) : null
  const accountPhone = formatAccountPhone(account?.phone)

  const imageReady = models?.slots.image.ready ?? status?.models.image.ready ?? false
  const textReady = models?.slots.text.ready ?? status?.models.text.ready ?? false
  const captionReady = models?.slots.caption.ready ?? status?.models.caption.ready ?? false

  const applyModels = (next: ModelCatalog) => {
    setModels(next)
    setStatus((current) =>
      current
        ? {
            ...current,
            models: {
              image: next.slots.image,
              text: next.slots.text,
              caption: next.slots.caption,
            },
          }
        : current,
    )
  }

  const selectModel = async (modelId: string) => {
    if (!modelSlot || modelBusy) return
    setModelBusy(true)
    setModelError(null)
    try {
      applyModels(await api.selectModels({ [modelSlot]: modelId }))
    } catch (err) {
      setModelError(err instanceof Error ? err.message : 'Could not select that model')
    } finally {
      setModelBusy(false)
    }
  }

  const downloadModel = async (modelId: string) => {
    if (modelBusy) return
    setModelBusy(true)
    setModelError(null)
    try {
      applyModels(await api.downloadModel(modelId))
    } catch (err) {
      setModelError(err instanceof Error ? err.message : 'Could not start the download')
    } finally {
      setModelBusy(false)
    }
  }

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

  const startSnowball = async (params: Record<string, unknown>) => {
    setBusy(true)
    setError(null)
    try {
      const job = await api.createJob('forward_snowball', params)
      setModalOpen(false)
      setHit(null)
      setQuery('')
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start snowball')
    } finally {
      setBusy(false)
    }
  }

  const startFromHit = async (params: Record<string, unknown>) => {
    await startSnowball(params)
  }

  const stopJob = async (job: Job) => {
    setBusy(true)
    setError(null)
    try {
      const stopped = await api.cancelJob(job.id)
      setJobs((current) => current.map((item) => (item.id === stopped.id ? stopped : item)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not stop job')
    } finally {
      setBusy(false)
    }
  }

  const dropAccount = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await api.removeSession()
      navigate('/setup', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the Telegram account')
      setBusy(false)
    }
  }

  const liveJob = jobs.find((job) => isLiveJob(job.status)) ?? null

  return (
    <div className={h.page}>
      <div className="homeOverview">
        <section className="homeCol">
          <h2 className="sectionTitle">Telegram Account</h2>
          {account ? (
            <div className={`card accountCard ${h.accountCard}`}>
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
              <AccountCardMenu
                busy={busy}
                onChangeAccount={() => void dropAccount()}
                onRemoveAccount={() => void dropAccount()}
              />
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
            <ModelCard
              title={models?.slots.image.label ?? 'Vision'}
              ready={imageReady}
              hint={models?.copy.image.blurb}
              downloading={models?.download?.params?.slot === 'image'}
              onClick={() => setModelSlot('image')}
            />
            <ModelCard
              title={models?.slots.text.label ?? 'Message text'}
              ready={textReady}
              hint={models?.copy.text.blurb}
              downloading={models?.download?.params?.slot === 'text'}
              onClick={() => setModelSlot('text')}
            />
            <ModelCard
              title={models?.slots.caption.label ?? 'Captions'}
              ready={captionReady}
              hint={models?.copy.caption.blurb}
              downloading={models?.download?.params?.slot === 'caption'}
              onClick={() => setModelSlot('caption')}
            />
          </div>
        </section>
      </div>

      <section className={`${h.crawl}${jobs.length > 0 ? ` ${h.crawlFilled}` : ''}`}>
        <h1 className={h.crawlTitle}>Begin Crawling Telegram</h1>
        {dialoguesRunning && !liveJob ? (
          <p>
            <LoadingText>{syncingChatsLabel(account, dialoguesLoaded)}</LoadingText>
          </p>
        ) : null}
        <div className={h.crawlSearch}>
          {liveJob ? (
            <JobCard
              job={liveJob}
              featured
              busy={busy}
              onStop={(job) => void stopJob(job)}
              onStart={(job) => void startSnowball(job.params)}
            />
          ) : (
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
          )}
        </div>
        {error ? <p className="error">{error}</p> : null}
        {liveJob ? null : (
          <aside className={h.note}>
            Enter the peer you would like to start scraping from (must be a public community with a
            username, or one that already exists on your account). Snowball scrapes its messages, then
            expands through Telegram forwards.
          </aside>
        )}
        <JobList
          jobs={liveJob ? jobs.filter((job) => job.id !== liveJob.id) : jobs}
          busy={busy}
          startBlocked={liveJob != null}
          onStop={(job) => void stopJob(job)}
          onStart={(job) => void startSnowball(job.params)}
        />
      </section>

      {modelSlot && models ? (
        <ModelSetupModal
          slot={modelSlot}
          catalog={models}
          busy={modelBusy}
          error={modelError}
          onClose={() => {
            setModelSlot(null)
            setModelError(null)
          }}
          onSelect={(id) => void selectModel(id)}
          onDownload={(id) => void downloadModel(id)}
        />
      ) : null}

      {modalOpen && hit ? (
        <SnowballConfigModal
          peer={hit}
          busy={busy}
          imageReady={imageReady}
          textReady={textReady}
          title="Begin snowballing"
          startLabel="Start snowball"
          onClose={() => setModalOpen(false)}
          onStart={(params) => void startFromHit(params)}
        />
      ) : null}
    </div>
  )
}

function ModelCard({
  title,
  ready,
  hint,
  downloading,
  onClick,
}: {
  title: string
  ready: boolean
  hint?: string
  downloading?: boolean
  onClick: () => void
}) {
  const statusClass = ready
    ? h.modelStatusReady
    : downloading
      ? h.modelStatusBusy
      : h.modelStatusWarn
  const status = ready ? 'Ready' : downloading ? 'Downloading' : 'Not ready'
  return (
    <button
      type="button"
      className={`card modelCardBtn ${h.modelCard}`}
      onClick={onClick}
      aria-label={`${title}. ${status}`}
    >
      <span className={`${h.modelStatus} ${statusClass}`} aria-hidden />
      <h3>{title}</h3>
      {downloading ? <p className="muted">Downloading weights…</p> : null}
      {!ready && !downloading ? <p className="muted">Click to set up.</p> : null}
      {ready && hint ? <p className="muted">{hint}</p> : null}
    </button>
  )
}

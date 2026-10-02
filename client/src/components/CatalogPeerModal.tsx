import { useEffect, useState } from 'react'
import { Download, Pickaxe, X } from 'lucide-react'
import { LoadingText } from './LoadingText'
import { PeerAvatar } from './PeerAvatar'
import { StopSyncConfirm } from './StopSyncConfirm'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { useSnowballJobs } from '../hooks/useSnowballJobs'
import {
  api,
  type CoverageLayer,
  type CoverageWindow,
  type EmbedBucket,
  type MediaBucket,
  type Job,
  type Peer,
  type PeerCoverage,
  type RemainderLayer,
} from '../lib/api'
import { useAppStatus } from '../layout/statusContext'
import {
  coverageTimelineSegment,
  formatCoverageDate,
  formatCoverageWindow,
  formatMaxMediaBytes,
  peerTypeLabel,
} from '../lib/peer'
import s from './CatalogPeerModal.module.css'

function peerLabel(peer: Peer): string {
  return (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id))
}

function remainderParams(peerId: number, layer: RemainderLayer): Record<string, unknown> {
  if (layer === 'embed_text' || layer === 'embed_images') {
    return {
      peer_external_id: peerId,
      targets: layer === 'embed_text' ? ['text'] : ['images'],
    }
  }
  const all = layer === 'all'
  return {
    seed_external_id: peerId,
    max_depth: 0,
    fill_remaining: true,
    remainder: layer,
    images: layer === 'image_download' || layer === 'image',
    videos: all || layer === 'video',
    messages: true,
    participants: false,
    embed_images: false,
    embed_text: false,
  }
}

function formatCount(value: number): string {
  return value.toLocaleString()
}

const DASH = '—'

function isDash(value: string): boolean {
  return value === DASH
}

function bucketText(bucket: MediaBucket | null | undefined): string {
  if (!bucket) return DASH
  return `${formatCount(bucket.downloaded)} / ${formatCount(bucket.total)}`
}

function embedText(bucket: EmbedBucket | null | undefined): string {
  if (!bucket || typeof bucket.done !== 'number' || typeof bucket.total !== 'number' || bucket.total <= 0) {
    return DASH
  }
  return `${formatCount(bucket.done)} / ${formatCount(bucket.total)}`
}

function embedRemaining(bucket: EmbedBucket | null | undefined): number {
  if (!bucket || typeof bucket.done !== 'number' || typeof bucket.total !== 'number') return 0
  return Math.max(0, bucket.total - bucket.done)
}

function postsValue(posts: (CoverageWindow & { count: number | null }) | null | undefined): string {
  if (posts?.count == null) return DASH
  if (posts.count === 0 && !posts.covered_after && !posts.covered_before) return DASH
  return formatCount(posts.count)
}

function forwardsDetail(peer: Peer): string | null {
  const unique = peer.forwards_unique
  const total = peer.forwards_total
  if (unique == null && total == null) return null
  const parts: string[] = []
  if (unique != null) parts.push(`${formatCount(unique)} unique fwd`)
  if (total != null) parts.push(`${formatCount(total)} total fwd`)
  return parts.join(' · ')
}

function remainingOf(bucket: MediaBucket | null | undefined): number {
  if (!bucket) return 0
  return Math.max(0, bucket.total - bucket.downloaded)
}

function hashedOf(bucket: MediaBucket | null | undefined): number {
  if (!bucket) return 0
  return bucket.hashed ?? 0
}

function remainingHashed(bucket: MediaBucket | null | undefined): number {
  if (!bucket) return 0
  return Math.max(0, bucket.total - hashedOf(bucket))
}

function imageBucketText(bucket: MediaBucket | null | undefined): string {
  if (!bucket) return DASH
  return `${formatCount(hashedOf(bucket))} / ${formatCount(bucket.total)}`
}

function downloadedText(bucket: MediaBucket | null | undefined): string | null {
  if (!bucket) return null
  return `${formatCount(bucket.downloaded)} downloaded`
}

export function CatalogPeerModal({ peer, onClose }: { peer: Peer; onClose: () => void }) {
  const { setJobs, jobs } = useSnowballJobs()
  const { running: dialoguesRunning, stop: stopChatSync } = useDialogueSync()
  const models = useAppStatus()?.models
  const [coverage, setCoverage] = useState<PeerCoverage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyLayer, setBusyLayer] = useState<RemainderLayer | null>(null)
  const [pendingLayer, setPendingLayer] = useState<RemainderLayer | null>(null)
  const [embedJob, setEmbedJob] = useState<Job | null>(null)

  const scrapeLaneBusy = jobs.some((job) => job.status === 'queued' || job.status === 'running')
  const embedLive = embedJob?.status === 'queued' || embedJob?.status === 'running'
  const shown = coverage?.peer ?? peer
  const handle = shown.username ? `@${shown.username}` : null

  useEffect(() => {
    let cancelled = false
    const load = () => {
      void api
        .peerCoverage(peer.external_id)
        .then((next) => {
          if (cancelled) return
          setCoverage(next)
          setError(null)
        })
        .catch((err: Error) => {
          if (cancelled) return
          setError(err.message)
        })
    }
    load()
    const track = dialoguesRunning || scrapeLaneBusy || embedLive
    if (!track) {
      return () => {
        cancelled = true
      }
    }
    const timer = window.setInterval(load, 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [peer.external_id, dialoguesRunning, scrapeLaneBusy, embedLive])

  useEffect(() => {
    if (!embedJob || (embedJob.status !== 'queued' && embedJob.status !== 'running')) return
    const id = embedJob.id
    const timer = window.setInterval(() => {
      void api.job(id).then(setEmbedJob).catch(() => undefined)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [embedJob?.id, embedJob?.status])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      if (pendingLayer) {
        setPendingLayer(null)
        return
      }
      onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, pendingLayer])

  const scrape = async (layer: RemainderLayer) => {
    const embedding = layer === 'embed_text' || layer === 'embed_images'
    if (busyLayer || (!embedding && scrapeLaneBusy)) return
    setBusyLayer(layer)
    setError(null)
    try {
      if (!embedding && dialoguesRunning) {
        await stopChatSync()
      }
      const job = embedding
        ? await api.createJob('embed', remainderParams(peer.external_id, layer))
        : await api.createJob('forward_snowball', remainderParams(peer.external_id, layer))
      if (embedding) setEmbedJob(job)
      else setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start scrape')
    } finally {
      setBusyLayer(null)
    }
  }

  const requestScrape = (layer: RemainderLayer) => {
    const embedding = layer === 'embed_text' || layer === 'embed_images'
    if (busyLayer || (!embedding && scrapeLaneBusy)) return
    if (!embedding && dialoguesRunning) {
      setPendingLayer(layer)
      return
    }
    void scrape(layer)
  }

  const posts = coverage?.posts
  const timelineStart = coverage?.timeline.start
  const timelineEnd = coverage?.timeline.end
  const timelineWindow = formatCoverageWindow(timelineStart, timelineEnd)
  const media = shown.media
  const scrapeDisabled = scrapeLaneBusy || busyLayer != null
  const embedDisabled = busyLayer != null
  const imageBucket = media?.image
  const imageHashRemaining = remainingHashed(imageBucket)
  const videoRemaining = remainingOf(media?.video)
  const audioRemaining = remainingOf(media?.audio)
  const gifRemaining = remainingOf(media?.gif)
  const documentRemaining = remainingOf(media?.document)
  const exclusions: string[] = []
  if (shown.videos_excluded) exclusions.push('Videos excluded')
  const maxLabel = formatMaxMediaBytes(shown.max_media_bytes)
  if (shown.large_excluded) {
    exclusions.push(maxLabel ? `Files over ${maxLabel} excluded` : 'Large files excluded')
  }

  return (
    <>
    <div className={`modalScrim ${s.scrim}`} onClick={onClose}>
      <div
        className={`modal ${s.modal}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="peer-coverage-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" className={s.close} aria-label="Close" onClick={onClose}>
          <X size={16} strokeWidth={2} aria-hidden />
        </button>
        <div className={s.head}>
          <PeerAvatar peer={shown} />
          <div className={s.headBody}>
            <h3 id="peer-coverage-title" className={s.title}>
              {peerLabel(shown)}
              {shown.is_scraping ? (
                <span className={`spinner ${s.spinner}`} aria-label="Scraping" />
              ) : null}
            </h3>
            <p className={s.meta}>
              {peerTypeLabel(shown.peer_type)}
              {handle ? ` · ${handle}` : ''}
              {shown.participants_count != null
                ? ` · ${formatCount(shown.participants_count)} subscribers`
                : ''}
            </p>
            {shown.is_scraping && shown.scrape_detail ? (
              <p className={s.live}>
                <LoadingText>{shown.scrape_detail}</LoadingText>
              </p>
            ) : null}
          </div>
        </div>

        {!coverage && !error ? (
          <p className={s.loading}>
            <LoadingText>Loading coverage</LoadingText>
          </p>
        ) : (
          <div className={s.layers}>
            <div className={s.axis} aria-hidden>
              <span />
              <span className={s.axisRange}>
                <span>{formatCoverageDate(coverage?.timeline.start) ?? '—'}</span>
                <span>{formatCoverageDate(coverage?.timeline.end) ?? timelineWindow}</span>
              </span>
              <span />
              <span />
            </div>
            <CoverageRow
              label="Posts"
              value={postsValue(posts)}
              origin={timelineStart}
              until={timelineEnd}
              layer={posts}
              detail={forwardsDetail(shown)}
              disabled={scrapeDisabled}
              busy={busyLayer === 'posts'}
              actionLabel="Scrape remainder"
              onScrape={() => void requestScrape('posts')}
            />
            <CoverageRow
              label="Images"
              value={imageBucketText(imageBucket)}
              valueDetail={downloadedText(imageBucket)}
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.media_layers?.image}
              remaining={imageHashRemaining}
              disabled={scrapeDisabled}
              actions={[
                {
                  key: 'image_download',
                  label: 'Download',
                  icon: 'download',
                  busy: busyLayer === 'image_download',
                  onClick: () => void requestScrape('image_download'),
                },
                {
                  key: 'image_phash',
                  label: 'Hash remainder',
                  icon: 'scrape',
                  busy: busyLayer === 'image_phash',
                  onClick: () => void requestScrape('image_phash'),
                },
              ]}
            />
            <CoverageRow
              label="Videos"
              value={bucketText(media?.video)}
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.media_layers?.video}
              remaining={videoRemaining}
              note={shown.videos_excluded ? 'Excluded on last pass' : null}
              disabled={scrapeDisabled}
              busy={busyLayer === 'video'}
              onScrape={() => void requestScrape('video')}
            />
            <CoverageRow
              label="Audio"
              value={bucketText(media?.audio)}
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.media_layers?.audio}
              remaining={audioRemaining}
              disabled={scrapeDisabled}
              busy={busyLayer === 'audio'}
              onScrape={() => void requestScrape('audio')}
            />
            <CoverageRow
              label="Gif"
              value={bucketText(media?.gif)}
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.media_layers?.gif}
              remaining={gifRemaining}
              disabled={scrapeDisabled}
              busy={busyLayer === 'gif'}
              onScrape={() => void requestScrape('gif')}
            />
            <CoverageRow
              label="Files"
              value={bucketText(media?.document)}
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.media_layers?.document}
              remaining={documentRemaining}
              disabled={scrapeDisabled}
              busy={busyLayer === 'document'}
              onScrape={() => void requestScrape('document')}
            />
            <CoverageRow
              label="Text embeddings"
              value={embedText(shown.embed_text)}
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.embeds.text}
              remaining={embedRemaining(shown.embed_text)}
              disabled={embedDisabled || !models?.text.ready}
              busy={busyLayer === 'embed_text'}
              actionLabel="Embed remainder"
              onScrape={() => void requestScrape('embed_text')}
            />
            <CoverageRow
              label="Image embeddings"
              value={embedText(shown.embed_images)}
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.embeds.images}
              remaining={embedRemaining(shown.embed_images)}
              disabled={embedDisabled || !models?.image.ready}
              busy={busyLayer === 'embed_images'}
              actionLabel="Embed remainder"
              onScrape={() => void requestScrape('embed_images')}
            />
          </div>
        )}

        {exclusions.length > 0 ? (
          <p className={s.notes}>{exclusions.join(' · ')}</p>
        ) : null}
        {error ? <p className="error">{error}</p> : null}

        <div className={s.actions}>
          <button
            type="button"
            className="btn btnPrimary"
            disabled={scrapeDisabled}
            onClick={() => void requestScrape('all')}
          >
            {busyLayer === 'all' ? (
              <span className="btnBusy">
                <span className="spinner" aria-hidden />
                Starting
              </span>
            ) : (
              'Scrape all remaining'
            )}
          </button>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
    {pendingLayer ? (
      <StopSyncConfirm
        busy={busyLayer != null}
        onClose={() => setPendingLayer(null)}
        onConfirm={() => {
          const layer = pendingLayer
          setPendingLayer(null)
          if (layer) void scrape(layer)
        }}
      />
    ) : null}
    </>
  )
}

function CoverageRow({
  label,
  value,
  valueDetail,
  origin,
  until,
  layer,
  detail,
  remaining,
  note,
  disabled,
  busy,
  actionLabel = 'Scrape remainder',
  onScrape,
  actions,
}: {
  label: string
  value: string
  valueDetail?: string | null
  origin?: string | null
  until?: string | null
  layer?: (CoverageLayer | CoverageWindow) | null
  detail?: string | null
  remaining?: number
  note?: string | null
  disabled?: boolean
  busy?: boolean
  actionLabel?: string
  onScrape?: () => void
  actions?: { key: string; label: string; icon?: 'scrape' | 'download'; busy?: boolean; onClick: () => void }[]
}) {
  const segment = coverageTimelineSegment(
    origin,
    until,
    layer?.covered_after,
    layer?.covered_before,
    layer?.fill,
  )
  const pct = Math.round(segment.width)
  const windowLabel = formatCoverageWindow(layer?.covered_after, layer?.covered_before)
  const muted = isDash(value)
  const incomplete = !muted && Boolean(remaining && remaining > 0)
  return (
    <div className={s.row}>
      <div className={s.rowMain}>
        <span className={s.label}>{label}</span>
        {detail ? <span className={s.detail}>{detail}</span> : null}
        {note ? <span className={s.note}>{note}</span> : null}
      </div>
      <span
        className={s.meter}
        role="progressbar"
        aria-label={`${label} coverage`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={windowLabel}
        title={windowLabel}
      >
        {segment.width > 0 ? (
          <span
            className={s.meterFill}
            style={{
              left: `${segment.left}%`,
              width: `max(${segment.width}%, 3px)`,
            }}
          />
        ) : null}
      </span>
      <span className={`${s.valueStack}${incomplete ? ` ${s.partial}` : ''}${muted ? ` ${s.valueMuted}` : ''}`}>
        <span className={s.value}>{value}</span>
        {valueDetail ? <span className={s.valueDetail}>{valueDetail}</span> : null}
      </span>
      {actions && actions.length > 0 ? (
        <span className={s.scrapeBtns}>
          {actions.map((action) => (
            <IconAction
              key={action.key}
              label={`${action.label} ${label.toLowerCase()}`}
              icon={action.icon ?? 'scrape'}
              busy={action.busy}
              disabled={disabled}
              onClick={action.onClick}
            />
          ))}
        </span>
      ) : onScrape ? (
        <span className={s.scrapeBtns}>
          <IconAction
            label={`${actionLabel} ${label.toLowerCase()}`}
            icon="scrape"
            busy={busy}
            disabled={disabled}
            onClick={onScrape}
          />
        </span>
      ) : (
        <span className={s.scrapeSlot} />
      )}
    </div>
  )
}

function IconAction({
  label,
  icon,
  busy,
  disabled,
  onClick,
}: {
  label: string
  icon: 'scrape' | 'download'
  busy?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={s.scrapeBtn}
      disabled={disabled}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {busy ? (
        <span className={`spinner ${s.btnSpinner}`} aria-hidden />
      ) : icon === 'download' ? (
        <Download size={15} strokeWidth={2} aria-hidden />
      ) : (
        <Pickaxe size={15} strokeWidth={2} aria-hidden />
      )}
    </button>
  )
}

import { useEffect, useState } from 'react'
import { Download, Pickaxe, X } from 'lucide-react'
import { LoadingText } from './LoadingText'
import { PeerAvatar } from './PeerAvatar'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { useSnowballJobs } from '../hooks/useSnowballJobs'
import {
  api,
  type CoverageLayer,
  type CoverageWindow,
  type MediaBucket,
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

function bucketText(bucket: MediaBucket | null | undefined): string {
  if (!bucket) return '—'
  return `${formatCount(bucket.downloaded)} / ${formatCount(bucket.total)}`
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
  if (!bucket) return '—'
  return `${formatCount(hashedOf(bucket))} / ${formatCount(bucket.total)}`
}

function downloadedText(bucket: MediaBucket | null | undefined): string | null {
  if (!bucket) return null
  return `${formatCount(bucket.downloaded)} downloaded`
}

export function CatalogPeerModal({ peer, onClose }: { peer: Peer; onClose: () => void }) {
  const { setJobs, jobs } = useSnowballJobs()
  const { running: dialoguesRunning } = useDialogueSync()
  const models = useAppStatus()?.models
  const [coverage, setCoverage] = useState<PeerCoverage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyLayer, setBusyLayer] = useState<RemainderLayer | null>(null)

  const jobBusy =
    dialoguesRunning || jobs.some((job) => job.status === 'queued' || job.status === 'running')
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
    const timer = window.setInterval(load, 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [peer.external_id])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const scrape = async (layer: RemainderLayer) => {
    if (jobBusy || busyLayer) return
    setBusyLayer(layer)
    setError(null)
    try {
      const job =
        layer === 'embed_text' || layer === 'embed_images'
          ? await api.createJob('embed', remainderParams(peer.external_id, layer))
          : await api.createJob('forward_snowball', remainderParams(peer.external_id, layer))
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start scrape')
    } finally {
      setBusyLayer(null)
    }
  }

  const posts = coverage?.posts
  const timelineStart = coverage?.timeline.start
  const timelineEnd = coverage?.timeline.end
  const timelineWindow = formatCoverageWindow(timelineStart, timelineEnd)
  const media = shown.media
  const scrapeDisabled = jobBusy || busyLayer != null
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
    <div className="modalScrim" onClick={onClose}>
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
              value={posts ? formatCount(posts.count) : '—'}
              origin={timelineStart}
              until={timelineEnd}
              layer={posts}
              detail={forwardsDetail(shown)}
              remaining={posts && posts.count === 0 ? 1 : 0}
              disabled={scrapeDisabled}
              busy={busyLayer === 'posts'}
              actionLabel="Scrape remainder"
              onScrape={() => void scrape('posts')}
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
                  key: 'image_phash',
                  label: 'Hash remainder',
                  icon: 'scrape',
                  busy: busyLayer === 'image_phash',
                  onClick: () => void scrape('image_phash'),
                },
                {
                  key: 'image_download',
                  label: 'Download',
                  icon: 'download',
                  busy: busyLayer === 'image_download',
                  onClick: () => void scrape('image_download'),
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
              onScrape={() => void scrape('video')}
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
              onScrape={() => void scrape('audio')}
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
              onScrape={() => void scrape('gif')}
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
              onScrape={() => void scrape('document')}
            />
            <CoverageRow
              label="Text embeddings"
              value={
                coverage
                  ? `${formatCount(coverage.embeds.text.done)} / ${formatCount(coverage.embeds.text.total)}`
                  : '—'
              }
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.embeds.text}
              remaining={
                coverage
                  ? Math.max(0, coverage.embeds.text.total - coverage.embeds.text.done)
                  : 0
              }
              disabled={scrapeDisabled || !models?.text.ready}
              busy={busyLayer === 'embed_text'}
              actionLabel="Embed remainder"
              onScrape={() => void scrape('embed_text')}
            />
            <CoverageRow
              label="Image embeddings"
              value={
                coverage
                  ? `${formatCount(coverage.embeds.images.done)} / ${formatCount(coverage.embeds.images.total)}`
                  : '—'
              }
              origin={timelineStart}
              until={timelineEnd}
              layer={coverage?.embeds.images}
              remaining={
                coverage
                  ? Math.max(0, coverage.embeds.images.total - coverage.embeds.images.done)
                  : 0
              }
              disabled={scrapeDisabled || !models?.image.ready}
              busy={busyLayer === 'embed_images'}
              actionLabel="Embed remainder"
              onScrape={() => void scrape('embed_images')}
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
            onClick={() => void scrape('all')}
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
      <span className={`${s.valueStack}${remaining && remaining > 0 ? ` ${s.partial}` : ''}`}>
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

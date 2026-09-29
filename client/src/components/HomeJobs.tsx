import { Pause, Play } from 'lucide-react'
import { LoadingText } from './LoadingText'
import { PeerAvatar } from './PeerAvatar'
import type { Job, Peer } from '../lib/api'
import { formatAddedAt } from '../lib/peer'
import h from '../pages/HomePage.module.css'

export function isLiveJob(status: string): boolean {
  return status === 'queued' || status === 'running'
}

export function isStoppedJob(status: string): boolean {
  return status === 'cancelled'
}

export function jobCurrentPeerId(job: Job): number | null {
  const raw = job.progress?.current_peer
  const id = Number(raw)
  return Number.isFinite(id) && id !== 0 ? id : null
}

export function jobSeedPeer(job: Job): Peer {
  if (job.seed_peer) return job.seed_peer
  const id = Number(job.params.seed_external_id ?? 0)
  return {
    external_id: Number.isFinite(id) ? id : 0,
    peer_type: 'channel',
    title: Number.isFinite(id) && id ? String(id) : 'Snowball',
    username: null,
    photo_path: null,
    is_scraping: false,
    scrape_detail: null,
    messages_scraped: 0,
    created_at: job.created_at,
    updated_at: job.created_at,
  }
}

export function jobTitle(job: Job): string {
  if (job.task_type === 'embed') return 'Embeddings'
  if (job.task_type === 'scope_rerank') return 'Scope rescore'
  if (job.task_type === 'download_model') {
    return String(job.progress?.model_label || job.params.model_id || 'Model download')
  }
  const peer = jobSeedPeer(job)
  return (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id || 'Snowball'))
}

function statusLabel(status: string): string {
  switch (status) {
    case 'queued':
      return 'Queued'
    case 'running':
      return 'Running'
    case 'succeeded':
      return 'Done'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Stopped'
    default:
      return status
  }
}

function statusClass(status: string): string {
  if (status === 'succeeded') return h.jobOk
  if (status === 'failed') return h.jobFail
  if (status === 'cancelled') return h.jobStopped
  return h.jobLive
}

function jobDetail(job: Job): string {
  if (job.status === 'failed' && job.error) return job.error
  if (job.status === 'succeeded') {
    if (job.task_type === 'download_model') {
      const label = job.progress?.model_label
      return typeof label === 'string' && label.trim() ? `${label} is ready` : 'Finished'
    }
    const raw =
      job.progress?.peers_done ??
      (job.progress?.stats as { peers?: number } | undefined)?.peers
    const peers = Number(raw)
    if (Number.isFinite(peers)) return `Finished (${peers} peer${peers === 1 ? '' : 's'})`
    return 'Finished'
  }
  const detail = job.progress?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail.replace(/^Snowball finished/i, 'Finished')
  }
  const peers = job.progress?.peers_done
  if (typeof peers === 'number') return `${peers} peers`
  return statusLabel(job.status)
}

function formatCount(count: number, singular: string, plural: string): string {
  return `${count.toLocaleString()} ${count === 1 ? singular : plural}`
}

function jobStatsLine(job: Job): string | null {
  const stats = job.progress?.stats
  const counts = stats && typeof stats === 'object' ? (stats as Record<string, unknown>) : {}
  const params = job.params ?? {}
  const parts: string[] = []
  const messages = Number(counts.messages ?? job.progress?.messages_scraped)
  if (Number.isFinite(messages) && messages > 0) {
    parts.push(formatCount(messages, 'message', 'messages'))
  }
  const images = Number(counts.image ?? 0)
  if (params.images || (Number.isFinite(images) && images > 0)) {
    if (Number.isFinite(images)) parts.push(formatCount(images, 'image', 'images'))
  }
  const videos = Number(counts.video ?? 0)
  if (params.videos || (Number.isFinite(videos) && videos > 0)) {
    if (Number.isFinite(videos)) parts.push(formatCount(videos, 'video', 'videos'))
  }
  const extras: Array<[string, string, string]> = [
    ['gif', 'gif', 'gifs'],
    ['audio', 'audio', 'audio'],
    ['document', 'document', 'documents'],
  ]
  for (const [key, singular, plural] of extras) {
    const count = Number(counts[key] ?? 0)
    if (Number.isFinite(count) && count > 0) parts.push(formatCount(count, singular, plural))
  }
  return parts.length > 0 ? parts.join(' · ') : null
}

type JobCardProps = {
  job: Job
  featured?: boolean
  busy?: boolean
  startBlocked?: boolean
  onStop: (job: Job) => void
  onStart: (job: Job) => void
}

export function JobCard({ job, featured, busy, startBlocked, onStop, onStart }: JobCardProps) {
  const live = isLiveJob(job.status)
  const stopped = isStoppedJob(job.status)
  const peer = jobSeedPeer(job)
  const when = formatAddedAt(job.started_at ?? job.created_at)
  const detail = jobDetail(job)
  const stats = jobStatsLine(job)
  const showActions = live || stopped

  return (
    <article className={featured ? h.jobFeatured : h.jobRow} data-status={job.status}>
      <PeerAvatar peer={peer} />
      <div className={h.jobBody}>
        <div className={h.jobTitleRow}>
          <span className={h.jobName}>{jobTitle(job)}</span>
          <span className={`${h.jobStatus} ${statusClass(job.status)}`}>{statusLabel(job.status)}</span>
        </div>
        <div className={h.jobMeta}>
          {live ? <LoadingText>{detail}</LoadingText> : detail}
          {when ? ` · ${when}` : ''}
        </div>
        {stats ? <div className={h.jobStats}>{stats}</div> : null}
      </div>
      {showActions ? (
        <div className={h.jobActions}>
          <button
            type="button"
            className={h.jobIconBtn}
            disabled={busy || !live}
            aria-label="Pause"
            title="Pause"
            onClick={() => onStop(job)}
          >
            <Pause size={16} strokeWidth={1.75} aria-hidden />
          </button>
          <button
            type="button"
            className={h.jobIconBtn}
            disabled={busy || live || startBlocked || job.task_type !== 'forward_snowball'}
            aria-label="Play"
            title="Play"
            onClick={() => onStart(job)}
          >
            <Play size={16} strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      ) : null}
    </article>
  )
}

export function JobList({
  jobs,
  busy,
  startBlocked,
  onStop,
  onStart,
}: {
  jobs: Job[]
  busy?: boolean
  startBlocked?: boolean
  onStop: (job: Job) => void
  onStart: (job: Job) => void
}) {
  if (jobs.length === 0) return null
  return (
    <div className={h.jobList} role="list" aria-label="Snowball jobs">
      {jobs.map((job) => (
        <div key={job.id} role="listitem">
          <JobCard
            job={job}
            busy={busy}
            startBlocked={startBlocked}
            onStop={onStop}
            onStart={onStart}
          />
        </div>
      ))}
    </div>
  )
}

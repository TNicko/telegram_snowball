import type { MediaBucket, Peer } from '../lib/api'
import { formatAddedAt, formatMaxMediaBytes, peerTypeLabel } from '../lib/peer'
import { PeerAvatar } from './PeerAvatar'
import t from './CatalogPeerTable.module.css'

const MEDIA_LABELS: { key: keyof NonNullable<Peer['media']>; label: string }[] = [
  { key: 'image', label: 'Images' },
  { key: 'video', label: 'Videos' },
  { key: 'audio', label: 'Audio' },
  { key: 'gif', label: 'Gif' },
  { key: 'document', label: 'Document' },
]

function dash() {
  return <span className={t.dash}>—</span>
}

function formatCount(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString()
}

function MediaValue({ bucket }: { bucket: MediaBucket | null | undefined }) {
  if (!bucket) return dash()
  const complete = bucket.downloaded >= bucket.total
  return (
    <span
      className={`${t.mediaValue}${complete ? '' : ` ${t.mediaPartial}`}`}
      title={`${bucket.downloaded.toLocaleString()} downloaded of ${bucket.total.toLocaleString()} in stored messages`}
    >
      <span>{bucket.downloaded.toLocaleString()}</span>
      <span className={t.mediaTotal}>/{bucket.total.toLocaleString()}</span>
    </span>
  )
}

function EmbedMark({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`${t.embedMark}${ok ? ` ${t.embedOk}` : ` ${t.embedNo}`}`} title={label}>
      <span className={t.embedLabel}>{label}</span>
      {ok ? (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M5 12.5 10 17.5 19 7"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      )}
    </span>
  )
}

export function CatalogPeerTable({
  peers,
  totalCount,
  emptyMessage,
}: {
  peers: Peer[]
  totalCount: number
  emptyMessage?: string
}) {
  return (
    <div className={t.table} role="table" aria-label="Peer catalog">
      <div className={`${t.toolbar}${totalCount === 0 ? ` ${t.toolbarEmpty}` : ''}`}>
        <span className={t.toolbarTitle}>
          {totalCount.toLocaleString()} {totalCount === 1 ? 'peer' : 'peers'}
        </span>
      </div>
      {peers.length === 0 ? (
        <p className={t.empty} role="status">
          {emptyMessage ?? 'No peers match that search.'}
        </p>
      ) : (
        <>
          <div className={`${t.head} ${t.row}`} role="row">
            <span className={t.headCell} role="columnheader">
              Peer
            </span>
            <span className={t.headCell} role="columnheader">
              Added
            </span>
            <span className={t.headCell} role="columnheader">
              Subscribers
            </span>
            <span className={`${t.headCell} ${t.statsHead}`} role="columnheader">
              Coverage
            </span>
          </div>
          <div className={t.body} role="rowgroup">
            {peers.map((peer) => (
              <CatalogPeerRow key={peer.external_id} peer={peer} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function CatalogPeerRow({ peer }: { peer: Peer }) {
  const label = (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id))
  const handle = peer.username ? `@${peer.username}` : null
  const subscribers = peer.participants_count
  const exclusions: string[] = []
  if (peer.videos_excluded) exclusions.push('Videos excluded')
  const maxLabel = formatMaxMediaBytes(peer.max_media_bytes)
  if (peer.large_excluded) {
    exclusions.push(maxLabel ? `Files over ${maxLabel} excluded` : 'Large files excluded')
  }

  return (
    <div className={`${t.row} ${t.bodyRow}`} role="row">
      <div className={`${t.cell} ${t.peerCell}`} role="cell" title={String(peer.external_id)}>
        <PeerAvatar peer={peer} />
        <span className={t.peerStack}>
          <span className={t.peerTitle}>{label}</span>
          <span className={t.peerHandle}>
            {peerTypeLabel(peer.peer_type)}
            {handle ? ` · ${handle}` : ''}
          </span>
        </span>
      </div>
      <span className={`${t.cell} ${t.dateCell}`} role="cell" title={peer.created_at}>
        {formatAddedAt(peer.created_at)}
      </span>
      <span className={`${t.cell} ${t.subsCell}`} role="cell">
        {subscribers == null ? dash() : formatCount(subscribers)}
      </span>
      <div className={`${t.cell} ${t.statsCell}`} role="cell">
        <div className={t.stats}>
          <span className={t.stat}>
            <span className={t.statLabel}>Posts</span>
            {peer.posts == null ? dash() : <span className={t.statValue}>{formatCount(peer.posts)}</span>}
          </span>
          {MEDIA_LABELS.map((item) => (
            <span className={t.stat} key={item.key}>
              <span className={t.statLabel}>{item.label}</span>
              <MediaValue bucket={peer.media?.[item.key]} />
            </span>
          ))}
        </div>
        <div className={t.embedRow}>
          <EmbedMark ok={Boolean(peer.embed_images)} label="Embed images" />
          <EmbedMark ok={Boolean(peer.embed_text)} label="Embed text" />
        </div>
        {exclusions.length > 0 ? (
          <div className={t.exclusions}>
            {exclusions.map((item) => (
              <span className={t.exclusion} key={item}>
                {item}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

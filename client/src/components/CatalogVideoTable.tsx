import { useState } from 'react'
import { Download, Loader2, Video } from 'lucide-react'
import { CatalogMediaPeerRow } from './CatalogImageTable'
import type { CatalogVideo } from '../lib/api'
import { formatAddedAt } from '../lib/peer'
import { formatBytes, formatDuration, formatResolution } from '../lib/format'
import { CatalogPager } from './CatalogPeerTable'
import { LoadingText } from './LoadingText'
import t from './CatalogPeerTable.module.css'
import m from './CatalogImageTable.module.css'
import v from './CatalogVideoTable.module.css'

function formatCount(value: number): string {
  return value.toLocaleString()
}

function VideoPlaceholder({
  sizeLabel,
  durationLabel,
}: {
  sizeLabel: string | null
  durationLabel: string | null
}) {
  return (
    <div className={`${m.thumbWrap} ${v.placeholder}`} aria-hidden>
      <Video size={28} strokeWidth={1.75} />
      {sizeLabel ? <span className={v.size}>{sizeLabel}</span> : null}
      {durationLabel ? <span className={v.duration}>{durationLabel}</span> : null}
    </div>
  )
}

function filenameFromHeader(header: string | null, fallback: string): string {
  if (!header) return fallback
  const utf = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf?.[1]) {
    try {
      return decodeURIComponent(utf[1])
    } catch {
      return fallback
    }
  }
  const quoted = header.match(/filename="([^"]+)"/i)
  if (quoted?.[1]) return quoted[1]
  const plain = header.match(/filename=([^;]+)/i)
  return plain?.[1]?.trim() || fallback
}

function VideoRow({ item }: { item: CatalogVideo }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sizeLabel = item.size_label || formatBytes(item.size_bytes)
  const durationLabel = formatDuration(item.duration)
  const resolution = formatResolution(item.width, item.height)

  const download = async () => {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(item.file_url)
      if (!response.ok) {
        let detail = response.statusText
        try {
          const body = (await response.json()) as { detail?: string }
          if (body.detail) detail = body.detail
        } catch {
          /* ignore */
        }
        throw new Error(detail)
      }
      const blob = await response.blob()
      const href = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = href
      link.download = filenameFromHeader(
        response.headers.get('Content-Disposition'),
        item.file_name || 'video.mp4',
      )
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(href)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not download this video')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`${m.row} ${m.bodyRow} ${v.row}`} role="row">
      <span className={`${m.cell} ${m.imageCell}`} role="cell">
        <VideoPlaceholder sizeLabel={sizeLabel} durationLabel={durationLabel} />
      </span>
      <div className={`${m.cell} ${m.sideCell}`} role="cell">
        <div className={m.meta}>
          <span className={m.metaItem}>{formatAddedAt(item.last_seen_at)}</span>
          {sizeLabel ? <span className={m.metaItem}>{sizeLabel}</span> : null}
          {durationLabel ? <span className={m.metaItem}>{durationLabel}</span> : null}
          {resolution ? <span className={m.metaItem}>{resolution}</span> : null}
          <span className={m.metaItem}>
            {formatCount(item.unique_peers)} unique {item.unique_peers === 1 ? 'peer' : 'peers'}
          </span>
          <span className={m.metaItem}>
            {formatCount(item.appearances)} {item.appearances === 1 ? 'appearance' : 'appearances'}
          </span>
          {item.persisted ? <span className={m.saved}>Saved</span> : null}
          {item.file_name ? (
            <span className={m.hash} title={item.file_name}>
              {item.file_name}
            </span>
          ) : null}
        </div>
        {(item.peers ?? []).length > 0 ? (
          <div className={m.peerList} aria-label="Unique peers for this video">
            {(item.peers ?? []).map((entry) => (
              <CatalogMediaPeerRow key={`${item.id}-${entry.peer.external_id}`} item={entry} />
            ))}
          </div>
        ) : (
          <p className={m.peerEmpty}>No peer links stored for this video.</p>
        )}
        {error ? <p className={v.error}>{error}</p> : null}
      </div>
      <span className={`${m.cell} ${m.actionsCell}`} role="cell">
        <button
          className={v.download}
          type="button"
          disabled={busy}
          onClick={() => void download()}
        >
          {busy ? <Loader2 size={14} strokeWidth={2} className={v.spin} /> : <Download size={14} strokeWidth={2} />}
          {busy ? 'Downloading' : 'Download'}
        </button>
      </span>
    </div>
  )
}

export function CatalogVideoTable({
  videos,
  total,
  page,
  pageSize,
  loading,
  emptyMessage,
  onPage,
}: {
  videos: CatalogVideo[]
  total: number
  page: number
  pageSize: number
  loading?: boolean
  emptyMessage?: string
  onPage: (page: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, pageCount)
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1
  const to = Math.min(safePage * pageSize, total)
  const pager =
    !loading && total > 0 ? (
      <CatalogPager
        page={safePage}
        pageCount={pageCount}
        from={from}
        to={to}
        total={total}
        onPage={onPage}
      />
    ) : null

  return (
    <div className={m.table} role="table" aria-label="Video catalog">
      <div className={`${t.toolbar}${total === 0 ? ` ${t.toolbarEmpty}` : ''}`}>
        <span className={t.toolbarTitle}>
          {loading && total === 0 ? (
            <LoadingText>Loading videos</LoadingText>
          ) : (
            `${total.toLocaleString()} ${total === 1 ? 'video' : 'videos'}`
          )}
        </span>
        {pager}
      </div>
      {loading && videos.length === 0 ? null : total === 0 ? (
        <p className={t.empty}>{emptyMessage ?? 'No videos stored yet.'}</p>
      ) : (
        <>
          <div className={m.body} role="rowgroup">
            {videos.map((item) => (
              <VideoRow key={item.id} item={item} />
            ))}
          </div>
          {pager ? <div className={t.footer}>{pager}</div> : null}
        </>
      )}
    </div>
  )
}

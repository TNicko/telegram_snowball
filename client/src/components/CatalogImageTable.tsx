import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { EllipsisVertical, Loader2, X } from 'lucide-react'
import { MediaFace, useMediaReady } from './ImageSkeleton'
import { api, type CatalogImage, type CatalogImagePeer, type Peer } from '../lib/api'
import { formatAddedAt, peerTypeLabel } from '../lib/peer'
import { CatalogPager } from './CatalogPeerTable'
import { LoadingText } from './LoadingText'
import { PeerAvatar } from './PeerAvatar'
import t from './CatalogPeerTable.module.css'
import m from './CatalogImageTable.module.css'

function formatCount(value: number): string {
  return value.toLocaleString()
}

function peerLabel(peer: Peer): string {
  return (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id))
}

function ImageThumb({ src }: { src: string }) {
  const { failed, loading, onReady, onFailed, imgRef } = useMediaReady(src)
  if (failed) {
    return <span className={m.thumbFallback} aria-hidden />
  }
  return (
    <MediaFace className={m.thumbWrap} loading={loading} label="Loading image">
      <img
        ref={imgRef}
        className={m.thumb}
        src={src}
        alt=""
        loading="lazy"
        onLoad={onReady}
        onError={onFailed}
      />
    </MediaFace>
  )
}

function ImageLightbox({ src, onClose }: { src: string; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const { failed, loading, onReady, onFailed, imgRef } = useMediaReady(src)

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  return createPortal(
    <div className={m.lightbox} onClick={onClose} role="presentation">
      <div
        className={m.lightboxStage}
        role="dialog"
        aria-modal="true"
        aria-label="Full image"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          ref={closeRef}
          className={m.lightboxClose}
          type="button"
          aria-label="Close"
          onClick={onClose}
        >
          <X size={18} strokeWidth={2.2} aria-hidden />
        </button>
        {failed ? (
          <p className={m.lightboxUnavailable}>Could not load this image.</p>
        ) : (
          <MediaFace className={m.lightboxFace} loading={loading} label="Loading image">
            <img
              ref={imgRef}
              className={m.lightboxImage}
              src={src}
              alt=""
              onLoad={onReady}
              onError={onFailed}
            />
          </MediaFace>
        )}
      </div>
    </div>,
    document.body,
  )
}

export function CatalogMediaPeerRow({ item }: { item: CatalogImagePeer }) {
  const handle = item.peer.username ? `@${item.peer.username}` : null
  const allForwarded = item.forwarded > 0 && item.forwarded >= item.appearances
  const someForwarded = item.forwarded > 0 && item.forwarded < item.appearances
  return (
    <div className={m.peerHit}>
      <PeerAvatar peer={item.peer} />
      <span className={m.peerStack}>
        <span className={m.peerTitle}>{peerLabel(item.peer)}</span>
        <span className={m.peerHandle}>
          {peerTypeLabel(item.peer.peer_type)}
          {handle ? ` · ${handle}` : ''}
        </span>
      </span>
      <span className={m.peerCount} title={`${formatCount(item.appearances)} in this peer`}>
        {formatCount(item.appearances)}
      </span>
      {item.forwarded > 0 ? (
        <span
          className={m.flag}
          title={
            someForwarded
              ? `${item.forwarded.toLocaleString()} of ${item.appearances.toLocaleString()} were forwards`
              : 'Forwarded'
          }
        >
          {allForwarded ? 'Fwd' : `Fwd ${item.forwarded.toLocaleString()}`}
        </span>
      ) : null}
    </div>
  )
}

function ImageRowMenu({
  persisted,
  busy,
  error,
  onDownload,
  onClear,
}: {
  persisted: boolean
  busy: boolean
  error: string | null
  onDownload: () => void
  onClear: () => void
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className={m.menuWrap} ref={wrapRef}>
      <button
        className={m.menuBtn}
        type="button"
        aria-label="Image actions"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        onClick={(event) => {
          event.stopPropagation()
          setOpen((value) => !value)
        }}
      >
        {busy ? <Loader2 size={16} strokeWidth={2} className={m.menuSpin} /> : <EllipsisVertical size={16} strokeWidth={2} />}
      </button>
      {open ? (
        <div className={m.menu} role="menu">
          {persisted ? (
            <button
              className={m.menuItem}
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setOpen(false)
                onClear()
              }}
            >
              Clear download
            </button>
          ) : (
            <button
              className={m.menuItem}
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setOpen(false)
                onDownload()
              }}
            >
              Download
            </button>
          )}
        </div>
      ) : null}
        {error && !open ? <p className={m.menuError}>{error}</p> : null}
    </div>
  )
}

function ImageRow({ item }: { item: CatalogImage }) {
  const [persisted, setPersisted] = useState(item.persisted)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const closePreview = useCallback(() => setPreviewOpen(false), [])

  useEffect(() => {
    setPersisted(item.persisted)
  }, [item.persisted, item.phash])

  const src = `${item.file_url}?p=${persisted ? 1 : 0}`

  const run = async (action: 'download' | 'clear') => {
    setBusy(true)
    setError(null)
    try {
      if (action === 'download') {
        await api.persistImage(item.phash)
        setPersisted(true)
      } else {
        await api.clearImagePersist(item.phash)
        setPersisted(false)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update this image')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`${m.row} ${m.bodyRow}`} role="row">
      <span className={`${m.cell} ${m.imageCell}`} role="cell">
        <button
          className={m.thumbBtn}
          type="button"
          aria-label="View full image"
          onClick={() => setPreviewOpen(true)}
        >
          <ImageThumb src={src} />
        </button>
        {previewOpen ? <ImageLightbox src={src} onClose={closePreview} /> : null}
      </span>
      <div className={`${m.cell} ${m.sideCell}`} role="cell">
        <div className={m.meta}>
          {item.score != null ? (
            <span className={m.metaItem}>{Math.round(item.score * 100)}% match</span>
          ) : null}
          <span className={m.metaItem}>{formatAddedAt(item.last_seen_at)}</span>
          <span className={m.metaItem}>
            {formatCount(item.unique_peers)} unique {item.unique_peers === 1 ? 'peer' : 'peers'}
          </span>
          <span className={m.metaItem}>
            {formatCount(item.appearances)} {item.appearances === 1 ? 'appearance' : 'appearances'}
          </span>
          {persisted ? <span className={m.saved}>Saved</span> : null}
          <span className={m.hash} title={item.phash}>
            {item.phash}
          </span>
        </div>
        {(item.peers ?? []).length > 0 ? (
          <div className={m.peerList} aria-label="Unique peers for this image">
            {(item.peers ?? []).map((entry) => (
              <CatalogMediaPeerRow key={`${item.phash}-${entry.peer.external_id}`} item={entry} />
            ))}
          </div>
        ) : (
          <p className={m.peerEmpty}>No peer links stored for this image.</p>
        )}
      </div>
      <span className={`${m.cell} ${m.actionsCell}`} role="cell">
        <ImageRowMenu
          persisted={persisted}
          busy={busy}
          error={error}
          onDownload={() => void run('download')}
          onClear={() => void run('clear')}
        />
      </span>
    </div>
  )
}

export type ImageSort = 'peers' | 'date'

export function CatalogImageTable({
  images,
  total,
  page,
  pageSize,
  sort = 'peers',
  loading,
  emptyMessage,
  onPage,
  onSort,
}: {
  images: CatalogImage[]
  total: number
  page: number
  pageSize: number
  sort?: ImageSort
  loading?: boolean
  emptyMessage?: string
  onPage: (page: number) => void
  onSort?: (sort: ImageSort) => void
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
    <div className={m.table} role="table" aria-label="Image catalog">
      <div className={`${t.toolbar}${total === 0 ? ` ${t.toolbarEmpty}` : ''}`}>
        <div className={m.toolbarLead}>
          <span className={t.toolbarTitle}>
            {loading && total === 0 ? (
              <LoadingText>Loading images</LoadingText>
            ) : (
              `${total.toLocaleString()} ${total === 1 ? 'image' : 'images'}`
            )}
          </span>
          {onSort ? (
            <div className={m.sortGroup} role="group" aria-label="Sort images">
              <button
                className={`${m.sortBtn}${sort === 'peers' ? ` ${m.sortBtnActive}` : ''}`}
                type="button"
                aria-pressed={sort === 'peers'}
                onClick={() => onSort('peers')}
              >
                Unique peers
              </button>
              <button
                className={`${m.sortBtn}${sort === 'date' ? ` ${m.sortBtnActive}` : ''}`}
                type="button"
                aria-pressed={sort === 'date'}
                onClick={() => onSort('date')}
              >
                Date
              </button>
            </div>
          ) : null}
        </div>
        {pager}
      </div>
      {loading && images.length === 0 ? null : total === 0 ? (
        <p className={t.empty}>{emptyMessage ?? 'No hashed images yet.'}</p>
      ) : (
        <>
          <div className={m.body} role="rowgroup">
            {images.map((item) => (
              <ImageRow key={item.phash} item={item} />
            ))}
          </div>
          {pager ? <div className={t.footer}>{pager}</div> : null}
        </>
      )}
    </div>
  )
}

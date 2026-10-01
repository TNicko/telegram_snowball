import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { AudioLines, FileText, Image as ImageIcon, ImagePlay, Video, X } from 'lucide-react'
import { MediaFace, useMediaReady } from './ImageSkeleton'
import { LoadingText } from './LoadingText'
import { api, type ForwardGraphNode, type GraphMessageDetail, type MessageMediaPreview } from '../lib/api'
import { formatBytes, formatDuration } from '../lib/format'
import { MEDIA_FILTER_LABELS, GRAPH_EDGE_LAYER_LABELS, type MediaFilterKey } from '../lib/graphConfig'
import m from './CatalogImageTable.module.css'
import v from './CatalogVideoTable.module.css'
import s from '../pages/GraphPage.module.css'

const dateFmt = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

function formatNodeDate(value: string | null | undefined): string | null {
  if (!value) return null
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return null
  return dateFmt.format(new Date(parsed))
}

function mediaLabel(kind: string | null | undefined): string {
  if (!kind) return 'None'
  return MEDIA_FILTER_LABELS[kind as MediaFilterKey] ?? kind
}

function storedMessageId(node: ForwardGraphNode): string | null {
  if (node.message_id) return node.message_id
  const match = /^m:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(node.id)
  return match?.[1] ?? null
}

function ImageThumb({ src, eager = false }: { src: string; eager?: boolean }) {
  const { failed, loading, onReady, onFailed, imgRef } = useMediaReady(src)
  if (failed) {
    return <span className={m.thumbFallback} aria-hidden />
  }
  return (
    <MediaFace className={m.thumbWrap} loading={loading} label="Loading image">
      <img
        key={src}
        ref={imgRef}
        className={m.thumb}
        src={src}
        alt=""
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        fetchPriority={eager ? 'high' : undefined}
        onLoad={onReady}
        onError={onFailed}
      />
    </MediaFace>
  )
}

function ImageLightbox({ src, onClose }: { src: string; onClose: () => void }) {
  const { failed, loading, onReady, onFailed, imgRef } = useMediaReady(src)
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
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
        <button className={m.lightboxClose} type="button" aria-label="Close" onClick={onClose}>
          <X size={18} strokeWidth={2.2} aria-hidden />
        </button>
        {failed ? (
          <p className={m.lightboxUnavailable}>Could not load this image.</p>
        ) : (
          <MediaFace className={m.lightboxFace} loading={loading} label="Loading image">
            <img
              key={src}
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

function MediaPlaceholder({
  icon,
  sizeLabel,
  detail,
}: {
  icon: 'video' | 'gif' | 'audio' | 'document' | 'image'
  sizeLabel: string | null
  detail: string | null
}) {
  const Icon =
    icon === 'video' ? Video : icon === 'gif' ? ImagePlay : icon === 'audio' ? AudioLines : icon === 'image' ? ImageIcon : FileText
  return (
    <div className={`${m.thumbWrap} ${v.placeholder}`} aria-hidden>
      <Icon size={28} strokeWidth={1.75} />
      {sizeLabel ? <span className={v.size}>{sizeLabel}</span> : null}
      {detail ? <span className={v.duration}>{detail}</span> : null}
    </div>
  )
}

function MessageMedia({ media, eager = false }: { media: MessageMediaPreview; eager?: boolean }) {
  const [open, setOpen] = useState(false)
  const sizeLabel = media.size_label || formatBytes(media.size_bytes)
  if (media.kind === 'image' && media.file_url) {
    return (
      <>
        <button className={m.thumbBtn} type="button" onClick={() => setOpen(true)} aria-label="Open image">
          <ImageThumb key={media.file_url} src={media.file_url} eager={eager} />
        </button>
        {open ? <ImageLightbox src={media.file_url} onClose={() => setOpen(false)} /> : null}
      </>
    )
  }
  if (media.kind === 'image') {
    return <MediaPlaceholder icon="image" sizeLabel={sizeLabel} detail={null} />
  }
  if (media.kind === 'video') {
    return <MediaPlaceholder icon="video" sizeLabel={sizeLabel} detail={formatDuration(media.duration)} />
  }
  if (media.kind === 'gif') {
    return <MediaPlaceholder icon="gif" sizeLabel={sizeLabel} detail={formatDuration(media.duration)} />
  }
  if (media.kind === 'audio') {
    return <MediaPlaceholder icon="audio" sizeLabel={sizeLabel} detail={formatDuration(media.duration)} />
  }
  return (
    <MediaPlaceholder icon="document" sizeLabel={sizeLabel} detail={media.mime_type || media.file_name || null} />
  )
}

export function GraphImageInspector({
  node,
  appearedIn,
  appearedInTitle,
}: {
  node: ForwardGraphNode
  appearedIn: string
  appearedInTitle?: string
}) {
  const src = node.photo_url || (node.phash ? `/api/images/${node.phash}/file` : null)
  const date = formatNodeDate(node.date)
  const numberFmt = new Intl.NumberFormat()

  return (
    <div className={`${s.inspector} ${s.inspectorMessage}`}>
      <div className={s.inspectorMessageHead}>
        <p className={s.inspectorTitle}>Shared image</p>
        {date ? <p className={s.inspectorId}>First seen {date}</p> : null}
      </div>
      {src ? (
        <div className={s.inspectorMedia}>
          <MessageMedia
            media={{
              kind: 'image',
              phash: node.phash,
              file_url: src,
            }}
            eager
          />
        </div>
      ) : (
        <p className={s.inspectorBodyMuted}>Image file is not on disk yet.</p>
      )}
      <dl className={s.inspectorStats}>
        <div>
          <dt>Unique peers</dt>
          <dd>{numberFmt.format(node.degree)}</dd>
        </div>
        <div>
          <dt>Appearances</dt>
          <dd>{numberFmt.format(node.forward_volume)}</dd>
        </div>
        <div>
          <dt>{GRAPH_EDGE_LAYER_LABELS.appearedIn}</dt>
          <dd title={appearedInTitle}>{appearedIn}</dd>
        </div>
      </dl>
    </div>
  )
}

export function GraphMessageInspector({
  node,
  sentTo,
  forwardedFrom,
  forwardedFromTitle,
}: {
  node: ForwardGraphNode
  sentTo: string
  forwardedFrom: string
  forwardedFromTitle?: string
}) {
  const [detail, setDetail] = useState<GraphMessageDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const messageId = storedMessageId(node)
    const originPeer = node.origin_peer_id
    const originMid = node.origin_telegram_id
    let cancelled = false
    setDetail(null)
    setError(null)
    setLoading(true)
    const request = messageId
      ? api.message(messageId)
      : originPeer != null && originMid != null
        ? api.lookupMessage(originPeer, originMid)
        : Promise.reject(new Error('Message not stored'))
    request
      .then((payload) => {
        if (!cancelled) setDetail(payload)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load this message')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [node.id, node.message_id, node.origin_peer_id, node.origin_telegram_id])

  const date = formatNodeDate(detail?.date ?? node.date)
  const kind = detail?.media_kind ?? node.media_kind
  const telegramId = detail?.telegram_message_id ?? node.telegram_message_id
  const body = detail?.content ?? (loading ? null : node.excerpt)

  return (
    <div className={`${s.inspector} ${s.inspectorMessage}`}>
      <div className={s.inspectorMessageHead}>
        <p className={s.inspectorTitle}>{date || 'Message'}</p>
        {telegramId != null ? <p className={s.inspectorId}>#{telegramId}</p> : null}
      </div>
      {loading ? (
        <p className={s.inspectorLoading}>
          <LoadingText>Loading message</LoadingText>
        </p>
      ) : null}
      {error ? <p className={s.inspectorError}>{error}</p> : null}
      {detail?.media ? (
        <div className={s.inspectorMedia}>
          <MessageMedia media={detail.media} eager />
        </div>
      ) : null}
      {body ? <p className={s.inspectorBody}>{body}</p> : !loading ? <p className={s.inspectorBodyMuted}>No text</p> : null}
      <dl className={s.inspectorStats}>
        <div>
          <dt>Date</dt>
          <dd>{date ?? '—'}</dd>
        </div>
        <div>
          <dt>Media</dt>
          <dd>{mediaLabel(kind)}</dd>
        </div>
        <div>
          <dt>{GRAPH_EDGE_LAYER_LABELS.sentTo}</dt>
          <dd>{sentTo}</dd>
        </div>
        <div>
          <dt>{GRAPH_EDGE_LAYER_LABELS.forwardedFrom}</dt>
          <dd title={forwardedFromTitle}>{forwardedFrom}</dd>
        </div>
      </dl>
    </div>
  )
}

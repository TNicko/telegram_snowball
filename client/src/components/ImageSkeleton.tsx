import { useState, type ReactNode } from 'react'
import s from './ImageSkeleton.module.css'

export function ImageSkeleton({
  className,
  label = 'Loading image',
}: {
  className?: string
  label?: string
}) {
  return (
    <span
      className={[s.skeleton, className].filter(Boolean).join(' ')}
      role="status"
      aria-label={label}
    />
  )
}

type MediaState = {
  src: string | null | undefined
  ready: boolean
  failed: boolean
}

export function useMediaReady(src: string | null | undefined) {
  const [state, setState] = useState<MediaState>({ src, ready: false, failed: false })
  if (state.src !== src) {
    setState({ src, ready: false, failed: false })
  }
  const ready = state.src === src && state.ready
  const failed = state.src === src && state.failed

  const onReady = () => {
    setState((current) =>
      current.src !== src || current.ready ? current : { src, ready: true, failed: false },
    )
  }
  const onFailed = () => {
    setState((current) =>
      current.src !== src || current.failed ? current : { src, ready: false, failed: true },
    )
  }

  const imgRef = (el: HTMLImageElement | null) => {
    if (!el || !src || el.getAttribute('src') !== src) return
    if (!el.complete) return
    if (el.naturalWidth > 0) onReady()
    else onFailed()
  }

  const videoRef = (el: HTMLVideoElement | null) => {
    if (!el || !src) return
    if (el.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) onReady()
  }

  return {
    ready,
    failed,
    loading: Boolean(src) && !ready && !failed,
    onReady,
    onFailed,
    imgRef,
    videoRef,
  }
}

export function MediaFace({
  className,
  loading,
  label = 'Loading image',
  children,
}: {
  className?: string
  loading: boolean
  label?: string
  children: ReactNode
}) {
  return (
    <span className={[s.face, className].filter(Boolean).join(' ')} data-loading={loading || undefined}>
      {loading ? <ImageSkeleton label={label} /> : null}
      {children}
    </span>
  )
}

import { useEffect, useRef } from 'react'
import type { Peer } from '../lib/api'
import { ImageSkeleton, useMediaReady } from './ImageSkeleton'
import sk from './ImageSkeleton.module.css'

export function PeerAvatar({ peer }: { peer: Peer }) {
  const src = peer.photo_url
  const isVideo = peer.photo_media_kind === 'video'
  const { failed, loading, onReady, onFailed, imgRef, videoRef } = useMediaReady(src)
  const playRef = useRef<HTMLVideoElement>(null)
  const initial = (peer.title ?? peer.username ?? '?').slice(0, 1)

  useEffect(() => {
    if (!src || failed || !isVideo) return
    const video = playRef.current
    if (!video) return
    void video.play().catch(() => undefined)
  }, [src, failed, isVideo])

  const setVideoRef = (el: HTMLVideoElement | null) => {
    playRef.current = el
    videoRef(el)
  }

  if (src && !failed && isVideo) {
    return (
      <div className={`avatar ${sk.face}`} data-loading={loading || undefined}>
        {loading ? <ImageSkeleton label="Loading photo" /> : null}
        <video
          ref={setVideoRef}
          src={src}
          autoPlay
          muted
          loop
          playsInline
          disablePictureInPicture
          preload="auto"
          onLoadedData={onReady}
          onError={onFailed}
        />
      </div>
    )
  }
  if (src && !failed) {
    return (
      <div className={`avatar ${sk.face}`} data-loading={loading || undefined}>
        {loading ? <ImageSkeleton label="Loading photo" /> : null}
        <img ref={imgRef} src={src} alt="" onLoad={onReady} onError={onFailed} />
      </div>
    )
  }
  return <div className="avatar">{initial}</div>
}

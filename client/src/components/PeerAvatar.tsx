import { useEffect, useRef, useState } from 'react'
import type { Peer } from '../lib/api'

export function PeerAvatar({ peer }: { peer: Peer }) {
  const [failed, setFailed] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const isVideo = peer.photo_media_kind === 'video'
  const src = peer.photo_url
  const initial = (peer.title ?? peer.username ?? '?').slice(0, 1)

  useEffect(() => {
    setFailed(false)
  }, [src, isVideo])

  useEffect(() => {
    if (!src || failed || !isVideo) return
    const video = videoRef.current
    if (!video) return
    void video.play().catch(() => undefined)
  }, [src, failed, isVideo])

  if (src && !failed && isVideo) {
    return (
      <div className="avatar">
        <video
          ref={videoRef}
          src={src}
          autoPlay
          muted
          loop
          playsInline
          disablePictureInPicture
          preload="auto"
          onError={() => setFailed(true)}
        />
      </div>
    )
  }
  if (src && !failed) {
    return (
      <div className="avatar">
        <img src={src} alt="" onError={() => setFailed(true)} />
      </div>
    )
  }
  return <div className="avatar">{initial}</div>
}

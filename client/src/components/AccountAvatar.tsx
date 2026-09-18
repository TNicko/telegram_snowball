import { useEffect, useRef, useState } from 'react'
import placeholder from '../assets/user-placeholder.svg?url'

type Size = 'sm' | 'md'
type MediaKind = 'image' | 'video' | null | undefined

export function AccountAvatar({
  photoUrl,
  mediaKind,
  name,
  size = 'md',
}: {
  photoUrl?: string | null
  mediaKind?: MediaKind
  name: string
  size?: Size
}) {
  const [failed, setFailed] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const isVideo = mediaKind === 'video'

  useEffect(() => {
    setFailed(false)
  }, [photoUrl, mediaKind])

  useEffect(() => {
    if (!photoUrl || failed || !isVideo) return
    const video = videoRef.current
    if (!video) return
    void video.play().catch(() => undefined)
  }, [photoUrl, failed, isVideo])

  const src = photoUrl && !failed ? photoUrl : placeholder
  const showVideo = Boolean(photoUrl) && !failed && isVideo

  return (
    <div className={`accountAvatar accountAvatar-${size}`}>
      {showVideo ? (
        <video
          ref={videoRef}
          src={src}
          autoPlay
          muted
          loop
          playsInline
          disablePictureInPicture
          preload="auto"
          aria-label={name}
          onError={() => setFailed(true)}
        />
      ) : (
        <img src={src} alt={name} onError={() => setFailed(true)} />
      )}
    </div>
  )
}

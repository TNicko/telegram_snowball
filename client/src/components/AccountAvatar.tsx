import { useEffect, useRef } from 'react'
import placeholder from '../assets/user-placeholder.svg?url'
import { ImageSkeleton, useMediaReady } from './ImageSkeleton'
import sk from './ImageSkeleton.module.css'

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
  const remote = Boolean(photoUrl)
  const { failed, loading, onReady, onFailed, imgRef, videoRef } = useMediaReady(photoUrl)
  const playRef = useRef<HTMLVideoElement>(null)
  const isVideo = mediaKind === 'video'
  const showVideo = remote && !failed && isVideo
  const src = photoUrl && !failed ? photoUrl : placeholder
  const showSkeleton = remote && loading

  useEffect(() => {
    if (!photoUrl || failed || !isVideo) return
    const video = playRef.current
    if (!video) return
    void video.play().catch(() => undefined)
  }, [photoUrl, failed, isVideo])

  const setVideoRef = (el: HTMLVideoElement | null) => {
    playRef.current = el
    videoRef(el)
  }

  return (
    <div
      className={`accountAvatar accountAvatar-${size} ${sk.face}`}
      data-loading={showSkeleton || undefined}
    >
      {showSkeleton ? <ImageSkeleton label="Loading photo" /> : null}
      {showVideo ? (
        <video
          ref={setVideoRef}
          src={src}
          autoPlay
          muted
          loop
          playsInline
          disablePictureInPicture
          preload="auto"
          aria-label={name}
          onLoadedData={onReady}
          onError={onFailed}
        />
      ) : (
        <img
          ref={remote && !failed ? imgRef : undefined}
          src={src}
          alt={name}
          onLoad={remote && !failed ? onReady : undefined}
          onError={onFailed}
        />
      )}
    </div>
  )
}

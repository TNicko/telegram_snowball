import { useEffect, useState } from 'react'
import { api, type CatalogStorageStats } from '../lib/api'
import s from './CatalogStorageBar.module.css'

const countFmt = new Intl.NumberFormat()

function Stat({
  label,
  count,
  size,
}: {
  label: string
  count: string
  size: string
}) {
  return (
    <div className={s.item}>
      <p className={s.label}>{label}</p>
      <p className={s.count}>{count}</p>
      <p className={s.meta}>{size}</p>
    </div>
  )
}

export function CatalogStorageBar() {
  const [stats, setStats] = useState<CatalogStorageStats | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      void api
        .catalogStats()
        .then((next) => {
          if (!cancelled) setStats(next)
        })
        .catch(() => undefined)
    }
    load()
    const timer = window.setInterval(load, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const messages = stats?.messages
  const images = stats?.images
  const hashed = stats?.hashed_images
  const videos = stats?.videos

  return (
    <div className={s.bar} aria-label="Catalog storage" aria-busy={stats ? undefined : 'true'}>
      <Stat
        label="Messages"
        count={messages ? countFmt.format(messages.count) : '—'}
        size={messages?.bytes_label ?? '—'}
      />
      <Stat
        label="Downloaded Images"
        count={images ? countFmt.format(images.count) : '—'}
        size={images?.bytes_label ?? '—'}
      />
      <Stat
        label="Hashed Images"
        count={hashed ? countFmt.format(hashed.count) : '—'}
        size={hashed?.bytes_label ?? '—'}
      />
      <Stat
        label="Downloaded Videos"
        count={videos ? countFmt.format(videos.count) : '—'}
        size={videos?.bytes_label ?? '—'}
      />
    </div>
  )
}

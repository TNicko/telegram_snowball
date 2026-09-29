export function modelDownloadProgressLabel(
  progress?: Record<string, unknown> | null,
  opts?: { compact?: boolean },
): string {
  const compact = Boolean(opts?.compact)
  const percent = Number(progress?.percent)
  const hasPercent = Number.isFinite(percent) && percent >= 0
  if (!hasPercent) return 'Downloading weights…'
  if (compact) return `Downloading weights · ${Math.round(percent)}%`
  const detail = progress?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return `Downloading weights · ${Math.round(percent)}%`
}

export function formatBytes(bytes: number | null | undefined): string | null {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return null
  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const
  let value = bytes
  let unit: (typeof units)[number] = 'B'
  for (const next of units) {
    unit = next
    if (value < 1024 || next === 'TB') break
    value /= 1024
  }
  if (unit === 'B') return `${Math.round(value)} B`
  const text = value >= 10 ? value.toFixed(0) : value.toFixed(1)
  return `${text.replace(/\.0$/, '')} ${unit}`
}

export function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`
}

export function formatResolution(width: number | null | undefined, height: number | null | undefined): string | null {
  if (!width || !height) return null
  return `${width.toLocaleString()}×${height.toLocaleString()}`
}

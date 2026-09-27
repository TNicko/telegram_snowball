import type { ForwardGraphNode, Peer } from './api'

export const PEER_TYPES = ['channel', 'megagroup', 'chat', 'user', 'bot'] as const
export type PeerType = (typeof PEER_TYPES)[number]

export function peerTypeLabel(peerType: string): string {
  switch (peerType) {
    case 'channel':
      return 'Channel'
    case 'megagroup':
      return 'Megagroup'
    case 'chat':
      return 'Chat'
    case 'user':
      return 'User'
    case 'bot':
      return 'Bot'
    default:
      return peerType
  }
}

export function formatCoverageWindow(
  after: string | null | undefined,
  before: string | null | undefined,
): string {
  const from = formatCoverageDate(after)
  const to = formatCoverageDate(before)
  if (from && to) return from === to ? from : `${from} – ${to}`
  if (to) return `Through ${to}`
  if (from) return `From ${from}`
  return 'Not scraped'
}

export function formatCoverageDate(iso: string | null | undefined): string | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
}

/** Place a scraped window on the [origin, now] timeline as left/width percentages. */
export function coverageTimelineSegment(
  origin: string | null | undefined,
  end: string | null | undefined,
  after: string | null | undefined,
  before: string | null | undefined,
  fill?: number | null,
): { left: number; width: number } {
  const startMs = origin ? Date.parse(origin) : Number.NaN
  const endMs = end ? Date.parse(end) : Number.NaN
  const afterMs = after ? Date.parse(after) : Number.NaN
  const beforeMs = before ? Date.parse(before) : Number.NaN
  if (Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs && Number.isFinite(afterMs)) {
    const span = endMs - startMs
    const clampedAfter = Math.min(endMs, Math.max(startMs, afterMs))
    const clampedBefore = Number.isFinite(beforeMs)
      ? Math.min(endMs, Math.max(clampedAfter, beforeMs))
      : endMs
    const left = ((clampedAfter - startMs) / span) * 100
    const right = ((clampedBefore - startMs) / span) * 100
    return { left: clampPct(left), width: clampPct(right - left) }
  }
  const walked = fill != null && Number.isFinite(fill) ? Math.max(0, Math.min(1, fill)) : 0
  if (walked <= 0) return { left: 0, width: 0 }
  const width = walked * 100
  return { left: clampPct(100 - width), width: clampPct(width) }
}

export function formatAddedAt(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const now = new Date()
  const sameYear = date.getFullYear() === now.getFullYear()
  const datePart = new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
  }).format(date)
  const sameDay =
    sameYear && date.getMonth() === now.getMonth() && date.getDate() === now.getDate()
  if (!sameDay) return datePart
  const timePart = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date)
  return `${datePart} ${timePart}`
}

export function formatMaxMediaBytes(bytes: number | null | undefined): string | null {
  if (bytes == null || bytes <= 0) return null
  const mb = bytes / 1_000_000
  if (mb >= 1) {
    const rounded = mb >= 10 ? Math.round(mb) : Math.round(mb * 10) / 10
    return `${rounded} MB`
  }
  const kb = Math.max(1, Math.round(bytes / 1000))
  return `${kb} KB`
}

export function peerMatchesQuery(peer: {
  external_id: number
  peer_type: string
  title: string | null
  username: string | null
}, query: string): boolean {
  const q = query.trim().toLowerCase().replace(/^@/, '')
  if (!q) return true
  const title = (peer.title ?? '').toLowerCase()
  const username = (peer.username ?? '').toLowerCase()
  const type = peer.peer_type.toLowerCase()
  const id = String(peer.external_id)
  return title.includes(q) || username.includes(q) || type.includes(q) || id.includes(q)
}

export function graphPeerAsPeer(node: ForwardGraphNode): Peer {
  return {
    external_id: node.external_id,
    peer_type: node.peer_type,
    title: node.label,
    username: node.username,
    photo_path: null,
    photo_url: node.photo_url ?? null,
    photo_media_kind: node.photo_media_kind ?? null,
    is_scraping: node.is_scraping,
    scrape_detail: node.scrape_detail ?? null,
    messages_scraped: 0,
    created_at: '',
    updated_at: '',
  }
}

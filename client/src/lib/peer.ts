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

export function formatAddedAt(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  if (sameDay) {
    return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date)
  }
  const sameYear = date.getFullYear() === now.getFullYear()
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
  }).format(date)
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

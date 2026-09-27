import { useRef, useState, type MouseEvent } from 'react'
import { X } from 'lucide-react'
import type { CatalogMessage, Peer } from '../lib/api'
import { formatAddedAt, peerTypeLabel } from '../lib/peer'
import { CatalogPager } from './CatalogPeerTable'
import { LoadingText } from './LoadingText'
import { PeerAvatar } from './PeerAvatar'
import t from './CatalogPeerTable.module.css'
import m from './CatalogMessageTable.module.css'

function clickLooksLikeSelection(event: MouseEvent, origin: { x: number; y: number }) {
  if (Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > 4) return true
  const selection = window.getSelection()
  return Boolean(selection && !selection.isCollapsed && selection.toString().length > 0)
}

function mediaLabel(kind: CatalogMessage['media_kind']): string | null {
  switch (kind) {
    case 'image':
      return 'Image'
    case 'video':
      return 'Video'
    case 'gif':
      return 'Gif'
    case 'audio':
      return 'Audio'
    case 'document':
      return 'Document'
    default:
      return null
  }
}

function peerLabel(peer: Peer): string {
  return (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id))
}

export function CatalogMessageTable({
  messages,
  total,
  page,
  pageSize,
  loading,
  emptyMessage,
  onPage,
}: {
  messages: CatalogMessage[]
  total: number
  page: number
  pageSize: number
  loading?: boolean
  emptyMessage?: string
  onPage: (page: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, pageCount)
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1
  const to = Math.min(safePage * pageSize, total)
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set())
  const pointerOrigin = useRef({ x: 0, y: 0 })
  const pager =
    !loading && total > 0 ? (
      <CatalogPager
        page={safePage}
        pageCount={pageCount}
        from={from}
        to={to}
        total={total}
        onPage={onPage}
      />
    ) : null

  const toggleRow = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className={m.table} role="table" aria-label="Message catalog">
      <div className={`${t.toolbar}${total === 0 ? ` ${t.toolbarEmpty}` : ''}`}>
        <span className={t.toolbarTitle}>
          {loading && total === 0 ? <LoadingText>Loading messages</LoadingText> : `${total.toLocaleString()} messages`}
        </span>
        {pager}
      </div>
      {loading && messages.length === 0 ? null : total === 0 ? (
        <p className={t.empty}>{emptyMessage ?? 'No messages stored yet.'}</p>
      ) : (
        <>
          <div className={`${m.head} ${m.row}`} role="row">
            <span className={m.headCell} role="columnheader">
              Date
            </span>
            <span className={m.headCell} role="columnheader">
              Peer
            </span>
            <span className={m.headCell} role="columnheader">
              Message
            </span>
          </div>
          <div className={m.body} role="rowgroup">
            {messages.map((item) => {
              const media = mediaLabel(item.media_kind)
              const text = (item.content ?? '').trim()
              const open = expanded.has(item.id)
              return (
                <div
                  key={item.id}
                  className={`${m.row} ${m.bodyRow}${open ? ` ${m.bodyRowExpanded}` : ''}`}
                  role="row"
                  tabIndex={0}
                  aria-expanded={open}
                  onPointerDown={(event) => {
                    if (event.button !== 0) return
                    pointerOrigin.current = { x: event.clientX, y: event.clientY }
                  }}
                  onClick={(event) => {
                    if (event.button !== 0) return
                    if (clickLooksLikeSelection(event, pointerOrigin.current)) return
                    toggleRow(item.id)
                  }}
                  onKeyDown={(event) => {
                    if (event.key !== 'Enter' && event.key !== ' ') return
                    event.preventDefault()
                    toggleRow(item.id)
                  }}
                >
                  <span className={`${m.cell} ${t.dateCell} ${m.dateCell}`} role="cell">
                    {formatAddedAt(item.date)}
                  </span>
                  <span className={`${m.cell} ${t.peerCell} ${m.peerCell}`} role="cell">
                    <PeerAvatar peer={item.peer} />
                    <span className={t.peerStack}>
                      <span className={t.peerTitle}>{peerLabel(item.peer)}</span>
                      <span className={t.peerHandle}>
                        {peerTypeLabel(item.peer.peer_type)}
                        {item.peer.username ? ` · @${item.peer.username}` : ''}
                      </span>
                    </span>
                  </span>
                  <span className={`${m.cell} ${m.messageCell}`} role="cell">
                    <span className={`${m.messageText}${text ? '' : ` ${m.placeholder}`}`}>
                      {text || 'no message'}
                    </span>
                    <span className={m.messageFlags}>
                      {item.score != null ? (
                        <span className={m.flag}>{Math.round(item.score * 100)}%</span>
                      ) : null}
                      {item.forwarded ? <span className={m.flag}>Fwd</span> : null}
                      {media ? <span className={m.flag}>{media}</span> : null}
                    </span>
                  </span>
                </div>
              )
            })}
          </div>
          {pager ? <div className={t.footer}>{pager}</div> : null}
        </>
      )}
    </div>
  )
}

export function PeerFilterChip({ peer, onClear }: { peer: Peer; onClear: () => void }) {
  return (
    <button type="button" className={m.chip} onClick={onClear} aria-label={`Clear filter ${peerLabel(peer)}`}>
      <PeerAvatar peer={peer} />
      <span className={m.chipLabel}>{peerLabel(peer)}</span>
      <X size={14} strokeWidth={2} aria-hidden />
    </button>
  )
}

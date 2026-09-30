import { useEffect, useMemo, useState } from 'react'
import {
  AudioLines,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronsLeft,
  ChevronsRight,
  FileText,
  Image,
  ImagePlay,
  Video,
  type LucideIcon,
} from 'lucide-react'
import type { EmbedBucket, MediaBucket, Peer } from '../lib/api'
import { formatAddedAt, formatMaxMediaBytes, PEER_TYPES, peerTypeLabel } from '../lib/peer'
import { LoadingText } from './LoadingText'
import { PeerAvatar } from './PeerAvatar'
import t from './CatalogPeerTable.module.css'

const PAGE_SIZE = 50

const MEDIA_ITEMS: { key: keyof NonNullable<Peer['media']>; label: string; icon: LucideIcon }[] = [
  { key: 'image', label: 'Images', icon: Image },
  { key: 'video', label: 'Videos', icon: Video },
  { key: 'audio', label: 'Audio', icon: AudioLines },
  { key: 'gif', label: 'Gif', icon: ImagePlay },
  { key: 'document', label: 'Files', icon: FileText },
]

type SortKey = 'peer' | 'added' | 'subscribers' | 'posts'
type SortDir = 'asc' | 'desc'
type SortState = { key: SortKey; dir: SortDir }

function dash() {
  return <span className={t.dash}>—</span>
}

function formatCount(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString()
}

function peerLabel(peer: Peer): string {
  return (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id))
}

function addedAt(peer: Peer): number {
  return new Date(peer.created_at ?? peer.updated_at).getTime()
}

function mediaTotal(peer: Peer): number {
  const media = peer.media
  if (!media) return 0
  return MEDIA_ITEMS.reduce((n, item) => n + (media[item.key]?.total ?? 0), 0)
}

function cmpNum(a: number | null | undefined, b: number | null | undefined, dir: SortDir): number {
  const aMissing = a == null
  const bMissing = b == null
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1
  return dir === 'asc' ? a - b : b - a
}

function sortPeers(peers: Peer[], sort: SortState): Peer[] {
  const { key, dir } = sort
  return peers.slice().sort((a, b) => {
    if (a.is_scraping !== b.is_scraping) return a.is_scraping ? -1 : 1
    let result = 0
    if (key === 'peer') {
      result = peerLabel(a).localeCompare(peerLabel(b), undefined, { sensitivity: 'base', numeric: true })
      if (dir === 'desc') result = -result
    } else if (key === 'added') {
      result = cmpNum(addedAt(a), addedAt(b), dir)
    } else if (key === 'subscribers') {
      result = cmpNum(a.participants_count, b.participants_count, dir)
    } else {
      result = cmpNum(a.posts, b.posts, dir)
      if (result === 0) result = cmpNum(a.forwards_total, b.forwards_total, dir)
      if (result === 0) result = cmpNum(mediaTotal(a), mediaTotal(b), dir)
    }
    if (result !== 0) return result
    return b.external_id - a.external_id
  })
}

function defaultDir(key: SortKey): SortDir {
  return key === 'peer' ? 'asc' : 'desc'
}

function pageWindow(current: number, total: number): Array<number | 'ellipsis'> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const keep = new Set([1, total, current, current - 1, current + 1])
  if (current <= 3) [1, 2, 3, 4, 5].forEach((n) => keep.add(n))
  if (current >= total - 2) [total - 4, total - 3, total - 2, total - 1, total].forEach((n) => keep.add(n))
  const nums = [...keep].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b)
  const out: Array<number | 'ellipsis'> = []
  for (const n of nums) {
    const prev = out[out.length - 1]
    if (typeof prev === 'number' && n - prev > 1) out.push('ellipsis')
    out.push(n)
  }
  return out
}

function MediaValue({
  bucket,
  label,
  icon: Icon,
}: {
  bucket: MediaBucket | null | undefined
  label: string
  icon: LucideIcon
}) {
  if (!bucket) {
    return (
      <span className={t.stat} title={label}>
        <Icon size={13} strokeWidth={2} className={t.mediaIcon} aria-hidden />
        <span className={t.srOnly}>{label}</span>
        {dash()}
      </span>
    )
  }
  const covered = bucket.hashed ?? bucket.downloaded
  const complete = covered >= bucket.total
  const title =
    bucket.hashed != null
      ? `${label}: ${bucket.hashed.toLocaleString()} of ${bucket.total.toLocaleString()} hashed · ${bucket.downloaded.toLocaleString()} downloaded`
      : `${label}: ${bucket.downloaded.toLocaleString()} of ${bucket.total.toLocaleString()}`
  return (
    <span className={`${t.stat}${complete ? '' : ` ${t.mediaPartial}`}`} title={title}>
      <Icon size={13} strokeWidth={2} className={t.mediaIcon} aria-hidden />
      <span className={t.srOnly}>{label}</span>
      <span className={t.mediaValue}>
        <span>{covered.toLocaleString()}</span>
        <span className={t.mediaTotal}>/{bucket.total.toLocaleString()}</span>
      </span>
    </span>
  )
}

function EmbedValue({ bucket, label }: { bucket: EmbedBucket | null | undefined; label: string }) {
  if (!bucket) {
    return (
      <span className={t.stat} title={label}>
        <span className={t.statLabel}>{label}</span>
        {dash()}
      </span>
    )
  }
  const complete = bucket.done >= bucket.total
  const title = `${label}: ${bucket.done.toLocaleString()} of ${bucket.total.toLocaleString()}`
  return (
    <span className={`${t.stat}${complete ? '' : ` ${t.mediaPartial}`}`} title={title}>
      <span className={t.statLabel}>{label}</span>
      <span className={t.mediaValue}>
        <span>{bucket.done.toLocaleString()}</span>
        <span className={t.mediaTotal}>/{bucket.total.toLocaleString()}</span>
      </span>
    </span>
  )
}

export function CatalogPager({
  page,
  pageCount,
  from,
  to,
  total,
  onPage,
}: {
  page: number
  pageCount: number
  from: number
  to: number
  total: number
  onPage: (page: number) => void
}) {
  const pages = pageWindow(page, pageCount)
  return (
    <nav className={t.pager} aria-label="Catalog pages">
      <span className={t.pagerRange}>
        {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
      </span>
      <button
        type="button"
        className={t.pagerBtn}
        disabled={page <= 1}
        aria-label="First page"
        onClick={() => onPage(1)}
      >
        <ChevronsLeft size={14} strokeWidth={2} />
      </button>
      <button
        type="button"
        className={t.pagerBtn}
        disabled={page <= 1}
        aria-label="Previous page"
        onClick={() => onPage(page - 1)}
      >
        <ChevronLeft size={14} strokeWidth={2} />
      </button>
      {pages.map((item, i) =>
        item === 'ellipsis' ? (
          <span key={`e${i}`} className={t.pagerEllipsis}>
            …
          </span>
        ) : (
          <button
            key={item}
            type="button"
            className={`${t.pagerBtn}${item === page ? ` ${t.pagerBtnActive}` : ''}`}
            aria-label={`Page ${item}`}
            aria-current={item === page ? 'page' : undefined}
            onClick={() => onPage(item)}
          >
            {item}
          </button>
        ),
      )}
      <button
        type="button"
        className={t.pagerBtn}
        disabled={page >= pageCount}
        aria-label="Next page"
        onClick={() => onPage(page + 1)}
      >
        <ChevronRight size={14} strokeWidth={2} />
      </button>
      <button
        type="button"
        className={t.pagerBtn}
        disabled={page >= pageCount}
        aria-label="Last page"
        onClick={() => onPage(pageCount)}
      >
        <ChevronsRight size={14} strokeWidth={2} />
      </button>
    </nav>
  )
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string
  sortKey: SortKey
  sort: SortState
  onSort: (key: SortKey) => void
}) {
  const active = sort.key === sortKey
  const ariaSort = active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'
  return (
    <span className={t.headCell} role="columnheader" aria-sort={ariaSort}>
      <button type="button" className={t.sortBtn} onClick={() => onSort(sortKey)}>
        {label}
        {active ? (
          sort.dir === 'asc' ? (
            <ChevronUp size={12} strokeWidth={2.4} aria-hidden />
          ) : (
            <ChevronDown size={12} strokeWidth={2.4} aria-hidden />
          )
        ) : null}
      </button>
    </span>
  )
}

export function CatalogPeerTable({
  peers,
  totalCount,
  query = '',
  filterKey = '',
  typeFilter = '',
  onTypeFilter,
  onPeerClick,
  emptyMessage,
  loading = false,
}: {
  peers: Peer[]
  totalCount: number
  query?: string
  filterKey?: string
  typeFilter?: string
  onTypeFilter?: (type: string) => void
  onPeerClick?: (peer: Peer) => void
  emptyMessage?: string
  loading?: boolean
}) {
  const [sort, setSort] = useState<SortState>({ key: 'added', dir: 'desc' })
  const [page, setPage] = useState(1)

  useEffect(() => {
    setPage(1)
  }, [query, filterKey])

  const sorted = useMemo(() => sortPeers(peers, sort), [peers, sort])
  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const fromIndex = (safePage - 1) * PAGE_SIZE
  const pageRows = sorted.slice(fromIndex, fromIndex + PAGE_SIZE)
  const from = sorted.length === 0 ? 0 : fromIndex + 1
  const to = Math.min(fromIndex + PAGE_SIZE, sorted.length)

  const onSort = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: defaultDir(key) },
    )
    setPage(1)
  }

  const onToolbarSort = (key: 'added' | 'posts') => {
    setSort({ key, dir: 'desc' })
    setPage(1)
  }

  const pager =
    !loading && sorted.length > 0 ? (
      <CatalogPager
        page={safePage}
        pageCount={pageCount}
        from={from}
        to={to}
        total={sorted.length}
        onPage={setPage}
      />
    ) : null

  return (
    <div className={t.table} role="table" aria-label="Peer catalog">
      <div className={`${t.toolbar}${loading || totalCount === 0 ? ` ${t.toolbarEmpty}` : ''}`}>
        <div className={t.toolbarLead}>
          <span className={t.toolbarTitle}>
            {loading ? (
              <LoadingText>Loading peers</LoadingText>
            ) : (
              `${totalCount.toLocaleString()} ${totalCount === 1 ? 'peer' : 'peers'}`
            )}
          </span>
          {loading || totalCount === 0 ? null : (
            <div className={t.sortGroup} role="group" aria-label="Sort peers">
              <button
                className={`${t.modeSortBtn}${sort.key === 'added' ? ` ${t.modeSortBtnActive}` : ''}`}
                type="button"
                aria-pressed={sort.key === 'added'}
                onClick={() => onToolbarSort('added')}
              >
                Date
              </button>
              <button
                className={`${t.modeSortBtn}${sort.key === 'posts' ? ` ${t.modeSortBtnActive}` : ''}`}
                type="button"
                aria-pressed={sort.key === 'posts'}
                onClick={() => onToolbarSort('posts')}
              >
                Coverage
              </button>
            </div>
          )}
          {loading || !onTypeFilter ? null : (
            <div className={t.sortGroup} role="group" aria-label="Filter by peer type">
              <button
                className={`${t.modeSortBtn}${typeFilter === '' ? ` ${t.modeSortBtnActive}` : ''}`}
                type="button"
                aria-pressed={typeFilter === ''}
                onClick={() => onTypeFilter('')}
              >
                All
              </button>
              {PEER_TYPES.map((type) => (
                <button
                  key={type}
                  className={`${t.modeSortBtn}${typeFilter === type ? ` ${t.modeSortBtnActive}` : ''}`}
                  type="button"
                  aria-pressed={typeFilter === type}
                  onClick={() => onTypeFilter(type)}
                >
                  {peerTypeLabel(type)}
                </button>
              ))}
            </div>
          )}
        </div>
        {pager}
      </div>
      {loading ? null : peers.length === 0 ? (
        <p className={t.empty} role="status">
          {emptyMessage ?? 'No peers match that search.'}
        </p>
      ) : (
        <>
          <div className={`${t.head} ${t.row}`} role="row">
            <SortHeader label="Peer" sortKey="peer" sort={sort} onSort={onSort} />
            <SortHeader label="Added" sortKey="added" sort={sort} onSort={onSort} />
            <SortHeader label="Subscribers" sortKey="subscribers" sort={sort} onSort={onSort} />
          </div>
          <div className={t.body} role="rowgroup">
            {pageRows.map((peer) => (
              <CatalogPeerRow key={peer.external_id} peer={peer} onClick={onPeerClick} />
            ))}
          </div>
          <div className={t.footer}>{pager}</div>
        </>
      )}
    </div>
  )
}

function CatalogPeerRow({ peer, onClick }: { peer: Peer; onClick?: (peer: Peer) => void }) {
  const label = peerLabel(peer)
  const handle = peer.username ? `@${peer.username}` : null
  const subscribers = peer.participants_count
  const exclusions: string[] = []
  const maxLabel = formatMaxMediaBytes(peer.max_media_bytes)
  if (peer.large_excluded) {
    exclusions.push(maxLabel ? `Files over ${maxLabel} excluded` : 'Large files excluded')
  }

  return (
    <div
      className={`${t.row} ${t.bodyRow}${onClick ? ` ${t.bodyRowClick}` : ''}`}
      role="row"
      tabIndex={onClick ? 0 : undefined}
      aria-label={onClick ? `Coverage for ${label}` : undefined}
      onClick={onClick ? () => onClick(peer) : undefined}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onClick(peer)
              }
            }
          : undefined
      }
    >
      <div className={`${t.cell} ${t.peerCell}`} role="cell" title={String(peer.external_id)}>
        <PeerAvatar peer={peer} />
        <span className={t.peerStack}>
          <span className={t.peerTitleRow}>
            <span className={t.peerTitle}>{label}</span>
            {peer.is_scraping ? (
              <span className={`spinner ${t.scrapeSpinner}`} aria-label="Scraping" />
            ) : null}
          </span>
          <span className={t.peerHandle}>
            {peerTypeLabel(peer.peer_type)}
            {handle ? ` · ${handle}` : ''}
            {peer.is_scraping && peer.scrape_detail ? ` · ${peer.scrape_detail}` : ''}
          </span>
        </span>
      </div>
      <span className={`${t.cell} ${t.dateCell}`} role="cell" title={peer.created_at}>
        {formatAddedAt(peer.created_at)}
      </span>
      <span className={`${t.cell} ${t.subsCell}`} role="cell">
        {subscribers == null ? dash() : formatCount(subscribers)}
      </span>
      <div className={`${t.cell} ${t.statsCell}`} role="cell">
        <div className={t.stats}>
          <span className={t.stat}>
            <span className={t.statLabel}>Posts</span>
            {peer.posts == null ? dash() : <span className={t.statValue}>{formatCount(peer.posts)}</span>}
          </span>
          <span className={t.stat}>
            <span className={t.statLabel}>Forwards</span>
            {peer.forwards_total == null ? dash() : (
              <span className={t.statValue} title="Forwarded messages stored for this peer">
                {formatCount(peer.forwards_total)}
              </span>
            )}
          </span>
          {MEDIA_ITEMS.map((item) => (
            <MediaValue key={item.key} bucket={peer.media?.[item.key]} label={item.label} icon={item.icon} />
          ))}
          <EmbedValue bucket={peer.embed_images} label="Embed images" />
          <EmbedValue bucket={peer.embed_text} label="Embed text" />
        </div>
        {exclusions.length > 0 ? (
          <div className={t.exclusions}>
            {exclusions.map((item) => (
              <span className={t.exclusion} key={item}>
                {item}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

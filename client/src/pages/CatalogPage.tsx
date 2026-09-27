import { useEffect, useMemo, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Navigate, useParams } from 'react-router'
import { AccountAvatar } from '../components/AccountAvatar'
import {
  ExportButton,
  GeneralCatalogExport,
  ImagesCatalogExport,
  MessagesCatalogExport,
  VideosCatalogExport,
  FilesCatalogExport,
} from '../components/CatalogExportModal'
import { CatalogImageTable, type ImageSort } from '../components/CatalogImageTable'
import { CatalogMessageTable, PeerFilterChip } from '../components/CatalogMessageTable'
import { CatalogPeerTable } from '../components/CatalogPeerTable'
import { CatalogPeerModal } from '../components/CatalogPeerModal'
import { CatalogSearchBar } from '../components/CatalogSearchBar'
import { CatalogVideoTable } from '../components/CatalogVideoTable'
import { CatalogFileTable } from '../components/CatalogFileTable'
import { LoadingText } from '../components/LoadingText'
import { PeerAvatar } from '../components/PeerAvatar'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { syncingChatsLabel } from '../lib/account'
import { api, type CatalogFile, type CatalogImage, type CatalogMessage, type CatalogVideo, type Peer } from '../lib/api'
import { peerMatchesQuery, peerTypeLabel } from '../lib/peer'
import { useAppStatus } from '../layout/statusContext'
import c from './CatalogPage.module.css'

const MESSAGE_PAGE_SIZE = 50
const IMAGE_PAGE_SIZE = 50
const VIDEO_PAGE_SIZE = 50
const FILE_PAGE_SIZE = 50

export default function CatalogPage() {
  const { kind = 'peers' } = useParams()
  if (kind === 'messages') return <CatalogMessagesPage />
  if (kind === 'images') return <CatalogImagesPage />
  if (kind === 'videos') return <CatalogVideosPage />
  if (kind === 'files') return <CatalogFilesPage />
  if (kind !== 'peers') return <Navigate to="/catalog/peers" replace />
  return <CatalogPeersPage />
}

function CatalogPeersPage() {
  const { peers, error, running, loaded, ready, refresh } = useDialogueSync()
  const account = useAppStatus()?.account ?? null
  const firstName = account?.first_name?.trim().split(/\s+/)[0] || null
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [exportOpen, setExportOpen] = useState(false)
  const [selected, setSelected] = useState<Peer | null>(null)
  const loadingList = !ready && peers.length === 0

  const visible = useMemo(
    () =>
      peers.filter(
        (peer) => (!typeFilter || peer.peer_type === typeFilter) && peerMatchesQuery(peer, query),
      ),
    [peers, query, typeFilter],
  )

  return (
    <div>
      <div className={c.toolbar}>
        <div className={c.search}>
          <CatalogSearchBar
            query={draft}
            onQueryChange={(value) => {
              setDraft(value)
              setQuery(value)
            }}
            onSearch={setQuery}
            isLoading={loadingList}
            flush
          />
        </div>
        <button
          type="button"
          className={c.sync}
          disabled={running}
          aria-label={firstName ? `Sync ${firstName}` : 'Sync chats'}
          onClick={() => void refresh()}
        >
          {running ? <span className="spinner" aria-hidden /> : (
            <RefreshCw size={14} strokeWidth={2} aria-hidden />
          )}
          Sync
          {account ? (
            <AccountAvatar
              photoUrl={account.photo_url}
              mediaKind={account.photo_media_kind}
              name={firstName ?? ''}
              size="sm"
            />
          ) : null}
          {firstName}
        </button>
        <ExportButton disabled={loadingList || peers.length === 0} onClick={() => setExportOpen(true)} />
      </div>
      {running ? (
        <p>
          <LoadingText>{syncingChatsLabel(account, loaded)}</LoadingText>
        </p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <CatalogPeerTable
        peers={visible}
        totalCount={visible.length}
        query={query}
        filterKey={typeFilter}
        typeFilter={typeFilter}
        onTypeFilter={setTypeFilter}
        onPeerClick={setSelected}
        loading={loadingList}
        emptyMessage={
          peers.length === 0
            ? 'No peers in this account yet.'
            : 'No peers match that filter.'
        }
      />
      {exportOpen ? (
        <GeneralCatalogExport
          peers={peers}
          typeFilter={typeFilter}
          onClose={() => setExportOpen(false)}
        />
      ) : null}
      {selected ? (
        <CatalogPeerModal
          peer={visible.find((item) => item.external_id === selected.external_id) ?? selected}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </div>
  )
}

function peerLabel(peer: Peer): string {
  return (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id))
}

function CatalogMessagesPage() {
  const { peers } = useDialogueSync()
  const textReady = useAppStatus()?.models.text.ready ?? false
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState<Peer | null>(null)
  const [page, setPage] = useState(1)
  const [mode, setMode] = useState<'peer' | 'meaning'>('peer')
  const [meaningQuery, setMeaningQuery] = useState('')
  const [rows, setRows] = useState<CatalogMessage[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)

  const matches = useMemo(() => {
    if (filter || mode === 'meaning' || !draft.trim()) return []
    return peers.filter((peer) => peerMatchesQuery(peer, draft)).slice(0, 8)
  }, [peers, draft, filter, mode])

  const pickPeer = (peer: Peer) => {
    setFilter(peer)
    setDraft('')
    setPage(1)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setRows([])
    const request =
      mode === 'meaning' && meaningQuery.trim()
        ? api.searchMessages({
            q: meaningQuery.trim(),
            peer_external_id: filter?.external_id,
            limit: MESSAGE_PAGE_SIZE,
          })
        : api.messages({
            peer_external_id: filter?.external_id,
            limit: MESSAGE_PAGE_SIZE,
            offset: (page - 1) * MESSAGE_PAGE_SIZE,
          })
    void request
      .then((res) => {
        if (cancelled) return
        setRows(res.messages)
        setTotal(res.total)
        setError(null)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filter?.external_id, page, mode, meaningQuery])

  return (
    <div>
      <div className={c.toolbar}>
        <div className={c.modeGroup} role="group" aria-label="Message search mode">
          <button
            type="button"
            className={`${c.modeBtn}${mode === 'meaning' ? ` ${c.modeBtnActive}` : ''}`}
            disabled={!textReady}
            title={textReady ? undefined : 'Download the text model on Home to search by meaning'}
            onClick={() => {
              setMode('meaning')
              setPage(1)
            }}
          >
            Meaning
          </button>
          <button
            type="button"
            className={`${c.modeBtn}${mode === 'peer' ? ` ${c.modeBtnActive}` : ''}`}
            onClick={() => {
              setMode('peer')
              setMeaningQuery('')
              setPage(1)
            }}
          >
            Peer
          </button>
        </div>
        <div className={c.search}>
          <CatalogSearchBar
            query={draft}
            onQueryChange={setDraft}
            onSearch={(value) => {
              if (mode === 'meaning') {
                setMeaningQuery(value)
                setPage(1)
                return
              }
              const hit = peers.find((peer) => peerMatchesQuery(peer, value))
              if (hit) pickPeer(hit)
            }}
            placeholder={
              mode === 'meaning'
                ? 'Search messages by meaning'
                : 'Filter by peer name, @username, or id'
            }
            ariaLabel={mode === 'meaning' ? 'Search messages by meaning' : 'Filter messages by peer'}
            flush
            isLoading={loading}
            results={
              matches.length > 0 ? (
                <>
                  {matches.map((peer) => (
                    <button
                      key={peer.external_id}
                      className={c.hit}
                      type="button"
                      role="option"
                      onClick={() => pickPeer(peer)}
                    >
                      <PeerAvatar peer={peer} />
                      <span className={c.hitBody}>
                        <span className={c.hitTitle}>{peerLabel(peer)}</span>
                        <span className={c.hitMeta}>
                          {peerTypeLabel(peer.peer_type)}
                          {peer.username ? ` · @${peer.username}` : ''}
                        </span>
                      </span>
                    </button>
                  ))}
                </>
              ) : null
            }
          />
        </div>
        {filter ? (
          <PeerFilterChip
            peer={filter}
            onClear={() => {
              setFilter(null)
              setPage(1)
            }}
          />
        ) : null}
        <ExportButton disabled={loading || (!filter && total === 0)} onClick={() => setExportOpen(true)} />
      </div>
      {error ? <p className="error">{error}</p> : null}
      <CatalogMessageTable
        messages={rows}
        total={total}
        page={page}
        pageSize={MESSAGE_PAGE_SIZE}
        loading={loading}
        onPage={setPage}
        emptyMessage={
          mode === 'meaning' && meaningQuery.trim()
            ? 'No embedded messages matched that query. Embed remainder from a peer, or snowball with Embed text on.'
            : filter
              ? 'No messages stored for this peer.'
              : 'No messages stored yet.'
        }
      />
      {exportOpen ? (
        <MessagesCatalogExport peer={filter} onClose={() => setExportOpen(false)} />
      ) : null}
    </div>
  )
}

function CatalogImagesPage() {
  const { peers } = useDialogueSync()
  const vision = useAppStatus()?.models.image
  const meaningOk = Boolean(vision?.ready && vision.multimodal)
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState<Peer | null>(null)
  const [page, setPage] = useState(1)
  const [mode, setMode] = useState<'peer' | 'meaning'>('peer')
  const [meaningQuery, setMeaningQuery] = useState('')
  const [sort, setSort] = useState<ImageSort>('peers')
  const [rows, setRows] = useState<CatalogImage[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)

  const matches = useMemo(() => {
    if (filter || mode === 'meaning' || !draft.trim()) return []
    return peers.filter((peer) => peerMatchesQuery(peer, draft)).slice(0, 8)
  }, [peers, draft, filter, mode])

  const pickPeer = (peer: Peer) => {
    setFilter(peer)
    setDraft('')
    setPage(1)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setRows([])
    const request =
      mode === 'meaning' && meaningQuery.trim()
        ? api.searchImages({
            q: meaningQuery.trim(),
            peer_external_id: filter?.external_id,
            limit: IMAGE_PAGE_SIZE,
          })
        : api.images({
            peer_external_id: filter?.external_id,
            sort,
            limit: IMAGE_PAGE_SIZE,
            offset: (page - 1) * IMAGE_PAGE_SIZE,
          })
    void request
      .then((res) => {
        if (cancelled) return
        setRows(res.images)
        setTotal(res.total)
        setError(null)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filter?.external_id, page, sort, mode, meaningQuery])

  return (
    <div>
      <div className={c.toolbar}>
        <div className={c.modeGroup} role="group" aria-label="Image search mode">
          <button
            type="button"
            className={`${c.modeBtn}${mode === 'meaning' ? ` ${c.modeBtnActive}` : ''}`}
            disabled={!meaningOk}
            title={
              meaningOk
                ? undefined
                : 'Text-to-image search needs a ready CLIP or SigLIP model'
            }
            onClick={() => {
              setMode('meaning')
              setPage(1)
            }}
          >
            Meaning
          </button>
          <button
            type="button"
            className={`${c.modeBtn}${mode === 'peer' ? ` ${c.modeBtnActive}` : ''}`}
            onClick={() => {
              setMode('peer')
              setMeaningQuery('')
              setPage(1)
            }}
          >
            Peer
          </button>
        </div>
        <div className={c.search}>
          <CatalogSearchBar
            query={draft}
            onQueryChange={setDraft}
            onSearch={(value) => {
              if (mode === 'meaning') {
                setMeaningQuery(value)
                setPage(1)
                return
              }
              const hit = peers.find((peer) => peerMatchesQuery(peer, value))
              if (hit) pickPeer(hit)
            }}
            placeholder={
              mode === 'meaning'
                ? 'Search downloaded images by text'
                : 'Filter by peer name, @username, or id'
            }
            ariaLabel={mode === 'meaning' ? 'Search images by meaning' : 'Filter images by peer'}
            flush
            isLoading={loading}
            results={
              matches.length > 0 ? (
                <>
                  {matches.map((peer) => (
                    <button
                      key={peer.external_id}
                      className={c.hit}
                      type="button"
                      role="option"
                      onClick={() => pickPeer(peer)}
                    >
                      <PeerAvatar peer={peer} />
                      <span className={c.hitBody}>
                        <span className={c.hitTitle}>{peerLabel(peer)}</span>
                        <span className={c.hitMeta}>
                          {peerTypeLabel(peer.peer_type)}
                          {peer.username ? ` · @${peer.username}` : ''}
                        </span>
                      </span>
                    </button>
                  ))}
                </>
              ) : null
            }
          />
        </div>
        {filter ? (
          <PeerFilterChip
            peer={filter}
            onClear={() => {
              setFilter(null)
              setPage(1)
            }}
          />
        ) : null}
        <ExportButton disabled={loading || (!filter && total === 0)} onClick={() => setExportOpen(true)} />
      </div>
      {error ? <p className="error">{error}</p> : null}
      <CatalogImageTable
        images={rows}
        total={total}
        page={page}
        pageSize={IMAGE_PAGE_SIZE}
        sort={sort}
        loading={loading}
        onPage={setPage}
        onSort={(next) => {
          setSort(next)
          setPage(1)
        }}
        emptyMessage={
          mode === 'meaning' && meaningQuery.trim()
            ? 'No embedded images matched that query. Images need to be on disk and embedded (CLIP/SigLIP).'
            : filter
              ? 'No hashed images stored for this peer.'
              : 'No hashed images yet. Run a snowball to collect image hashes.'
        }
      />
      {exportOpen ? (
        <ImagesCatalogExport peer={filter} onClose={() => setExportOpen(false)} />
      ) : null}
    </div>
  )
}

function CatalogVideosPage() {
  const { peers } = useDialogueSync()
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState<Peer | null>(null)
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<CatalogVideo[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)

  const matches = useMemo(() => {
    if (filter || !draft.trim()) return []
    return peers.filter((peer) => peerMatchesQuery(peer, draft)).slice(0, 8)
  }, [peers, draft, filter])

  const pickPeer = (peer: Peer) => {
    setFilter(peer)
    setDraft('')
    setPage(1)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setRows([])
    void api
      .videos({
        peer_external_id: filter?.external_id,
        limit: VIDEO_PAGE_SIZE,
        offset: (page - 1) * VIDEO_PAGE_SIZE,
      })
      .then((res) => {
        if (cancelled) return
        setRows(res.videos)
        setTotal(res.total)
        setError(null)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filter?.external_id, page])

  return (
    <div>
      <div className={c.toolbar}>
        <div className={c.search}>
          <CatalogSearchBar
            query={draft}
            onQueryChange={setDraft}
            onSearch={(value) => {
              const hit = peers.find((peer) => peerMatchesQuery(peer, value))
              if (hit) pickPeer(hit)
            }}
            placeholder="Filter by peer name, @username, or id"
            ariaLabel="Filter videos by peer"
            flush
            results={
              matches.length > 0 ? (
                <>
                  {matches.map((peer) => (
                    <button
                      key={peer.external_id}
                      className={c.hit}
                      type="button"
                      role="option"
                      onClick={() => pickPeer(peer)}
                    >
                      <PeerAvatar peer={peer} />
                      <span className={c.hitBody}>
                        <span className={c.hitTitle}>{peerLabel(peer)}</span>
                        <span className={c.hitMeta}>
                          {peerTypeLabel(peer.peer_type)}
                          {peer.username ? ` · @${peer.username}` : ''}
                        </span>
                      </span>
                    </button>
                  ))}
                </>
              ) : null
            }
          />
        </div>
        {filter ? (
          <PeerFilterChip
            peer={filter}
            onClear={() => {
              setFilter(null)
              setPage(1)
            }}
          />
        ) : null}
        <ExportButton disabled={loading || (!filter && total === 0)} onClick={() => setExportOpen(true)} />
      </div>
      {error ? <p className="error">{error}</p> : null}
      <CatalogVideoTable
        videos={rows}
        total={total}
        page={page}
        pageSize={VIDEO_PAGE_SIZE}
        loading={loading}
        onPage={setPage}
        emptyMessage={
          filter
            ? 'No videos stored for this peer.'
            : 'No videos stored yet. Run a snowball to collect video metadata.'
        }
      />
      {exportOpen ? (
        <VideosCatalogExport peer={filter} onClose={() => setExportOpen(false)} />
      ) : null}
    </div>
  )
}

function CatalogFilesPage() {
  const { peers } = useDialogueSync()
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState<Peer | null>(null)
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<CatalogFile[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)

  const matches = useMemo(() => {
    if (filter || !draft.trim()) return []
    return peers.filter((peer) => peerMatchesQuery(peer, draft)).slice(0, 8)
  }, [peers, draft, filter])

  const pickPeer = (peer: Peer) => {
    setFilter(peer)
    setDraft('')
    setPage(1)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setRows([])
    void api
      .files({
        peer_external_id: filter?.external_id,
        limit: FILE_PAGE_SIZE,
        offset: (page - 1) * FILE_PAGE_SIZE,
      })
      .then((res) => {
        if (cancelled) return
        setRows(res.files)
        setTotal(res.total)
        setError(null)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filter?.external_id, page])

  return (
    <div>
      <div className={c.toolbar}>
        <div className={c.search}>
          <CatalogSearchBar
            query={draft}
            onQueryChange={setDraft}
            onSearch={(value) => {
              const hit = peers.find((peer) => peerMatchesQuery(peer, value))
              if (hit) pickPeer(hit)
            }}
            placeholder="Filter by peer name, @username, or id"
            ariaLabel="Filter files by peer"
            flush
            results={
              matches.length > 0 ? (
                <>
                  {matches.map((peer) => (
                    <button
                      key={peer.external_id}
                      className={c.hit}
                      type="button"
                      role="option"
                      onClick={() => pickPeer(peer)}
                    >
                      <PeerAvatar peer={peer} />
                      <span className={c.hitBody}>
                        <span className={c.hitTitle}>{peerLabel(peer)}</span>
                        <span className={c.hitMeta}>
                          {peerTypeLabel(peer.peer_type)}
                          {peer.username ? ` · @${peer.username}` : ''}
                        </span>
                      </span>
                    </button>
                  ))}
                </>
              ) : null
            }
          />
        </div>
        {filter ? (
          <PeerFilterChip
            peer={filter}
            onClear={() => {
              setFilter(null)
              setPage(1)
            }}
          />
        ) : null}
        <ExportButton disabled={loading || (!filter && total === 0)} onClick={() => setExportOpen(true)} />
      </div>
      {error ? <p className="error">{error}</p> : null}
      <CatalogFileTable
        files={rows}
        total={total}
        page={page}
        pageSize={FILE_PAGE_SIZE}
        loading={loading}
        onPage={setPage}
        emptyMessage={
          filter
            ? 'No other files stored for this peer.'
            : 'No other files stored yet. Image and video documents appear in those catalogs instead.'
        }
      />
      {exportOpen ? (
        <FilesCatalogExport peer={filter} onClose={() => setExportOpen(false)} />
      ) : null}
    </div>
  )
}

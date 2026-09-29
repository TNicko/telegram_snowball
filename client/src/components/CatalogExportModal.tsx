import { useMemo, useState, type ReactNode } from 'react'
import { Download, FileBraces, FileSpreadsheet } from 'lucide-react'
import type { DateRange } from 'react-day-picker'
import { CatalogSearchBar } from './CatalogSearchBar'
import { DateRangeField } from './DateRangeField'
import { PeerFilterChip } from './CatalogMessageTable'
import { PeerAvatar } from './PeerAvatar'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { downloadExport, type Peer } from '../lib/api'
import { PEER_TYPES, peerMatchesQuery, peerTypeLabel, type PeerType } from '../lib/peer'
import c from '../pages/CatalogPage.module.css'
import s from './CatalogExportModal.module.css'

export type ExportFormat = 'csv' | 'json'

function peerLabel(peer: Peer): string {
  return (peer.title ?? '').trim() || (peer.username ? `@${peer.username}` : String(peer.external_id))
}

function startOfDayIso(date: Date): string {
  const next = new Date(date)
  next.setHours(0, 0, 0, 0)
  return next.toISOString()
}

function endOfDayIso(date: Date): string {
  const next = new Date(date)
  next.setHours(23, 59, 59, 999)
  return next.toISOString()
}

export function ExportButton({ disabled, onClick }: { disabled?: boolean; onClick: () => void }) {
  return (
    <button type="button" className={s.exportBtn} disabled={disabled} onClick={onClick}>
      <Download size={14} strokeWidth={2} aria-hidden />
      Export
    </button>
  )
}

function FormatToggle({
  value,
  onChange,
}: {
  value: ExportFormat
  onChange: (format: ExportFormat) => void
}) {
  return (
    <div className={s.formatGroup} role="group" aria-label="Export format">
      <button
        type="button"
        className={`${s.formatBtn}${value === 'csv' ? ` ${s.formatBtnActive}` : ''}`}
        aria-pressed={value === 'csv'}
        onClick={() => onChange('csv')}
      >
        <FileSpreadsheet size={12} strokeWidth={2} aria-hidden />
        CSV
      </button>
      <button
        type="button"
        className={`${s.formatBtn}${value === 'json' ? ` ${s.formatBtnActive}` : ''}`}
        aria-pressed={value === 'json'}
        onClick={() => onChange('json')}
      >
        <FileBraces size={12} strokeWidth={2} aria-hidden />
        JSON
      </button>
    </div>
  )
}

function ExportModalShell({
  title,
  format,
  onFormatChange,
  summary,
  children,
  busy,
  error,
  disabled,
  onExport,
  onClose,
}: {
  title: string
  format: ExportFormat
  onFormatChange: (format: ExportFormat) => void
  summary: ReactNode
  children?: ReactNode
  busy: boolean
  error: string | null
  disabled?: boolean
  onExport: () => void
  onClose: () => void
}) {
  return (
    <div className="modalScrim" onClick={onClose}>
      <div className={`modal ${s.modal}`} onClick={(event) => event.stopPropagation()}>
        <h3 className={s.title}>{title}</h3>
        <div className={s.row}>
          <span className={s.label}>Format</span>
          <FormatToggle value={format} onChange={onFormatChange} />
        </div>
        {children}
        <p className={s.summary}>{summary}</p>
        {error ? <p className="error">{error}</p> : null}
        <div className={s.actions}>
          <button
            type="button"
            className={`btn btnPrimary${busy ? ' btnLoading' : ''}`}
            disabled={busy || disabled}
            onClick={onExport}
          >
            {busy ? (
              <span className="btnBusy">
                <span className="spinner" aria-hidden />
                Exporting
              </span>
            ) : (
              'Export'
            )}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

function PeerPick({
  peer,
  onChange,
}: {
  peer: Peer | null
  onChange: (peer: Peer | null) => void
}) {
  const { peers } = useDialogueSync()
  const [draft, setDraft] = useState('')
  const matches = useMemo(() => {
    if (peer || !draft.trim()) return []
    return peers.filter((item) => peerMatchesQuery(item, draft)).slice(0, 8)
  }, [peers, draft, peer])

  return (
    <div className={s.peerPick}>
      <span className={s.label}>Peer</span>
      {peer ? (
        <PeerFilterChip peer={peer} onClear={() => onChange(null)} />
      ) : (
        <CatalogSearchBar
          query={draft}
          onQueryChange={setDraft}
          onSearch={(value) => {
            const hit = peers.find((item) => peerMatchesQuery(item, value))
            if (hit) {
              onChange(hit)
              setDraft('')
            }
          }}
          placeholder="All peers, or search to limit to one"
          ariaLabel="Filter export by peer"
          flush
          results={
            matches.length > 0 ? (
              <>
                {matches.map((item) => (
                  <button
                    key={item.external_id}
                    className={c.hit}
                    type="button"
                    role="option"
                    onClick={() => {
                      onChange(item)
                      setDraft('')
                    }}
                  >
                    <PeerAvatar peer={item} />
                    <span className={c.hitBody}>
                      <span className={c.hitTitle}>{peerLabel(item)}</span>
                      <span className={c.hitMeta}>
                        {peerTypeLabel(item.peer_type)}
                        {item.username ? ` · @${item.username}` : ''}
                      </span>
                    </span>
                  </button>
                ))}
              </>
            ) : null
          }
        />
      )}
    </div>
  )
}

async function runExport(
  path: string,
  body: Record<string, unknown>,
  setBusy: (busy: boolean) => void,
  setError: (error: string | null) => void,
  onClose: () => void,
) {
  setBusy(true)
  setError(null)
  try {
    await downloadExport(path, body)
    onClose()
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Export failed')
  } finally {
    setBusy(false)
  }
}

export function GeneralCatalogExport({
  peers,
  typeFilter,
  onClose,
}: {
  peers: Peer[]
  typeFilter: string
  onClose: () => void
}) {
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [types, setTypes] = useState<PeerType[]>(() =>
    typeFilter && PEER_TYPES.includes(typeFilter as PeerType)
      ? [typeFilter as PeerType]
      : [...PEER_TYPES],
  )
  const [includeEdges, setIncludeEdges] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const counts = useMemo(() => {
    const tally: Record<string, number> = {}
    for (const type of PEER_TYPES) tally[type] = 0
    for (const peer of peers) {
      if (peer.peer_type in tally) tally[peer.peer_type] += 1
    }
    return tally
  }, [peers])

  const selectedCount = types.reduce((sum, type) => sum + (counts[type] ?? 0), 0)
  const toggle = (type: PeerType) => {
    setTypes((current) =>
      current.includes(type) ? current.filter((item) => item !== type) : [...current, type],
    )
  }

  return (
    <ExportModalShell
      title="Export general catalog"
      format={format}
      onFormatChange={setFormat}
      summary={
        format === 'csv'
          ? `${selectedCount.toLocaleString()} peers as a zip of per-type CSVs${includeEdges ? ', plus forward edges' : ''}.`
          : `${selectedCount.toLocaleString()} peers grouped by type in one JSON file.`
      }
      busy={busy}
      error={error}
      disabled={types.length === 0}
      onClose={onClose}
      onExport={() =>
        void runExport(
          '/api/export/peers',
          {
            format,
            peer_types: types,
            include_forward_edges: includeEdges,
          },
          setBusy,
          setError,
          onClose,
        )
      }
    >
      <div className={s.block}>
        <span className={s.label}>Peer types</span>
        <div className={s.typeList}>
          {PEER_TYPES.map((type) => (
            <label key={type} className={s.check}>
              <input
                type="checkbox"
                checked={types.includes(type)}
                onChange={() => toggle(type)}
              />
              {peerTypeLabel(type)}
              <span className={s.typeCount}>{(counts[type] ?? 0).toLocaleString()}</span>
            </label>
          ))}
        </div>
      </div>
      <label className={s.check}>
        <input
          type="checkbox"
          checked={includeEdges}
          onChange={(event) => setIncludeEdges(event.target.checked)}
        />
        Include forward edges
      </label>
    </ExportModalShell>
  )
}

export function MessagesCatalogExport({
  peer,
  onClose,
}: {
  peer: Peer | null
  onClose: () => void
}) {
  const [format, setFormat] = useState<ExportFormat>('json')
  const [selected, setSelected] = useState<Peer | null>(peer)
  const [range, setRange] = useState<DateRange | undefined>()
  const [textOnly, setTextOnly] = useState(false)
  const [mediaOnly, setMediaOnly] = useState(false)
  const [includeForwards, setIncludeForwards] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  return (
    <ExportModalShell
      title="Export messages"
      format={format}
      onFormatChange={setFormat}
      summary={
        format === 'json'
          ? `JSON grouped by peer${selected ? ` (${peerLabel(selected)})` : ''}.`
          : `One CSV row per message${selected ? ` for ${peerLabel(selected)}` : ''}.`
      }
      busy={busy}
      error={error}
      onClose={onClose}
      onExport={() =>
        void runExport(
          '/api/export/messages',
          {
            format,
            peer_external_id: selected?.external_id ?? null,
            date_from: range?.from ? startOfDayIso(range.from) : null,
            date_to: range?.to ? endOfDayIso(range.to) : range?.from ? endOfDayIso(range.from) : null,
            text_only: textOnly,
            media_only: mediaOnly,
            include_forwards: includeForwards,
          },
          setBusy,
          setError,
          onClose,
        )
      }
    >
      <PeerPick peer={selected} onChange={setSelected} />
      <div className={s.block}>
        <span className={s.label}>Date range</span>
        <DateRangeField value={range} onChange={setRange} popoverZIndex={90} />
      </div>
      <label className={s.check}>
        <input type="checkbox" checked={textOnly} onChange={(event) => setTextOnly(event.target.checked)} />
        Only messages with text
      </label>
      <label className={s.check}>
        <input type="checkbox" checked={mediaOnly} onChange={(event) => setMediaOnly(event.target.checked)} />
        Only messages with media
      </label>
      <label className={s.check}>
        <input
          type="checkbox"
          checked={includeForwards}
          onChange={(event) => setIncludeForwards(event.target.checked)}
        />
        Include forward metadata
      </label>
    </ExportModalShell>
  )
}

export function ImagesCatalogExport({
  peer,
  onClose,
}: {
  peer: Peer | null
  onClose: () => void
}) {
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [selected, setSelected] = useState<Peer | null>(peer)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  return (
    <ExportModalShell
      title="Export images"
      format={format}
      onFormatChange={setFormat}
      summary={
        format === 'csv'
          ? 'Zip of images.csv plus image_peers.csv.'
          : 'JSON nested by pHash, with per-image peer lists.'
      }
      busy={busy}
      error={error}
      onClose={onClose}
      onExport={() =>
        void runExport(
          '/api/export/images',
          { format, peer_external_id: selected?.external_id ?? null },
          setBusy,
          setError,
          onClose,
        )
      }
    >
      <PeerPick peer={selected} onChange={setSelected} />
    </ExportModalShell>
  )
}

export function VideosCatalogExport({
  peer,
  onClose,
}: {
  peer: Peer | null
  onClose: () => void
}) {
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [selected, setSelected] = useState<Peer | null>(peer)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  return (
    <ExportModalShell
      title="Export videos"
      format={format}
      onFormatChange={setFormat}
      summary={
        format === 'csv'
          ? 'Zip of videos.csv plus video_peers.csv (Telegram media metadata).'
          : 'JSON nested by video, with per-video peer lists.'
      }
      busy={busy}
      error={error}
      onClose={onClose}
      onExport={() =>
        void runExport(
          '/api/export/videos',
          { format, peer_external_id: selected?.external_id ?? null },
          setBusy,
          setError,
          onClose,
        )
      }
    >
      <PeerPick peer={selected} onChange={setSelected} />
    </ExportModalShell>
  )
}

export function FilesCatalogExport({
  peer,
  onClose,
}: {
  peer: Peer | null
  onClose: () => void
}) {
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [selected, setSelected] = useState<Peer | null>(peer)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  return (
    <ExportModalShell
      title="Export files"
      format={format}
      onFormatChange={setFormat}
      summary={
        format === 'csv'
          ? 'Zip of files.csv plus file_peers.csv (Telegram file metadata).'
          : 'JSON nested by file, with per-file peer lists.'
      }
      busy={busy}
      error={error}
      onClose={onClose}
      onExport={() =>
        void runExport(
          '/api/export/files',
          { format, peer_external_id: selected?.external_id ?? null },
          setBusy,
          setError,
          onClose,
        )
      }
    >
      <PeerPick peer={selected} onChange={setSelected} />
    </ExportModalShell>
  )
}

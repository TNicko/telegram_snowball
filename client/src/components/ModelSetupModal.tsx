import { useState } from 'react'
import { Star } from 'lucide-react'
import { LoadingText } from './LoadingText'
import type { ModelCatalog, ModelHealth, ModelSlot } from '../lib/api'
import h from '../pages/HomePage.module.css'

type Props = {
  slot: ModelSlot
  catalog: ModelCatalog
  busy?: boolean
  error?: string | null
  onClose: () => void
  onSelect: (modelId: string) => void
  onDownload: (modelId: string) => void
}

function downloadLabel(item: ModelHealth): string {
  if (!item.download_gb) return 'No download'
  if (item.download_gb < 0.1) return `${Math.round(item.download_gb * 1000)} MB`
  return `${item.download_gb} GB`
}

function optionGroups(options: ModelHealth[]) {
  const groups: { key: string; label: string | null; items: ModelHealth[] }[] = []
  for (const item of options) {
    const key = item.group ?? 'default'
    const last = groups.at(-1)
    if (!last || last.key !== key) {
      groups.push({ key, label: item.group_label ?? null, items: [item] })
    } else {
      last.items.push(item)
    }
  }
  return groups
}

export function ModelSetupModal({
  slot,
  catalog,
  busy,
  error,
  onClose,
  onSelect,
  onDownload,
}: Props) {
  const options = catalog.catalog[slot] ?? []
  const selected = catalog.slots[slot]
  const [picked, setPicked] = useState(selected?.id ?? options[0]?.id ?? '')
  const copy = catalog.copy[slot]
  const current = options.find((item) => item.id === picked) ?? selected
  const download = catalog.download
  const downloadingId =
    download && typeof download.params?.model_id === 'string' ? download.params.model_id : null
  const downloadDetail =
    download && typeof download.progress?.detail === 'string' ? download.progress.detail : null

  return (
    <div className="modalScrim" onClick={onClose}>
      <div
        className={`modal ${h.modelModal}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-setup-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h3 id="model-setup-title" className={h.modalTitle}>
          {copy?.title ?? selected?.title ?? 'Model'}
        </h3>
        <p className={h.modelBlurb}>{copy?.blurb}</p>
        <div className={h.modelChoices} role="radiogroup" aria-label="Model options">
          {optionGroups(options).map((group) => (
            <div key={group.key} className={h.modelGroup}>
              {group.label ? <p className={h.modelGroupLabel}>{group.label}</p> : null}
              {group.items.map((item) => (
                <label
                  key={item.id}
                  className={`${h.modelChoice}${item.id === picked ? ` ${h.modelChoiceOn}` : ''}`}
                >
                  <input
                    type="radio"
                    name={`model-${slot}`}
                    checked={item.id === picked}
                    onChange={() => setPicked(item.id)}
                  />
                  <span className={h.modelChoiceBody}>
                    <span className={h.modelChoiceHead}>
                      <span className={h.modelChoiceLabel}>{item.label}</span>
                      {item.recommended ? (
                        <span className={h.modelBadgeRecommended}>
                          <Star size={10} strokeWidth={0} fill="currentColor" aria-hidden />
                          Recommended
                        </span>
                      ) : null}
                      {item.default && !item.recommended ? (
                        <span className={h.modelBadge}>Default</span>
                      ) : null}
                    </span>
                    {item.download_gb || item.hardware ? (
                      <span className={h.modelChoiceMeta}>
                        {downloadLabel(item)}
                        {item.hardware ? ` · ${item.hardware}` : ''}
                      </span>
                    ) : null}
                    {item.purpose ? <span className={h.modelChoicePurpose}>{item.purpose}</span> : null}
                  </span>
                </label>
              ))}
            </div>
          ))}
        </div>
        {downloadDetail ? (
          <p className={h.modelProgress}>
            <span className="spinner" aria-hidden />
            <LoadingText>{downloadDetail}</LoadingText>
          </p>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        <div className={h.modelActions}>
          <button type="button" className={h.modelGhost} onClick={onClose} disabled={busy}>
            Close
          </button>
          {current && current.id !== selected?.id && current.ready ? (
            <button
              type="button"
              className="btn btnPrimary"
              disabled={busy}
              onClick={() => onSelect(current.id)}
            >
              Use {current.label}
            </button>
          ) : null}
          {current && !current.ready && current.id !== 'none' ? (
            <button
              type="button"
              className="btn btnPrimary"
              disabled={busy || downloadingId != null}
              onClick={() => onDownload(current.id)}
            >
              {downloadingId === current.id ? 'Downloading…' : `Download ${current.label}`}
            </button>
          ) : null}
          {current?.id === 'none' && selected?.id !== 'none' ? (
            <button
              type="button"
              className="btn btnPrimary"
              disabled={busy}
              onClick={() => onSelect('none')}
            >
              Don’t use captions
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

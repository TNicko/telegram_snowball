import { useEffect, useState } from 'react'
import { ChevronRight, TriangleAlert } from 'lucide-react'
import type { DateRange } from 'react-day-picker'
import { DateRangeField } from './DateRangeField'
import { InfoTip } from './InfoTip'
import { PeerAvatar } from './PeerAvatar'
import type { Peer } from '../lib/api'
import { peerTypeLabel } from '../lib/peer'
import h from '../pages/HomePage.module.css'

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

export type SnowballConfigModalProps = {
  peer: Peer
  busy?: boolean
  imageReady: boolean
  textReady: boolean
  /** Home crawl always snowballs; graph scrape defaults to this peer only. */
  snowballChoice?: boolean
  /** Vision inputs on Home; after the seed, pick depth-1+ peers by forward score. */
  scopeAvailable?: boolean
  defaultSnowball?: boolean
  title: string
  startLabel: string
  onClose: () => void
  onStart: (params: Record<string, unknown>) => void
}

export function SnowballConfigModal({
  peer,
  busy,
  imageReady,
  textReady,
  scopeAvailable = false,
  snowballChoice = false,
  defaultSnowball = true,
  title,
  startLabel,
  onClose,
  onStart,
}: SnowballConfigModalProps) {
  const [embedImages, setEmbedImages] = useState(imageReady)
  const [embedText, setEmbedText] = useState(textReady)
  const [images, setImages] = useState(false)
  const [videos, setVideos] = useState(false)
  const [participants, setParticipants] = useState(false)
  const [dateRange, setDateRange] = useState<DateRange | undefined>()
  const [restrictRange, setRestrictRange] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [maxDepth, setMaxDepth] = useState('')
  const [maxBytes, setMaxBytes] = useState('')
  const [snowball, setSnowball] = useState(defaultSnowball)
  const [useScope, setUseScope] = useState(scopeAvailable && imageReady)
  const rangeSelected = Boolean(dateRange?.from && dateRange?.to)

  useEffect(() => {
    setEmbedImages(imageReady)
  }, [imageReady])

  useEffect(() => {
    setUseScope(scopeAvailable && imageReady)
  }, [scopeAvailable, imageReady])

  useEffect(() => {
    setEmbedText(textReady)
  }, [textReady])

  useEffect(() => {
    if (!rangeSelected) setRestrictRange(false)
  }, [rangeSelected])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const followForwards = snowballChoice ? snowball : true

  const start = () => {
    onStart({
      seed_external_id: peer.external_id,
      images,
      videos,
      participants,
      embed_images: imageReady && embedImages,
      embed_text: textReady && embedText,
      use_scope: Boolean(scopeAvailable && imageReady && embedImages && useScope),
      date_from: rangeSelected && dateRange?.from ? startOfDayIso(dateRange.from) : null,
      date_to: rangeSelected && dateRange?.to ? endOfDayIso(dateRange.to) : null,
      restrict_date_range: rangeSelected && restrictRange,
      max_depth: followForwards ? (maxDepth ? Number(maxDepth) : null) : 0,
      max_media_bytes: maxBytes ? Number(maxBytes) : null,
    })
  }

  return (
    <div className="modalScrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <h3 className={h.modalTitle}>{title}</h3>
        <div className={h.seed}>
          <PeerAvatar peer={peer} />
          <span className={h.hitBody}>
            <span className={h.hitTitle}>
              {(peer.title ?? '').trim() ||
                (peer.username ? `@${peer.username}` : String(peer.external_id))}
            </span>
            <span className={h.hitMeta}>
              {peerTypeLabel(peer.peer_type)}
              {peer.username ? ` · @${peer.username}` : ''}
            </span>
          </span>
        </div>

        {snowballChoice ? (
          <label className={h.option}>
            <input
              type="checkbox"
              checked={snowball}
              onChange={(event) => setSnowball(event.target.checked)}
            />
            <InfoTip text="Follow forwards from this peer into other communities. Leave off to scrape only this peer.">
              Snowball through forwards
            </InfoTip>
          </label>
        ) : null}

        <DateRangeField value={dateRange} onChange={setDateRange} popoverZIndex={90} />
        {rangeSelected ? (
          <label className={h.option}>
            <input
              type="checkbox"
              checked={restrictRange}
              onChange={(event) => setRestrictRange(event.target.checked)}
            />
            <InfoTip text="Only follow forwards whose source messages fall inside the selected dates.">
              Restrict forward crawl to date window
            </InfoTip>
          </label>
        ) : null}

        <label className={h.option}>
          <input type="checkbox" checked={images} onChange={(event) => setImages(event.target.checked)} />
          <InfoTip text="Images outside a selected date range are skipped. Inside the range, every image is still fetched long enough to compute a perceptual hash, then discarded. Enable this to keep the original files on disk.">
            Download and persist images
          </InfoTip>
        </label>
        <label className={h.option}>
          <input type="checkbox" checked={videos} onChange={(event) => setVideos(event.target.checked)} />
          <span className={h.optionLabel}>Download videos</span>
        </label>
        <label className={h.option}>
          <input
            type="checkbox"
            checked={participants}
            onChange={(event) => setParticipants(event.target.checked)}
          />
          <InfoTip text="Also store the member list for groups and channels you can access.">
            Scrape participants
          </InfoTip>
        </label>
        <label className={`${h.option}${imageReady ? '' : ` ${h.optionDisabled}`}`}>
          <input
            type="checkbox"
            checked={embedImages}
            disabled={!imageReady}
            onChange={(event) => setEmbedImages(event.target.checked)}
          />
          <InfoTip text="Embed scraped images in the selected vision model for visual similarity. Text-to-image search needs CLIP or SigLIP.">
            Embed images
          </InfoTip>
          {imageReady ? null : (
            <span className={h.modelWarn}>
              <TriangleAlert size={13} strokeWidth={2} aria-hidden />
              Please setup the model to use this option.
            </span>
          )}
        </label>
        {scopeAvailable ? (
          <label className={`${h.option}${imageReady && embedImages ? '' : ` ${h.optionDisabled}`}`}>
            <input
              type="checkbox"
              checked={useScope && imageReady && embedImages}
              disabled={!imageReady || !embedImages}
              onChange={(event) => setUseScope(event.target.checked)}
            />
            <InfoTip text="After the first channel is scraped, prefer forwarded communities that match your Scope inputs instead of visiting them in first-seen order.">
              Steer by scope
            </InfoTip>
          </label>
        ) : null}
        <label className={`${h.option}${textReady ? '' : ` ${h.optionDisabled}`}`}>
          <input
            type="checkbox"
            checked={embedText}
            disabled={!textReady}
            onChange={(event) => setEmbedText(event.target.checked)}
          />
          <InfoTip text="Embed message text in the selected text model so forwards can be matched by meaning.">
            Embed message text
          </InfoTip>
          {textReady ? null : (
            <span className={h.modelWarn}>
              <TriangleAlert size={13} strokeWidth={2} aria-hidden />
              Please setup the model to use this option.
            </span>
          )}
        </label>

        <button
          type="button"
          className={h.advanced}
          aria-expanded={advanced}
          onClick={() => setAdvanced((value) => !value)}
        >
          Advanced
          <ChevronRight className={h.advancedChevron} size={14} strokeWidth={2} aria-hidden />
        </button>
        {advanced ? (
          <div className={h.advancedPanel}>
            {followForwards ? (
              <label className={h.advRow} htmlFor="depth">
                <span>Max depth</span>
                <input
                  id="depth"
                  className={h.advInput}
                  inputMode="numeric"
                  placeholder="Unlimited"
                  value={maxDepth}
                  onChange={(event) => setMaxDepth(event.target.value)}
                />
              </label>
            ) : null}
            <label className={h.advRow} htmlFor="bytes">
              <span>Max media bytes</span>
              <input
                id="bytes"
                className={h.advInput}
                inputMode="numeric"
                placeholder="None"
                value={maxBytes}
                onChange={(event) => setMaxBytes(event.target.value)}
              />
            </label>
          </div>
        ) : null}

        <div className={h.actions}>
          <button className="btn btnPrimary" disabled={busy} onClick={start}>
            {startLabel}
          </button>
          <button className="btn" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

import { ChevronDown, ChevronRight, Layers, Maximize2, Plus, RotateCcw, Settings2 } from 'lucide-react'
import { useState } from 'react'
import type { DateRange } from 'react-day-picker'
import { DateRangeField } from './DateRangeField'
import {
  cloneGraphView,
  DEFAULT_GRAPH_LAYERS,
  DEFAULT_GRAPH_QUERY,
  DEFAULT_GRAPH_VIEW,
  GRAPH_EDGE_LAYER_LABELS,
  GRAPH_LAYER_PRESETS,
  MEDIA_FILTER_KEYS,
  MEDIA_FILTER_LABELS,
  cloneGraphLayers,
  cloneGraphQuery,
  matchingLayerPresetId,
  type GraphLayersConfig,
  type GraphQueryConfig,
  type GraphViewConfig,
  type MediaFilterKey,
} from '../lib/graphConfig'
import { endOfDayIso, isoToDate, startOfDayIso } from '../lib/graphQuery'
import s from './GraphControls.module.css'

type Props = {
  view: GraphViewConfig
  onChange: (view: GraphViewConfig) => void
  onFitView: () => void
  onRestartLayout: () => void
  pendingNewNodes?: number
  onLoadNewNodes?: () => void
}

function SliderRow({
  label,
  hint,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string
  hint?: string
  value: number
  min: number
  max: number
  step: number
  format?: (value: number) => string
  onChange: (value: number) => void
}) {
  const shown = format ? format(value) : String(value)
  return (
    <label className={s.slider}>
      <span className={s.sliderHead}>
        <span className={s.sliderLabel} title={hint}>
          {label}
        </span>
        <span className={s.sliderValue}>{shown}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  )
}

function CheckRow({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string
  hint?: string
  checked: boolean
  disabled?: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className={`${s.check}${disabled ? ` ${s.checkDisabled}` : ''}`} title={hint}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{label}</span>
    </label>
  )
}

function FoldHeader({
  label,
  open,
  onToggle,
}: {
  label: string
  open: boolean
  onToggle: () => void
}) {
  return (
    <button type="button" className={s.fold} aria-expanded={open} onClick={onToggle}>
      {label}
      <ChevronRight className={s.foldChevron} size={13} strokeWidth={2} aria-hidden />
    </button>
  )
}

function patchCosmos(view: GraphViewConfig, patch: Partial<GraphViewConfig['cosmos']>): GraphViewConfig {
  return { ...view, cosmos: { ...view.cosmos, ...patch } }
}

function patchSizing(view: GraphViewConfig, patch: Partial<GraphViewConfig['sizing']>): GraphViewConfig {
  return { ...view, sizing: { ...view.sizing, ...patch } }
}

function patchLabels(view: GraphViewConfig, patch: Partial<GraphViewConfig['labels']>): GraphViewConfig {
  return { ...view, labels: { ...view.labels, ...patch } }
}

function patchLayers(view: GraphViewConfig, patch: Partial<GraphLayersConfig>): GraphViewConfig {
  return { ...view, layers: { ...view.layers, ...patch } }
}

function patchMediaFilter(
  view: GraphViewConfig,
  key: MediaFilterKey,
  checked: boolean,
): GraphViewConfig {
  return patchLayers(view, {
    mediaFilter: { ...view.layers.mediaFilter, [key]: checked },
  })
}

function patchQuery(view: GraphViewConfig, patch: Partial<GraphQueryConfig>): GraphViewConfig {
  return { ...view, query: cloneGraphQuery({ ...(view.query ?? DEFAULT_GRAPH_QUERY), ...patch }) }
}

export function GraphControls({
  view,
  onChange,
  onFitView,
  onRestartLayout,
  pendingNewNodes = 0,
  onLoadNewNodes,
}: Props) {
  const [layersOpen, setLayersOpen] = useState(true)
  const [physicsOpen, setPhysicsOpen] = useState(false)
  const [nodesOpen, setNodesOpen] = useState(false)
  const [edgesOpen, setEdgesOpen] = useState(false)
  const c = view.cosmos
  const layers = view.layers
  const messagesOn = layers.forwardMessages
  const sharedOn = layers.sharedImages ?? false
  const query = view.query ?? DEFAULT_GRAPH_QUERY
  const dateRange: DateRange | undefined =
    query.dateFrom || query.dateTo
      ? { from: isoToDate(query.dateFrom), to: isoToDate(query.dateTo) }
      : undefined
  const presetId = matchingLayerPresetId(layers)
  const activePreset = GRAPH_LAYER_PRESETS.find((item) => item.id === presetId)

  return (
    <aside className={s.panel}>
      <div className={s.toolbar}>
        {pendingNewNodes > 0 ? (
          <button
            type="button"
            className={`${s.iconBtn} ${s.iconBtnHighlight}`}
            onClick={onLoadNewNodes}
            title="Add the new nodes to the graph"
          >
            <Plus size={14} strokeWidth={2} aria-hidden />
            {pendingNewNodes === 1 ? '1 new node' : `${pendingNewNodes} new nodes`}
          </button>
        ) : null}
        <button type="button" className={s.iconBtn} onClick={onFitView} title="Fit to view">
          <Maximize2 size={14} strokeWidth={2} aria-hidden />
          Fit
        </button>
        <button type="button" className={s.iconBtn} onClick={onRestartLayout} title="Restart layout">
          <RotateCcw size={14} strokeWidth={2} aria-hidden />
          Relayout
        </button>
        <button
          type="button"
          className={`${s.iconBtn} ${layersOpen ? s.iconBtnActive : ''}`}
          aria-expanded={layersOpen}
          onClick={() => setLayersOpen((value) => !value)}
        >
          <Layers size={14} strokeWidth={2} aria-hidden />
          Layers
          <ChevronDown
            size={14}
            strokeWidth={2}
            className={`${s.chevron}${layersOpen ? ` ${s.chevronOpen}` : ''}`}
            aria-hidden
          />
        </button>
        <button
          type="button"
          className={`${s.iconBtn} ${physicsOpen ? s.iconBtnActive : ''}`}
          aria-expanded={physicsOpen}
          onClick={() => setPhysicsOpen((value) => !value)}
        >
          <Settings2 size={14} strokeWidth={2} aria-hidden />
          Physics
          <ChevronDown
            size={14}
            strokeWidth={2}
            className={`${s.chevron}${physicsOpen ? ` ${s.chevronOpen}` : ''}`}
            aria-hidden
          />
        </button>
      </div>

      {layersOpen ? (
        <div className={s.body}>
          <p className={s.section}>Preset</p>
          <select
            className={s.presetSelect}
            value={presetId}
            aria-label="Layer preset"
            onChange={(event) => {
              const preset = GRAPH_LAYER_PRESETS.find((item) => item.id === event.target.value)
              if (!preset) return
              onChange(patchLayers(view, cloneGraphLayers(preset.layers)))
            }}
          >
            {GRAPH_LAYER_PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.label}
              </option>
            ))}
            {presetId === 'custom' ? (
              <option value="custom">Custom</option>
            ) : null}
          </select>
          {activePreset ? <p className={s.presetHint}>{activePreset.description}</p> : null}

          <FoldHeader label="Nodes" open={nodesOpen} onToggle={() => setNodesOpen((value) => !value)} />
          {nodesOpen ? (
            <>
              <CheckRow
                label="Scraped peers"
                checked={layers.scrapedPeers}
                onChange={(scrapedPeers) => onChange(patchLayers(view, { scrapedPeers }))}
              />
              <CheckRow
                label="Unscraped peers"
                checked={layers.unscrapedPeers}
                onChange={(unscrapedPeers) => onChange(patchLayers(view, { unscrapedPeers }))}
              />
              <CheckRow
                label="Forwarded messages"
                hint="One node per original message, with posted-in and forwarded-by edges"
                checked={layers.forwardMessages}
                onChange={(forwardMessages) =>
                  onChange(
                    patchLayers(view, {
                      forwardMessages,
                      sharedImages: forwardMessages ? false : layers.sharedImages,
                    }),
                  )
                }
              />
              <CheckRow
                label="Shared images"
                hint="One node per unique image that appears in two or more peers"
                checked={sharedOn}
                onChange={(sharedImages) =>
                  onChange(
                    patchLayers(
                      view,
                      sharedImages
                        ? {
                            sharedImages: true,
                            forwardMessages: false,
                            forwardFrom: false,
                            forwardTo: false,
                            sentTo: false,
                            forwardedFrom: false,
                            appearedIn: true,
                          }
                        : { sharedImages: false },
                    ),
                  )
                }
              />
              {messagesOn || sharedOn ? (
                <>
                  <p className={s.subSection}>Date range</p>
                  <div className={s.dateScope}>
                    <DateRangeField
                      value={dateRange}
                      onChange={(range) =>
                        onChange(
                          patchQuery(view, {
                            dateFrom: range?.from ? startOfDayIso(range.from) : null,
                            dateTo: range?.to ? endOfDayIso(range.to) : null,
                          }),
                        )
                      }
                    />
                  </div>
                </>
              ) : null}
              {messagesOn ? (
                <div className={s.nested}>
                  <CheckRow
                    label="Self-forwards"
                    hint="Messages a peer forwarded back to itself. Off by default."
                    checked={layers.selfForwards ?? false}
                    onChange={(selfForwards) => onChange(patchLayers(view, { selfForwards }))}
                  />
                  <CheckRow
                    label="Color by media"
                    hint="Tint forwarded-message nodes by stored media kind"
                    checked={layers.colorByMedia}
                    onChange={(colorByMedia) => onChange(patchLayers(view, { colorByMedia }))}
                  />
                  <p className={s.subSection}>Show media</p>
                  <div className={s.checkGrid}>
                    {MEDIA_FILTER_KEYS.map((key) => (
                      <CheckRow
                        key={key}
                        label={MEDIA_FILTER_LABELS[key]}
                        checked={layers.mediaFilter[key]}
                        onChange={(checked) => onChange(patchMediaFilter(view, key, checked))}
                      />
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          ) : null}

          <FoldHeader label="Edges" open={edgesOpen} onToggle={() => setEdgesOpen((value) => !value)} />
          {edgesOpen ? (
            <>
              <CheckRow
                label={GRAPH_EDGE_LAYER_LABELS.forwardFrom}
                hint="Peer that posted a forward → original peer"
                checked={layers.forwardFrom}
                onChange={(forwardFrom) => onChange(patchLayers(view, { forwardFrom }))}
              />
              <CheckRow
                label={GRAPH_EDGE_LAYER_LABELS.forwardTo}
                hint="Original peer → peer that posted the forward"
                checked={layers.forwardTo}
                onChange={(forwardTo) => onChange(patchLayers(view, { forwardTo }))}
              />
              <CheckRow
                label={GRAPH_EDGE_LAYER_LABELS.sentTo}
                hint="Message → peer that originally posted it"
                checked={layers.sentTo ?? true}
                disabled={!messagesOn}
                onChange={(sentTo) => onChange(patchLayers(view, { sentTo }))}
              />
              <CheckRow
                label={GRAPH_EDGE_LAYER_LABELS.forwardedFrom}
                hint="Peer that posted the forward → message"
                checked={layers.forwardedFrom ?? true}
                disabled={!messagesOn}
                onChange={(forwardedFrom) => onChange(patchLayers(view, { forwardedFrom }))}
              />
              <CheckRow
                label={GRAPH_EDGE_LAYER_LABELS.appearedIn}
                hint="Unique image → every peer it was posted in"
                checked={layers.appearedIn ?? true}
                disabled={!sharedOn}
                onChange={(appearedIn) => onChange(patchLayers(view, { appearedIn }))}
              />
            </>
          ) : null}
          <button
            type="button"
            className={s.reset}
            onClick={() => onChange(patchLayers(view, cloneGraphLayers(DEFAULT_GRAPH_LAYERS)))}
          >
            Reset layers
          </button>
        </div>
      ) : null}

      {physicsOpen ? (
        <div className={s.body}>
          <p className={s.section}>Forces</p>
          <SliderRow
            label="Gravity"
            hint="Pull toward the centre of the world"
            value={c.simulationGravity ?? 0.25}
            min={0}
            max={0.5}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(simulationGravity) => onChange(patchCosmos(view, { simulationGravity }))}
          />
          <SliderRow
            label="Repulsion"
            hint="How strongly nodes push apart"
            value={c.simulationRepulsion ?? 0.5}
            min={0}
            max={2}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(simulationRepulsion) => onChange(patchCosmos(view, { simulationRepulsion }))}
          />
          <SliderRow
            label="Link strength"
            hint="How tightly connected nodes pull together"
            value={c.simulationLinkSpring ?? 0}
            min={0}
            max={2}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(simulationLinkSpring) => onChange(patchCosmos(view, { simulationLinkSpring }))}
          />
          <SliderRow
            label="Link distance"
            hint="Preferred edge length. The example stops at 20; this goes higher so larger nodes do not overlap."
            value={c.simulationLinkDistance ?? 120}
            min={1}
            max={200}
            step={1}
            onChange={(simulationLinkDistance) => onChange(patchCosmos(view, { simulationLinkDistance }))}
          />
          <SliderRow
            label="Friction"
            hint="Damping. Higher keeps nodes moving longer."
            value={c.simulationFriction ?? 0.5}
            min={0}
            max={1}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(simulationFriction) => onChange(patchCosmos(view, { simulationFriction }))}
          />
          <SliderRow
            label="Cluster strength"
            hint="Pulls scraped, unscraped, and message nodes toward others of the same kind"
            value={c.simulationCluster ?? 0.05}
            min={0}
            max={1}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(simulationCluster) => onChange(patchCosmos(view, { simulationCluster }))}
          />

          <p className={s.section}>Size</p>
          <SliderRow
            label="Unique-peer weight"
            hint="How much unique forward neighbours grow a node"
            value={view.sizing.degreeWeight}
            min={0}
            max={3}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(degreeWeight) => onChange(patchSizing(view, { degreeWeight }))}
          />
          <SliderRow
            label="Volume weight"
            hint="How much total forwards grow a node"
            value={view.sizing.volumeWeight}
            min={0}
            max={2}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(volumeWeight) => onChange(patchSizing(view, { volumeWeight }))}
          />
          <SliderRow
            label="Base size"
            hint="Minimum peer size (at least 2× message nodes)"
            value={view.sizing.baseSize}
            min={0.4}
            max={8}
            step={0.1}
            format={(v) => v.toFixed(1)}
            onChange={(baseSize) => onChange(patchSizing(view, { baseSize }))}
          />
          <SliderRow
            label="Max size"
            value={view.sizing.maxSize}
            min={2}
            max={24}
            step={0.5}
            format={(v) => v.toFixed(1)}
            onChange={(maxSize) => onChange(patchSizing(view, { maxSize }))}
          />
          <SliderRow
            label="Message size"
            hint="Size of forwarded-message nodes"
            value={view.sizing.messageSize}
            min={0.6}
            max={8}
            step={0.1}
            format={(v) => v.toFixed(1)}
            onChange={(messageSize) => onChange(patchSizing(view, { messageSize }))}
          />

          <p className={s.section}>Links & labels</p>
          <SliderRow
            label="Link width"
            value={c.linkWidthScale ?? 1}
            min={0.2}
            max={6}
            step={0.1}
            format={(v) => v.toFixed(1)}
            onChange={(linkWidthScale) => onChange(patchCosmos(view, { linkWidthScale }))}
          />
          <SliderRow
            label="Link opacity"
            value={c.linkOpacity ?? 1}
            min={0.08}
            max={1}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(linkOpacity) => onChange(patchCosmos(view, { linkOpacity }))}
          />
          <SliderRow
            label="Labels (large nodes)"
            hint="Zoom where the biggest nodes show titles"
            value={view.labels.zoomAtMaxSize}
            min={0.2}
            max={6}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(zoomAtMaxSize) => onChange(patchLabels(view, { zoomAtMaxSize }))}
          />
          <SliderRow
            label="Labels (small nodes)"
            hint="Zoom required before the smallest nodes show titles"
            value={view.labels.zoomAtMinSize}
            min={1}
            max={16}
            step={0.1}
            format={(v) => v.toFixed(1)}
            onChange={(zoomAtMinSize) => onChange(patchLabels(view, { zoomAtMinSize }))}
          />
          <SliderRow
            label="Label fade"
            hint="How gradually titles appear after crossing their zoom threshold"
            value={view.labels.fadeSpan}
            min={0.1}
            max={3}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(fadeSpan) => onChange(patchLabels(view, { fadeSpan }))}
          />
          <SliderRow
            label="Max labels"
            value={view.labels.maxVisible}
            min={20}
            max={800}
            step={10}
            onChange={(maxVisible) => onChange(patchLabels(view, { maxVisible }))}
          />

          <button
            type="button"
            className={s.reset}
            onClick={() => onChange(cloneGraphView(DEFAULT_GRAPH_VIEW))}
          >
            Reset defaults
          </button>
        </div>
      ) : null}
    </aside>
  )
}

import { ChevronDown, Layers, Maximize2, Plus, Settings2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  cloneGraphView,
  DEFAULT_GRAPH_VIEW,
  GRAPH_LAYER_PRESETS,
  cloneGraphLayers,
  matchingLayerPresetId,
  type GraphLayersConfig,
  type GraphViewConfig,
} from '../lib/graphConfig'
import s from './GraphControls.module.css'

type Props = {
  view: GraphViewConfig
  onChange: (view: GraphViewConfig) => void
  onFitView: () => void
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

function patchCosmos(view: GraphViewConfig, patch: Partial<GraphViewConfig['cosmos']>): GraphViewConfig {
  return { ...view, cosmos: { ...view.cosmos, ...patch } }
}

function patchSizing(view: GraphViewConfig, patch: Partial<GraphViewConfig['sizing']>): GraphViewConfig {
  return { ...view, sizing: { ...view.sizing, ...patch } }
}

function patchLayers(view: GraphViewConfig, patch: Partial<GraphLayersConfig>): GraphViewConfig {
  return { ...view, layers: { ...view.layers, ...patch } }
}

export function GraphControls({
  view,
  onChange,
  onFitView,
  pendingNewNodes = 0,
  onLoadNewNodes,
}: Props) {
  const [layersOpen, setLayersOpen] = useState(true)
  const [physicsOpen, setPhysicsOpen] = useState(false)
  const c = view.cosmos
  const presetId = matchingLayerPresetId(view.layers)
  const selectValue = presetId === 'shared-images' ? 'shared-images' : 'peer-forwards'
  const activePreset = GRAPH_LAYER_PRESETS.find((item) => item.id === selectValue)

  useEffect(() => {
    if (presetId === 'peer-forwards' || presetId === 'shared-images') return
    const preset = GRAPH_LAYER_PRESETS.find((item) => item.id === 'peer-forwards')
    if (!preset) return
    onChange(patchLayers(view, cloneGraphLayers(preset.layers)))
  }, [presetId, onChange, view])

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
            {'Add '}
            {pendingNewNodes === 1 ? '1 new node to the graph' : `${pendingNewNodes} new nodes to the graph`}
          </button>
        ) : null}
        <button type="button" className={s.iconBtn} onClick={onFitView} title="Fit to view">
          <Maximize2 size={14} strokeWidth={2} aria-hidden />
          Fit
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
            value={selectValue}
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
          </select>
          {activePreset ? <p className={s.presetHint}>{activePreset.description}</p> : null}
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
            hint="Preferred edge length"
            value={c.simulationLinkDistance ?? 1}
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
            hint="Pulls scraped and unscraped peers toward others of the same kind"
            value={c.simulationCluster ?? 0}
            min={0}
            max={1}
            step={0.01}
            format={(v) => v.toFixed(2)}
            onChange={(simulationCluster) => onChange(patchCosmos(view, { simulationCluster }))}
          />

          <p className={s.section}>Size</p>
          <SliderRow
            label="Volume weight"
            hint="How much incident forward volume grows a peer"
            value={view.sizing.volumeWeight}
            min={0}
            max={2}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(volumeWeight) => onChange(patchSizing(view, { volumeWeight }))}
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

import {
  Cosmograph,
  CosmographProvider,
  type CosmographConfig,
  type CosmographRef,
} from '@cosmograph/react'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, type CSSProperties } from 'react'
import type { ForwardGraphEdge, ForwardGraphNode } from '../lib/api'
import {
  DEFAULT_GRAPH_VIEW,
  GRAPH_CONFIG,
  colorForEdge,
  colorForNode,
  sizeForNode,
  titleForNode,
  type GraphViewConfig,
} from '../lib/graphConfig'
import s from './CosmosGraph.module.css'

type CosmosGraphProps = {
  nodes: ForwardGraphNode[]
  edges: ForwardGraphEdge[]
  selectedId?: string | null
  onNodeClick?: (node: ForwardGraphNode | null) => void
  view?: GraphViewConfig
}

export type CosmosGraphHandle = {
  clearSelection: () => void
  fitView: () => void
  resume: () => void
  persistLayout: () => void
}

/** CSS custom properties so label classes stay in lock-step with GRAPH_CONFIG.colors. */
const labelColorVars = {
  '--graph-scraped': GRAPH_CONFIG.colors.scraped,
  '--graph-unscraped': GRAPH_CONFIG.colors.unscraped,
  '--graph-scraping': GRAPH_CONFIG.colors.scraping,
  '--graph-message': GRAPH_CONFIG.colors.message,
} as CSSProperties

function definedConfig(values: CosmographConfig): CosmographConfig {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined))
}

/** Stable identity. A new function here makes Cosmograph rebuild the WebGL graph. */
function pointSizeFromColumn(value: number): number {
  const px = Number(value)
  return Number.isFinite(px) && px > 0 ? px : 1
}

function cosmographConfig(view: GraphViewConfig): CosmographConfig {
  const engine = GRAPH_CONFIG.cosmograph
  const physics = view.cosmos
  return definedConfig({
    pointIdBy: engine.pointIdBy,
    pointLabelBy: engine.pointLabelBy,
    pointColorBy: engine.pointColorBy,
    pointColorStrategy: engine.pointColorStrategy,
    linkSourceBy: engine.linkSourceBy,
    linkTargetBy: engine.linkTargetBy,
    linkColorBy: engine.linkColorBy,
    linkColorStrategy: engine.linkColorStrategy,
    fitViewOnInit: engine.fitViewOnInit,
    initialZoomLevel: engine.initialZoomLevel,
    backgroundColor: physics.backgroundColor,
    hoveredPointRingColor: physics.hoveredPointRingColor,
    pointGreyoutColor: physics.pointGreyoutColor,
    pointGreyoutOpacity: physics.pointGreyoutOpacity,
    linkGreyoutOpacity: physics.linkGreyoutOpacity,
    linkDefaultWidth: physics.linkDefaultWidth,
    linkWidthScale: physics.linkWidthScale,
    linkOpacity: physics.linkOpacity,
    fitViewDelay: physics.fitViewDelay,
    fitViewPadding: physics.fitViewPadding,
    pointSize: physics.pointSize,
    pointDefaultSize: physics.pointDefaultSize,
    // `pointSizeStrategy: 'direct'` ignores pointSizeByFn. Leave the strategy unset
    // so this function is what the library actually calls.
    pointSizeBy: 'fwd',
    pointSizeByFn: pointSizeFromColumn,
    // File value, not the saved view. A stored `true` clamps every sprite to one size.
    scalePointsOnZoom: GRAPH_CONFIG.cosmos.scalePointsOnZoom,
    scaleLinksOnZoom: physics.scaleLinksOnZoom,
    simulationGravity: physics.simulationGravity,
    simulationCenter: physics.simulationCenter,
    simulationRepulsion: physics.simulationRepulsion,
    simulationRepulsionTheta: physics.simulationRepulsionTheta,
    simulationCluster: physics.simulationCluster,
    pointClusterBy: physics.simulationCluster != null ? 'group' : undefined,
    simulationLinkSpring: physics.simulationLinkSpring,
    simulationLinkDistance: physics.simulationLinkDistance,
    simulationLinkDistRandomVariationRange: physics.simulationLinkDistRandomVariationRange,
    simulationFriction: physics.simulationFriction,
    simulationDecay: physics.simulationDecay,
  })
}

function labelClassForNode(node: ForwardGraphNode | undefined): string {
  if (!node) return s.unscraped
  if (node.is_scraping) return s.scraping
  if (node.kind === 'message' || node.kind === 'image') return s.message
  if (node.scraped) return s.scraped
  return s.unscraped
}

const CosmosGraph = forwardRef<CosmosGraphHandle, CosmosGraphProps>(function CosmosGraph(
  { nodes, edges, selectedId = null, onNodeClick, view = DEFAULT_GRAPH_VIEW },
  ref,
) {
  const cosmographRef = useRef<CosmographRef>(undefined)
  const onNodeClickRef = useRef(onNodeClick)
  onNodeClickRef.current = onNodeClick
  const nodesRef = useRef(nodes)
  nodesRef.current = nodes

  const points = useMemo(() => {
    let maxVolume = 1
    for (const node of nodes) {
      if (node.kind === 'message' || node.kind === 'image') continue
      maxVolume = Math.max(maxVolume, node.forward_volume ?? 0)
    }
    const defaultSize = view.cosmos.pointDefaultSize
    return nodes.map((node) => ({
      id: node.id,
      label: titleForNode(node) ?? node.id,
      color: colorForNode(node, view.layers),
      fwd: sizeForNode(node, view.sizing, defaultSize, maxVolume),
      group: node.is_scraping
        ? 'scraping'
        : node.kind === 'message'
          ? 'message'
          : node.kind === 'image'
            ? 'image'
            : node.scraped
              ? 'scraped'
              : 'unscraped',
    }))
  }, [nodes, view.layers, view.sizing, view.cosmos.pointDefaultSize])

  const links = useMemo(
    () =>
      edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        color: colorForEdge(edge.kind ?? 'forward_from', view.cosmos.linkColor),
      })),
    [edges, view.cosmos.linkColor],
  )

  const config = useMemo(() => cosmographConfig(view), [view])
  const engine = GRAPH_CONFIG.cosmograph
  const initialZoomLevel = engine.initialZoomLevel

  useImperativeHandle(ref, () => ({
    clearSelection: () => {
      cosmographRef.current?.selectPoints(null)
    },
    fitView: () => {
      const padding = view.cosmos.fitViewPadding
      if (padding == null) cosmographRef.current?.fitView(250)
      else cosmographRef.current?.fitView(250, padding)
    },
    resume: () => {
      cosmographRef.current?.unpause()
    },
    persistLayout: () => {},
  }))

  useEffect(() => {
    const graph = cosmographRef.current
    if (!graph) return
    if (!selectedId) {
      graph.selectPoints(null)
      return
    }
    const index = nodes.findIndex((node) => node.id === selectedId)
    if (index < 0) {
      graph.selectPoints(null)
      return
    }
    // Third argument selects the point's neighbours and their edges, which is the library default.
    graph.selectPoint(index, false, true)
  }, [selectedId, nodes])

  // Mark a force change, then start only from onConfigUpdated so the new values are already applied.
  const simulationKey = [
    view.cosmos.simulationGravity,
    view.cosmos.simulationRepulsion,
    view.cosmos.simulationLinkSpring,
    view.cosmos.simulationLinkDistance,
    view.cosmos.simulationFriction,
    view.cosmos.simulationCluster,
  ].join('|')
  const simulationKeyRef = useRef(simulationKey)
  const pendingSimulationStart = useRef(false)
  useEffect(() => {
    if (simulationKeyRef.current === simulationKey) return
    simulationKeyRef.current = simulationKey
    pendingSimulationStart.current = true
  }, [simulationKey])

  // Cosmograph deletes `initialZoomLevel` before constructing cosmos.gl, so it is a no-op
  // unless we set it ourselves once the WebGL graph exists.
  useEffect(() => {
    let cancelled = false
    let attempts = 0
    const apply = () => {
      if (cancelled) return
      const graph = cosmographRef.current
      if (graph && graph.getZoomLevel() != null) {
        graph.setZoomLevel(initialZoomLevel, 0)
        return
      }
      attempts += 1
      if (attempts < 180) requestAnimationFrame(apply)
    }
    apply()
    return () => {
      cancelled = true
    }
  }, [initialZoomLevel])

  // These have to stay referentially stable. Cosmograph treats any new function prop as a
  // config change and rebuilds the WebGL graph. Jobs and stats both update during the
  // first load, and a rebuild that overlaps the initial one draws the graph a second time.
  const handleMount = useCallback((graph: CosmographRef) => {
    cosmographRef.current = graph
  }, [])
  const handleConfigUpdated = useCallback(() => {
    const graph = cosmographRef.current
    if (graph == null) return
    if (pendingSimulationStart.current) {
      pendingSimulationStart.current = false
      graph.start()
    }
    const current = graph.getZoomLevel()
    if (current == null) return
    if (Math.abs(current - 1) < 0.02 && Number(initialZoomLevel) !== 1) {
      graph.setZoomLevel(initialZoomLevel, 0)
    }
  }, [initialZoomLevel])
  const handleClick = useCallback((index: number | undefined) => {
    if (index == null) {
      onNodeClickRef.current?.(null)
      return
    }
    onNodeClickRef.current?.(nodesRef.current[index] ?? null)
  }, [])
  const pointLabelClassName = useCallback(
    (_: unknown, index: number) => labelClassForNode(nodesRef.current[index]),
    [],
  )

  return (
    <div className={s.wrap} style={labelColorVars}>
      <CosmographProvider>
        <Cosmograph
          ref={cosmographRef}
          className={s.graph}
          points={points}
          links={links}
          {...config}
          onMount={handleMount}
          onConfigUpdated={handleConfigUpdated}
          selectPointOnClick={engine.selectPointOnClick}
          selectPointOnLabelClick={engine.selectPointOnLabelClick}
          showHoveredPointLabel={engine.showHoveredPointLabel}
          hoveredPointLabelClassName={s.hoveredLabel}
          pointLabelClassName={pointLabelClassName}
          onClick={handleClick}
        />
      </CosmographProvider>
    </div>
  )
})

export default CosmosGraph

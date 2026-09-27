import { Graph } from '@cosmos.gl/graph'
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { ForwardGraphEdge, ForwardGraphNode } from '../lib/api'
import {
  DEFAULT_GRAPH_VIEW,
  GRAPH_CONFIG,
  labelOpacityForZoom,
  sizeForNode,
  titleForNode,
  truncateLabel,
  type GraphViewConfig,
} from '../lib/graphConfig'
import {
  appendStableNodeOrder,
  capturePositionsById,
  graphStructureKey,
  neighbourLookupFromLinks,
  partitionLayoutGraph,
  physicsConfigKey,
  placeMessageSatellites,
  shouldSatelliteMessages,
  toCosmosData,
  type CosmosGraphData,
} from '../lib/cosmosUtils'
import {
  clearGraphLayoutSession,
  readGraphLayoutSession,
  writeGraphNodeOrder,
  writeGraphPositions,
} from '../lib/graphSession'
import s from './CosmosGraph.module.css'

type CosmosGraphProps = {
  nodes: ForwardGraphNode[]
  edges: ForwardGraphEdge[]
  selectedId?: string | null
  onNodeClick?: (node: ForwardGraphNode | null) => void
  view?: GraphViewConfig
  /** Bump to forget saved positions and re-run the force layout. */
  layoutEpoch?: number
}

export type CosmosGraphHandle = {
  clearSelection: () => void
  fitView: () => void
  restartLayout: () => void
  resume: () => void
  persistLayout: () => void
}

type OverlayLabel = {
  id: string
  text: string
  fullText: string
  x: number
  y: number
  opacity: number
  scraped: boolean
  scraping: boolean
}

type ScrapeGlow = {
  x: number
  y: number
}

type LabelCandidate = OverlayLabel & { size: number }

function scrapeNodeIndex(nodes: ForwardGraphNode[]): number {
  return nodes.findIndex((node) => node.kind !== 'message' && node.is_scraping)
}

function applyScrapeFocus(graph: InstanceType<typeof Graph>, nodes: ForwardGraphNode[]) {
  const index = scrapeNodeIndex(nodes)
  graph.setConfig({
    focusedPointRingColor: GRAPH_CONFIG.colors.scraping,
    focusedPointIndex: index >= 0 ? index : undefined,
  })
}

function applyLinkColors(graph: InstanceType<typeof Graph>, colors: Float32Array) {
  const setter = (graph as unknown as { setLinkColors?: (value: Float32Array) => void }).setLinkColors
  setter?.call(graph, colors)
}

function applyCosmosBuffers(graph: InstanceType<typeof Graph>, data: CosmosGraphData) {
  graph.setPointPositions(data.pointPositions)
  graph.setPointColors(data.pointColors)
  graph.setPointSizes(data.pointSizes)
  graph.setLinks(data.links)
  graph.setLinkWidths(data.linkWidths)
  applyLinkColors(graph, data.linkColors)
}

const CosmosGraph = forwardRef<CosmosGraphHandle, CosmosGraphProps>(function CosmosGraph(
  { nodes, edges, selectedId = null, onNodeClick, view = DEFAULT_GRAPH_VIEW, layoutEpoch = 0 },
  ref,
) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const graphRef = useRef<HTMLDivElement | null>(null)
  const graphInstanceRef = useRef<InstanceType<typeof Graph> | null>(null)
  const onNodeClickRef = useRef(onNodeClick)
  const selectedIdRef = useRef(selectedId)
  selectedIdRef.current = selectedId
  const viewRef = useRef(view)
  viewRef.current = view
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  const skipPhysicsRef = useRef(true)
  const skipDataRef = useRef(true)
  const lastEpochRef = useRef(layoutEpoch)
  const appliedTopologyRef = useRef<string>('')
  const appliedPeerKeyRef = useRef<string>('')
  const appliedNodesRef = useRef<ForwardGraphNode[]>([])
  const appliedEdgesRef = useRef<ForwardGraphEdge[]>([])
  const pointIdToIndexRef = useRef<Map<string, number>>(new Map())
  const neighbourLookupRef = useRef<Map<number, Set<number>>>(new Map())
  const highlightedIndicesRef = useRef<Set<number> | null>(null)
  const hoveredIndexRef = useRef<number | undefined>(undefined)
  const draggingIdRef = useRef<string | null>(null)
  const labelRafRef = useRef<number | null>(null)
  const simulatingRef = useRef(false)
  const lastGlowMsRef = useRef(0)
  const labelsClearedForSimRef = useRef(false)
  const positionsByIdRef = useRef<Map<string, [number, number]>>(new Map())
  const nodeOrderRef = useRef<string[]>([])
  const layoutHydratedRef = useRef(false)
  if (!layoutHydratedRef.current) {
    layoutHydratedRef.current = true
    const session = readGraphLayoutSession()
    positionsByIdRef.current = session.positions
    nodeOrderRef.current = session.nodeOrder
  }
  const [labels, setLabels] = useState<OverlayLabel[]>([])
  const [scrapeGlow, setScrapeGlow] = useState<ScrapeGlow | null>(null)

  if (layoutEpoch !== lastEpochRef.current) {
    nodeOrderRef.current = []
    positionsByIdRef.current = new Map()
    clearGraphLayoutSession()
  }

  const { ordered, order } = appendStableNodeOrder(nodes, nodeOrderRef.current)
  nodeOrderRef.current = order
  writeGraphNodeOrder(order)

  onNodeClickRef.current = onNodeClick
  const latestNodesRef = useRef(ordered)
  const latestEdgesRef = useRef(edges)
  const attachedRef = useRef(false)
  const satelliteRef = useRef(false)
  const attachSatellitesRef = useRef<() => void>(() => {})
  const beginPeerSimulationRef = useRef<(alpha: number) => void>(() => {})
  const syncSatellitePositionsRef = useRef<() => void>(() => {})
  latestNodesRef.current = ordered
  latestEdgesRef.current = edges
  if (graphInstanceRef.current == null) {
    nodesRef.current = ordered
    edgesRef.current = edges
  }

  const partition = useMemo(() => partitionLayoutGraph(ordered, edges), [ordered, edges])
  const satellite = shouldSatelliteMessages(partition, ordered.length, edges.length)
  const topologyKey = useMemo(() => graphStructureKey(ordered, edges), [ordered, edges])
  const peerTopologyKey = useMemo(
    () => graphStructureKey(partition.peers, partition.peerEdges),
    [partition],
  )
  const remountKey = `${view.layout.spaceSize}|${layoutEpoch}|${satellite ? 's' : 'n'}|lz`
  const physicsKey = physicsConfigKey(view)
  satelliteRef.current = satellite

  const appearanceKey = useMemo(() => {
    let hash = ordered.length | 0
    for (const node of ordered) {
      hash = (hash * 33 + (node.scraped ? 11 : 5)) | 0
      hash = (hash * 33 + (node.is_scraping ? 19 : 3)) | 0
      hash = (hash * 33 + (node.kind === 'message' ? 7 : node.kind === 'image' ? 23 : 2)) | 0
      hash = (hash * 33 + (node.stub ? 17 : 1)) | 0
      hash = (hash * 33 + (node.media_kind ?? '').length) | 0
      hash = (hash * 33 + (node.degree | 0)) | 0
      hash = (hash * 33 + (node.forward_volume | 0)) | 0
    }
    for (const edge of edges) hash = (hash * 33 + (edge.count | 0)) | 0
    hash = (hash * 33 + Math.round(view.sizing.baseSize * 100)) | 0
    hash = (hash * 33 + Math.round(view.sizing.scoreScale * 100)) | 0
    hash = (hash * 33 + Math.round(view.sizing.maxSize * 100)) | 0
    hash = (hash * 33 + Math.round(view.sizing.degreeWeight * 100)) | 0
    hash = (hash * 33 + Math.round(view.sizing.volumeWeight * 100)) | 0
    hash = (hash * 33 + Math.round((view.sizing.messageSize ?? 2.2) * 100)) | 0
    hash = (hash * 33 + Math.round(view.cosmos.linkWidthScale * 100)) | 0
    hash = (hash * 33 + (view.layers.colorByMedia ? 13 : 4)) | 0
    const palette = `${GRAPH_CONFIG.colors.message}|${GRAPH_CONFIG.colors.scraping}|${Object.values(GRAPH_CONFIG.colors.media).join('|')}|${Object.values(GRAPH_CONFIG.colors.edges).join('|')}`
    for (let i = 0; i < palette.length; i++) hash = (hash * 33 + palette.charCodeAt(i)) | 0
    return hash
  }, [ordered, edges, view.sizing, view.cosmos.linkWidthScale, view.layers.colorByMedia])

  const emitPositions = (positions: Map<string, [number, number]>) => {
    positionsByIdRef.current = positions
    writeGraphPositions(positions)
  }

  const captureLivePositions = () => {
    const g = graphInstanceRef.current
    const applied = appliedNodesRef.current
    if (!g || applied.length === 0) return
    try {
      const live = g.getPointPositions?.() as ArrayLike<number> | undefined
      if (live && live.length >= applied.length * 2) {
        const next = new Map(positionsByIdRef.current)
        for (const [id, pos] of capturePositionsById(applied, live)) next.set(id, pos)
        emitPositions(next)
      }
    } catch {
      // ignore
    }
  }

  const attachSatellites = () => {
    const g = graphInstanceRef.current
    if (!g) return
    const fullNodes = latestNodesRef.current
    const fullEdges = latestEdgesRef.current
    const nextPartition = partitionLayoutGraph(fullNodes, fullEdges)
    captureLivePositions()
    const peerPositions = new Map(positionsByIdRef.current)
    const messagePositions = placeMessageSatellites(nextPartition, peerPositions, viewRef.current)
    const merged = new Map(peerPositions)
    for (const [id, pos] of messagePositions) merged.set(id, pos)
    emitPositions(merged)
    const data = toCosmosData(fullNodes, fullEdges, merged, viewRef.current)
    applyCosmosBuffers(g, data)
    nodesRef.current = fullNodes
    edgesRef.current = fullEdges
    appliedNodesRef.current = fullNodes
    appliedEdgesRef.current = fullEdges
    pointIdToIndexRef.current = data.pointIdToIndex
    neighbourLookupRef.current = neighbourLookupFromLinks(data.links)
    appliedTopologyRef.current = graphStructureKey(fullNodes, fullEdges)
    appliedPeerKeyRef.current = graphStructureKey(nextPartition.peers, nextPartition.peerEdges)
    attachedRef.current = true
    simulatingRef.current = false
    applyScrapeFocus(g, fullNodes)
    g.pause()
    g.render(0)
    scheduleLabelRefresh()
  }
  attachSatellitesRef.current = attachSatellites

  const syncSatellitePositions = () => {
    const g = graphInstanceRef.current
    if (!g || !attachedRef.current) return
    const fullNodes = latestNodesRef.current
    const fullEdges = latestEdgesRef.current
    const nextPartition = partitionLayoutGraph(fullNodes, fullEdges)
    let current = positionsByIdRef.current
    try {
      const live = g.getPointPositions?.() as ArrayLike<number> | undefined
      if (live && live.length >= fullNodes.length * 2) {
        current = capturePositionsById(fullNodes, live)
      }
    } catch {
      // ignore
    }
    const peerPositions = new Map<string, [number, number]>()
    for (const peer of nextPartition.peers) {
      const pos = current.get(peer.id)
      if (pos) peerPositions.set(peer.id, pos)
    }
    const messagePositions = placeMessageSatellites(nextPartition, peerPositions, viewRef.current)
    const merged = new Map(current)
    for (const [id, pos] of messagePositions) merged.set(id, pos)
    const indexMap = pointIdToIndexRef.current
    const next = new Float32Array(fullNodes.length * 2)
    for (let i = 0; i < fullNodes.length; i++) {
      const pos = merged.get(fullNodes[i].id)
      const index = indexMap.get(fullNodes[i].id) ?? i
      if (!pos) continue
      next[index * 2] = pos[0]
      next[index * 2 + 1] = pos[1]
    }
    g.setPointPositions(next)
    g.render(0)
    emitPositions(merged)
    scheduleLabelRefresh()
  }
  syncSatellitePositionsRef.current = syncSatellitePositions

  const beginPeerSimulation = (alpha: number) => {
    const g = graphInstanceRef.current
    if (!g) return
    const fullNodes = latestNodesRef.current
    const fullEdges = latestEdgesRef.current
    const nextPartition = partitionLayoutGraph(fullNodes, fullEdges)
    const useSatellite = shouldSatelliteMessages(nextPartition, fullNodes.length, fullEdges.length)
    satelliteRef.current = useSatellite
    if (!useSatellite) {
      const data = toCosmosData(fullNodes, fullEdges, positionsByIdRef.current, viewRef.current)
      applyCosmosBuffers(g, data)
      nodesRef.current = fullNodes
      edgesRef.current = fullEdges
      appliedNodesRef.current = fullNodes
      appliedEdgesRef.current = fullEdges
      pointIdToIndexRef.current = data.pointIdToIndex
      neighbourLookupRef.current = neighbourLookupFromLinks(data.links)
      appliedTopologyRef.current = graphStructureKey(fullNodes, fullEdges)
      appliedPeerKeyRef.current = graphStructureKey(nextPartition.peers, nextPartition.peerEdges)
      attachedRef.current = true
      simulatingRef.current = true
      applyScrapeFocus(g, fullNodes)
      g.start(alpha)
      return
    }
    captureLivePositions()
    const data = toCosmosData(
      nextPartition.peers,
      nextPartition.peerEdges,
      positionsByIdRef.current,
      viewRef.current,
    )
    applyCosmosBuffers(g, data)
    nodesRef.current = nextPartition.peers
    edgesRef.current = nextPartition.peerEdges
    appliedNodesRef.current = nextPartition.peers
    appliedEdgesRef.current = nextPartition.peerEdges
    pointIdToIndexRef.current = data.pointIdToIndex
    neighbourLookupRef.current = neighbourLookupFromLinks(data.links)
    appliedPeerKeyRef.current = graphStructureKey(nextPartition.peers, nextPartition.peerEdges)
    attachedRef.current = false
    simulatingRef.current = true
    applyScrapeFocus(g, nextPartition.peers)
    g.start(alpha)
  }
  beginPeerSimulationRef.current = beginPeerSimulation

  const refreshLabels = () => {
    const g = graphInstanceRef.current
    const wrap = wrapRef.current
    if (!g || !wrap) {
      setLabels([])
      setScrapeGlow(null)
      return
    }

    const highlighted = highlightedIndicesRef.current
    const { maxVisible, offsetY, viewportPaddingPx, minGapPx } = viewRef.current.labels
    const currentNodes = nodesRef.current
    const scrapeIndex = scrapeNodeIndex(currentNodes)
    const glowOnly = simulatingRef.current

    let zoom = 0
    try {
      zoom = g.getZoomLevel()
    } catch {
      setLabels([])
      setScrapeGlow(null)
      return
    }

    const positions = g.getPointPositions()
    if (!positions || positions.length < currentNodes.length * 2) {
      setLabels([])
      setScrapeGlow(null)
      return
    }

    const width = wrap.clientWidth
    const height = wrap.clientHeight
    const inView = (x: number, y: number) =>
      x >= -viewportPaddingPx &&
      y >= -viewportPaddingPx &&
      x <= width + viewportPaddingPx &&
      y <= height + viewportPaddingPx

    let nextGlow: ScrapeGlow | null = null
    if (scrapeIndex >= 0) {
      try {
        const [gx, gy] = g.spaceToScreenPosition([
          positions[scrapeIndex * 2],
          positions[scrapeIndex * 2 + 1],
        ])
        if (inView(gx, gy)) nextGlow = { x: gx, y: gy }
      } catch {
        // node may be off-space during layout
      }
    }
    setScrapeGlow(nextGlow)

    if (glowOnly) {
      if (!labelsClearedForSimRef.current) {
        labelsClearedForSimRef.current = true
        setLabels([])
      }
      return
    }
    labelsClearedForSimRef.current = false

    const candidates: LabelCandidate[] = []
    let scrapeLabel: LabelCandidate | null = null
    const draggingId = draggingIdRef.current

    for (let i = 0; i < currentNodes.length; i++) {
      const node = currentNodes[i]
      if (node.kind === 'message') continue
      const scraping = i === scrapeIndex
      if (highlighted && !highlighted.has(i) && !scraping) continue
      if (draggingId && node.id === draggingId) continue
      const size = sizeForNode(node, viewRef.current.sizing)
      const opacity = scraping ? 1 : labelOpacityForZoom(size, zoom, viewRef.current)
      if (opacity < 0.08) continue
      const rawTitle = titleForNode(node)
      if (!rawTitle) continue
      let x: number
      let y: number
      try {
        ;[x, y] = g.spaceToScreenPosition([positions[i * 2], positions[i * 2 + 1]])
      } catch {
        continue
      }
      if (!inView(x, y)) continue
      const candidate: LabelCandidate = {
        id: node.id,
        text: truncateLabel(rawTitle, viewRef.current.labels.maxChars),
        fullText: rawTitle,
        x,
        y: y + offsetY,
        opacity,
        scraped: node.scraped || scraping,
        scraping,
        size,
      }
      if (scraping) scrapeLabel = candidate
      else candidates.push(candidate)
    }

    candidates.sort((a, b) => b.size - a.size || b.opacity - a.opacity)
    const kept: LabelCandidate[] = scrapeLabel ? [scrapeLabel] : []
    const gap = Math.max(8, minGapPx)
    for (const candidate of candidates) {
      if (kept.length >= maxVisible) break
      const crowded = kept.some((other) => {
        if (other.scraping) return false
        const dx = other.x - candidate.x
        const dy = other.y - candidate.y
        return dx * dx + dy * dy < gap * gap
      })
      if (crowded) continue
      kept.push(candidate)
    }

    setLabels(
      kept.map(({ id, text, fullText, x, y, opacity, scraped, scraping }) => ({
        id,
        text,
        fullText,
        x,
        y,
        opacity,
        scraped,
        scraping,
      })),
    )
  }

  const refreshLabelsRef = useRef(refreshLabels)
  refreshLabelsRef.current = refreshLabels

  const scheduleLabelRefresh = () => {
    if (labelRafRef.current != null) return
    labelRafRef.current = window.requestAnimationFrame(() => {
      labelRafRef.current = null
      refreshLabelsRef.current()
    })
  }

  const highlightIndicesFor = (index: number): number[] => {
    const neighbours = Array.from(neighbourLookupRef.current.get(index) ?? [])
    const indices = [index, ...neighbours]
    const scrapeIndex = scrapeNodeIndex(nodesRef.current)
    if (scrapeIndex >= 0 && !indices.includes(scrapeIndex)) indices.push(scrapeIndex)
    return indices
  }

  const applyHighlightIndices = (indices: number[] | null) => {
    const g = graphInstanceRef.current
    if (!g) return
    if (!indices || indices.length === 0) {
      g.unselectPoints()
      highlightedIndicesRef.current = null
      scheduleLabelRefresh()
      return
    }
    g.selectPointsByIndices(indices)
    highlightedIndicesRef.current = new Set(indices)
    scheduleLabelRefresh()
  }

  const restoreHighlight = () => {
    const id = selectedIdRef.current
    if (!id) {
      applyHighlightIndices(null)
      return
    }
    const index = pointIdToIndexRef.current.get(id)
    if (index == null) {
      applyHighlightIndices(null)
      return
    }
    applyHighlightIndices(highlightIndicesFor(index))
  }

  const highlightAndSelect = (index: number) => {
    applyHighlightIndices(highlightIndicesFor(index))
    const node = nodesRef.current[index]
    if (node) onNodeClickRef.current?.(node)
  }

  const highlightAndSelectRef = useRef(highlightAndSelect)
  highlightAndSelectRef.current = highlightAndSelect
  const restoreHighlightRef = useRef(restoreHighlight)
  restoreHighlightRef.current = restoreHighlight

  const hideDraggedLabel = () => {
    const index = hoveredIndexRef.current
    const id = index != null ? nodesRef.current[index]?.id ?? null : null
    if (draggingIdRef.current === id) return
    draggingIdRef.current = id
    scheduleLabelRefresh()
  }

  const showDraggedLabel = () => {
    if (draggingIdRef.current == null) return
    draggingIdRef.current = null
    scheduleLabelRefresh()
  }

  const cosmosConstructorConfig = (currentView: GraphViewConfig) => {
    const c = currentView.cosmos
    const layout = currentView.layout
    return {
      enableSimulation: true,
      spaceSize: layout.spaceSize,
      backgroundColor: c.backgroundColor,
      scalePointsOnZoom: true,
      linkDefaultWidth: c.linkDefaultWidth,
      linkWidthScale: c.linkWidthScale,
      linkColor: c.linkColor,
      linkOpacity: c.linkOpacity,
      linkArrows: false,
      scaleLinksOnZoom: true,
      enableSimulationDuringZoom: false,
      pixelRatio: satelliteRef.current
        ? 1
        : Math.min(2, typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1),
      linkVisibilityDistanceRange: [...c.linkVisibilityDistanceRange] as [number, number],
      linkVisibilityMinTransparency: c.linkVisibilityMinTransparency,
      fitViewOnInit: false,
      fitViewDelay: 0,
      fitViewPadding: c.fitViewPadding,
      pointSize: c.pointSize,
      enableDrag: true,
      pointGreyoutColor: c.pointGreyoutColor,
      pointGreyoutOpacity: c.pointGreyoutOpacity,
      linkGreyoutOpacity: c.linkGreyoutOpacity,
      simulationFriction: c.simulationFriction,
      simulationDecay: c.simulationDecay,
      simulationCenter: c.simulationCenter,
      simulationGravity: c.simulationGravity,
      simulationLinkSpring: c.simulationLinkSpring,
      simulationLinkDistance: c.simulationLinkDistance,
      simulationLinkDistRandomVariationRange: [...c.simulationLinkDistRandomVariationRange] as [
        number,
        number,
      ],
      simulationRepulsion: c.simulationRepulsion,
      simulationRepulsionTheta: c.simulationRepulsionTheta,
      renderHoveredPointRing: true,
      hoveredPointRingColor: c.hoveredPointRingColor,
      focusedPointRingColor: GRAPH_CONFIG.colors.scraping,
      focusedPointIndex: (() => {
        const index = scrapeNodeIndex(nodesRef.current)
        return index >= 0 ? index : undefined
      })(),
      curvedLinks: false,
    }
  }

  useImperativeHandle(ref, () => ({
    clearSelection: () => {
      graphInstanceRef.current?.unselectPoints()
      highlightedIndicesRef.current = null
      scheduleLabelRefresh()
    },
    fitView: () => {
      graphInstanceRef.current?.fitView(400, viewRef.current.cosmos.fitViewPadding)
    },
    restartLayout: () => {
      positionsByIdRef.current = new Map()
      clearGraphLayoutSession()
    },
    resume: () => {
      const g = graphInstanceRef.current
      if (!g) return
      try {
        g.render()
      } catch {
        // ignore
      }
      scheduleLabelRefresh()
    },
    persistLayout: () => {
      captureLivePositions()
      writeGraphPositions(positionsByIdRef.current, true)
    },
  }))

  useEffect(() => {
    const div = graphRef.current
    if (!div || nodesRef.current.length === 0) return
    if (layoutEpoch !== lastEpochRef.current) {
      positionsByIdRef.current = new Map()
      lastEpochRef.current = layoutEpoch
    }

    const fullNodes = latestNodesRef.current
    const fullEdges = latestEdgesRef.current
    const nextPartition = partitionLayoutGraph(fullNodes, fullEdges)
    const useSatellite = shouldSatelliteMessages(nextPartition, fullNodes.length, fullEdges.length)
    satelliteRef.current = useSatellite
    const simNodes = useSatellite ? nextPartition.peers : fullNodes
    const simEdges = useSatellite ? nextPartition.peerEdges : fullEdges
    nodesRef.current = simNodes
    edgesRef.current = simEdges

    const cosmosData = toCosmosData(simNodes, simEdges, positionsByIdRef.current, viewRef.current)
    neighbourLookupRef.current = neighbourLookupFromLinks(cosmosData.links)
    highlightedIndicesRef.current = null
    appliedNodesRef.current = simNodes
    appliedEdgesRef.current = simEdges
    pointIdToIndexRef.current = cosmosData.pointIdToIndex
    appliedTopologyRef.current = graphStructureKey(fullNodes, fullEdges)
    appliedPeerKeyRef.current = graphStructureKey(nextPartition.peers, nextPartition.peerEdges)
    attachedRef.current = !useSatellite

    const c = viewRef.current.cosmos
    const layout = viewRef.current.layout
    const peerIds = nextPartition.peers.map((node) => node.id)
    const peerHits = peerIds.reduce((n, id) => n + (positionsByIdRef.current.has(id) ? 1 : 0), 0)
    const allIds = fullNodes.map((node) => node.id)
    const allHits = allIds.reduce((n, id) => n + (positionsByIdRef.current.has(id) ? 1 : 0), 0)
    const restoreSettled = useSatellite
      ? peerIds.length > 0 && peerHits / peerIds.length >= 0.6
      : allIds.length > 0 && allHits / allIds.length >= 0.6
    let settled = restoreSettled
    let framed = restoreSettled
    const fitNow = (duration = 0) => {
      graphInstanceRef.current?.fitView(duration, Math.max(0.16, c.fitViewPadding))
    }
    const settleLayout = (fitDuration = 0) => {
      if (satelliteRef.current) {
        attachSatellitesRef.current()
      } else {
        graphInstanceRef.current?.pause()
        captureLivePositions()
        attachedRef.current = true
      }
      settled = true
      if (!framed) {
        framed = true
        if (fitDuration > 0) fitNow(fitDuration)
      }
    }
    const g = new Graph(div, {
      ...cosmosConstructorConfig(viewRef.current),
      onPointClick: (index: number) => {
        highlightAndSelectRef.current(index)
      },
      onClick: (index: number | undefined) => {
        if (index !== undefined) {
          highlightAndSelectRef.current(index)
          return
        }
        graphInstanceRef.current?.unselectPoints()
        highlightedIndicesRef.current = null
        scheduleLabelRefresh()
        onNodeClickRef.current?.(null)
      },
      onMouseMove: (index: number | undefined) => {
        hoveredIndexRef.current = index
      },
      onPointMouseOver: (index: number) => {
        hoveredIndexRef.current = index
      },
      onDragStart: () => {
        hideDraggedLabel()
      },
      onDrag: () => {
        if (simulatingRef.current) return
        const now = performance.now()
        if (now - lastGlowMsRef.current < 80) return
        lastGlowMsRef.current = now
        scheduleLabelRefresh()
      },
      onDragEnd: () => {
        showDraggedLabel()
        if (satelliteRef.current && attachedRef.current) syncSatellitePositionsRef.current()
      },
      onZoom: () => {
        scheduleLabelRefresh()
      },
      onSimulationTick: (alpha: number) => {
        simulatingRef.current = true
        const now = performance.now()
        if (now - lastGlowMsRef.current >= 250) {
          lastGlowMsRef.current = now
          scheduleLabelRefresh()
        }
        if (alpha <= c.simulationStopAlpha) {
          simulatingRef.current = false
          settleLayout(400)
        }
      },
      onSimulationEnd: () => {
        simulatingRef.current = false
        scheduleLabelRefresh()
        settleLayout(400)
      },
    })

    graphInstanceRef.current = g
    skipPhysicsRef.current = true
    skipDataRef.current = true
    applyCosmosBuffers(g, cosmosData)
    g.render()
    applyScrapeFocus(g, simNodes)
    restoreHighlightRef.current()
    fitNow(0)
    if (restoreSettled) {
      simulatingRef.current = false
      if (useSatellite) attachSatellitesRef.current()
      else captureLivePositions()
      window.requestAnimationFrame(() => {
        fitNow(0)
        scheduleLabelRefresh()
      })
    } else {
      simulatingRef.current = true
      attachedRef.current = !useSatellite
      g.start(layout.simulationStartAlpha)
    }
    scheduleLabelRefresh()

    return () => {
      if (labelRafRef.current != null) {
        window.cancelAnimationFrame(labelRafRef.current)
        labelRafRef.current = null
      }
      if (settled) {
        try {
          const live = g.getPointPositions?.() as ArrayLike<number> | undefined
          const applied = appliedNodesRef.current
          if (live && applied.length > 0 && live.length >= applied.length * 2) {
            emitPositions(capturePositionsById(applied, live))
          }
        } catch {
          // ignore — instance may already be torn down
        }
      }
      graphInstanceRef.current = null
      g.destroy()
      setLabels([])
      setScrapeGlow(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remountKey])

  useEffect(() => {
    const g = graphInstanceRef.current
    if (!g || ordered.length === 0) return
    if (skipPhysicsRef.current) {
      skipPhysicsRef.current = false
      return
    }
    const c = viewRef.current.cosmos
    g.setConfig({
      simulationFriction: c.simulationFriction,
      simulationDecay: c.simulationDecay,
      simulationCenter: c.simulationCenter,
      simulationGravity: c.simulationGravity,
      simulationLinkSpring: c.simulationLinkSpring,
      simulationLinkDistance: c.simulationLinkDistance,
      simulationLinkDistRandomVariationRange: [...c.simulationLinkDistRandomVariationRange] as [
        number,
        number,
      ],
      simulationRepulsion: c.simulationRepulsion,
      simulationRepulsionTheta: c.simulationRepulsionTheta,
      linkDefaultWidth: c.linkDefaultWidth,
      linkWidthScale: c.linkWidthScale,
      linkColor: c.linkColor,
      linkOpacity: c.linkOpacity,
      linkVisibilityDistanceRange: [...c.linkVisibilityDistanceRange] as [number, number],
      linkVisibilityMinTransparency: c.linkVisibilityMinTransparency,
      scaleLinksOnZoom: true,
    })
    simulatingRef.current = true
    beginPeerSimulationRef.current(0.28)
    scheduleLabelRefresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [physicsKey, remountKey])

  useEffect(() => {
    const g = graphInstanceRef.current
    if (!g || ordered.length === 0) return
    if (skipDataRef.current) {
      skipDataRef.current = false
      return
    }

    const grew = topologyKey !== appliedTopologyRef.current
    const peersChanged = peerTopologyKey !== appliedPeerKeyRef.current
    if (grew || peersChanged) captureLivePositions()

    if (satellite) {
      if (peersChanged) {
        appliedPeerKeyRef.current = peerTopologyKey
        beginPeerSimulationRef.current(0.16)
        scheduleLabelRefresh()
        return
      }
      if (simulatingRef.current && !attachedRef.current) {
        const peerData = toCosmosData(
          partition.peers,
          partition.peerEdges,
          positionsByIdRef.current,
          viewRef.current,
        )
        g.setPointColors(peerData.pointColors)
        g.setPointSizes(peerData.pointSizes)
        g.setLinkWidths(peerData.linkWidths)
        applyLinkColors(g, peerData.linkColors)
        applyScrapeFocus(g, partition.peers)
        g.render()
        scheduleLabelRefresh()
        return
      }
      if (grew || !attachedRef.current) {
        attachSatellitesRef.current()
      } else {
        const cosmosData = toCosmosData(ordered, edges, positionsByIdRef.current, viewRef.current)
        g.setPointColors(cosmosData.pointColors)
        g.setPointSizes(cosmosData.pointSizes)
        g.setLinkWidths(cosmosData.linkWidths)
        applyLinkColors(g, cosmosData.linkColors)
        appliedNodesRef.current = ordered
        appliedEdgesRef.current = edges
        pointIdToIndexRef.current = cosmosData.pointIdToIndex
        applyScrapeFocus(g, ordered)
        g.render()
      }
      restoreHighlightRef.current()
      scheduleLabelRefresh()
      return
    }

    const cosmosData = toCosmosData(ordered, edges, positionsByIdRef.current, viewRef.current)
    if (grew) {
      g.setPointPositions(cosmosData.pointPositions)
      g.setLinks(cosmosData.links)
      neighbourLookupRef.current = neighbourLookupFromLinks(cosmosData.links)
      appliedTopologyRef.current = topologyKey
    }
    g.setPointColors(cosmosData.pointColors)
    g.setPointSizes(cosmosData.pointSizes)
    g.setLinkWidths(cosmosData.linkWidths)
    applyLinkColors(g, cosmosData.linkColors)
    appliedNodesRef.current = ordered
    appliedEdgesRef.current = edges
    pointIdToIndexRef.current = cosmosData.pointIdToIndex
    nodesRef.current = ordered
    edgesRef.current = edges
    applyScrapeFocus(g, ordered)
    g.render()
    if (grew) {
      simulatingRef.current = true
      g.start(0.16)
    }
    restoreHighlightRef.current()
    scheduleLabelRefresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topologyKey, peerTopologyKey, appearanceKey, remountKey])

  useEffect(() => {
    restoreHighlightRef.current()
  }, [selectedId, topologyKey, remountKey])

  useEffect(() => {
    scheduleLabelRefresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.labels, appearanceKey, remountKey])

  if (nodes.length === 0) return null

  return (
    <div
      ref={wrapRef}
      className={s.wrap}
      style={{
        ['--graph-scraped-color' as string]: GRAPH_CONFIG.colors.scraped,
        ['--graph-scraping-color' as string]: GRAPH_CONFIG.colors.scraping,
      }}
    >
      <div ref={graphRef} className={s.canvas} />
      {scrapeGlow ? (
        <div
          className={s.scrapeGlowWrap}
          style={{ transform: `translate(${scrapeGlow.x}px, ${scrapeGlow.y}px)` }}
          aria-hidden
        >
          <span className={s.scrapeGlow} />
        </div>
      ) : null}
      <div className={s.labels} aria-hidden>
        {labels.map((label) => (
          <span
            key={label.id}
            className={`${s.label}${label.scraping ? ` ${s.labelScraping}` : label.scraped ? ` ${s.labelScraped}` : ''}`}
            style={{
              transform: `translate(calc(${label.x}px - 50%), ${label.y}px)`,
              opacity: label.opacity,
            }}
            title={label.fullText}
          >
            {label.text}
          </span>
        ))}
      </div>
    </div>
  )
})

export default CosmosGraph

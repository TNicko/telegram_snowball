import type { ForwardGraphEdge, ForwardGraphNode } from './api'
import {
  DEFAULT_GRAPH_VIEW,
  GRAPH_CONFIG,
  colorForEdge,
  colorForNode,
  sizeForNode,
  type GraphViewConfig,
} from './graphConfig'
import { edgeKind, isMessageNode } from './graphLayers'

export type CosmosGraphData = {
  pointPositions: Float32Array
  pointColors: Float32Array
  pointSizes: Float32Array
  links: Float32Array
  linkWidths: Float32Array
  linkColors: Float32Array
  pointIdToIndex: Map<string, number>
  structureKey: string
}

const rgbaCache = new Map<string, [number, number, number, number]>()

function hexToRgba01(hex: string): [number, number, number, number] {
  const hit = rgbaCache.get(hex)
  if (hit) return hit
  const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i)
  const rgba: [number, number, number, number] = m
    ? [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255, 1]
    : [...GRAPH_CONFIG.colors.fallbackRgba]
  rgbaCache.set(hex, rgba)
  return rgba
}

function clampCoord(value: number, spaceSize: number, pad: number): number {
  return Math.min(spaceSize - pad, Math.max(pad, value))
}

function placeFromCenter(
  nodes: ForwardGraphNode[],
  view: GraphViewConfig,
  placed: Map<string, [number, number]>,
): void {
  const spaceSize = view.layout.spaceSize
  const center = spaceSize / 2
  const pad = spaceSize * 0.04
  const disk = spaceSize * Math.max(0.004, view.layout.centerJitterFraction)
  const golden = Math.PI * (3 - Math.sqrt(5))
  const pending = nodes.filter((node) => !placed.has(node.id))
  const n = Math.max(1, pending.length)
  pending.forEach((node, index) => {
    const radius = disk * Math.sqrt((index + 1) / n)
    const angle = index * golden
    placed.set(node.id, [
      clampCoord(center + radius * Math.cos(angle), spaceSize, pad),
      clampCoord(center + radius * Math.sin(angle), spaceSize, pad),
    ])
  })
}

function computeInitialPositions(
  nodes: ForwardGraphNode[],
  edges: ForwardGraphEdge[],
  view: GraphViewConfig,
  previousPositions?: Map<string, [number, number]> | null,
): Map<string, [number, number]> {
  const placed = new Map<string, [number, number]>()
  const known = new Set(nodes.map((node) => node.id))
  if (previousPositions) {
    for (const [id, pos] of previousPositions) {
      if (known.has(id)) placed.set(id, pos)
    }
  }

  const adj = new Map<string, string[]>()
  for (const node of nodes) adj.set(node.id, [])
  for (const edge of edges) {
    adj.get(edge.source)?.push(edge.target)
    adj.get(edge.target)?.push(edge.source)
  }

  const spaceSize = view.layout.spaceSize
  const pad = spaceSize * 0.04
  const ringRadius = view.cosmos.simulationLinkDistance * view.layout.hubLeafRingRadiusFactor

  // New crawl nodes spawn next to a neighbour that already has a position.
  let grew = true
  while (grew) {
    grew = false
    for (const node of nodes) {
      if (placed.has(node.id)) continue
      const anchors = (adj.get(node.id) ?? []).filter((id) => placed.has(id))
      if (!anchors.length) continue
      const hub = anchors[0]
      const [hx, hy] = placed.get(hub)!
      const siblings = (adj.get(hub) ?? []).filter((id) => placed.has(id) && id !== hub)
      const index = siblings.length
      const angle = (2 * Math.PI * index) / Math.max(6, siblings.length + 1)
      placed.set(node.id, [
        clampCoord(hx + ringRadius * Math.cos(angle), spaceSize, pad),
        clampCoord(hy + ringRadius * Math.sin(angle), spaceSize, pad),
      ])
      grew = true
    }
  }

  placeFromCenter(nodes, view, placed)
  return placed
}

/** Keep GPU point indices stable as crawl adds nodes (append-only). */
export function appendStableNodeOrder(
  nodes: ForwardGraphNode[],
  order: readonly string[],
): { ordered: ForwardGraphNode[]; addedCount: number; order: string[] } {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const ordered: ForwardGraphNode[] = []
  for (const id of order) {
    const node = byId.get(id)
    if (!node) continue
    ordered.push(node)
    byId.delete(id)
  }
  const added = [...byId.values()].sort((a, b) => a.id.localeCompare(b.id))
  ordered.push(...added)
  return { ordered, addedCount: added.length, order: ordered.map((node) => node.id) }
}

/** Identity of topology only — colours / sizes / scrape flags must not change this. */
export function graphStructureKey(nodes: ForwardGraphNode[], edges: ForwardGraphEdge[]): string {
  let hash = (nodes.length * 73856093) ^ (edges.length * 19349663)
  for (const node of nodes) {
    const id = node.id
    for (let i = 0; i < id.length; i++) hash = (hash * 33 + id.charCodeAt(i)) | 0
  }
  for (const edge of edges) {
    const source = edge.source
    const target = edge.target
    const kind = edgeKind(edge)
    for (let i = 0; i < source.length; i++) hash = (hash * 33 + source.charCodeAt(i)) | 0
    hash = (hash * 33 + 62) | 0
    for (let i = 0; i < kind.length; i++) hash = (hash * 33 + kind.charCodeAt(i)) | 0
    hash = (hash * 33 + 62) | 0
    for (let i = 0; i < target.length; i++) hash = (hash * 33 + target.charCodeAt(i)) | 0
  }
  return `${nodes.length}:${edges.length}:${hash}`
}

export function neighbourLookupFromLinks(links: Float32Array): Map<number, Set<number>> {
  const direct = new Map<number, Set<number>>()
  for (let i = 0; i < links.length; i += 2) {
    const a = links[i]
    const b = links[i + 1]
    if (!direct.has(a)) direct.set(a, new Set())
    if (!direct.has(b)) direct.set(b, new Set())
    direct.get(a)!.add(b)
    direct.get(b)!.add(a)
  }
  return direct
}

export function toCosmosData(
  nodes: ForwardGraphNode[],
  edges: ForwardGraphEdge[],
  previousPositions?: Map<string, [number, number]> | null,
  view: GraphViewConfig = DEFAULT_GRAPH_VIEW,
): CosmosGraphData {
  const spaceSize = view.layout.spaceSize
  const initialPositions = computeInitialPositions(nodes, edges, view, previousPositions)
  const n = nodes.length
  const pointPositions = new Float32Array(n * 2)
  const pointColors = new Float32Array(n * 4)
  const pointSizes = new Float32Array(n)
  const pointIdToIndex = new Map<string, number>()

  for (let index = 0; index < n; index++) {
    const node = nodes[index]
    pointIdToIndex.set(node.id, index)
    const pos = initialPositions.get(node.id)
    if (pos) {
      pointPositions[index * 2] = pos[0]
      pointPositions[index * 2 + 1] = pos[1]
    } else {
      const center = spaceSize / 2
      pointPositions[index * 2] = center
      pointPositions[index * 2 + 1] = center
    }
    const rgba = hexToRgba01(colorForNode(node, view.layers))
    const colorAt = index * 4
    pointColors[colorAt] = rgba[0]
    pointColors[colorAt + 1] = rgba[1]
    pointColors[colorAt + 2] = rgba[2]
    pointColors[colorAt + 3] = rgba[3]
    pointSizes[index] = sizeForNode(node, view.sizing)
  }

  const linkCount = edges.length
  const links = new Float32Array(linkCount * 2)
  const linkWidths = new Float32Array(linkCount)
  const linkColors = new Float32Array(linkCount * 4)
  const widthScale = view.cosmos.linkWidthScale
  let written = 0
  for (const edge of edges) {
    const si = pointIdToIndex.get(edge.source)
    const ti = pointIdToIndex.get(edge.target)
    if (si == null || ti == null) continue
    const kind = edgeKind(edge)
    const at = written
    links[at * 2] = si
    links[at * 2 + 1] = ti
    const peerEdge = kind === 'forward_from' || kind === 'forward_to'
    linkWidths[at] = peerEdge
      ? Math.max(0.38, Math.log1p(Math.max(0, edge.count)) * Math.max(0.28, widthScale))
      : Math.max(0.3, Math.max(0.28, widthScale) * 0.55)
    const color = hexToRgba01(colorForEdge(kind, view.cosmos.linkColor))
    const colorAt = at * 4
    linkColors[colorAt] = color[0]
    linkColors[colorAt + 1] = color[1]
    linkColors[colorAt + 2] = color[2]
    linkColors[colorAt + 3] = 1
    written += 1
  }

  return {
    pointPositions,
    pointColors,
    pointSizes,
    links: written === linkCount ? links : links.subarray(0, written * 2),
    linkWidths: written === linkCount ? linkWidths : linkWidths.subarray(0, written),
    linkColors: written === linkCount ? linkColors : linkColors.subarray(0, written * 4),
    pointIdToIndex,
    structureKey: graphStructureKey(nodes, edges),
  }
}

export type LayoutPartition = {
  peers: ForwardGraphNode[]
  messages: ForwardGraphNode[]
  peerEdges: ForwardGraphEdge[]
  messageEdges: ForwardGraphEdge[]
}

export function partitionLayoutGraph(
  nodes: ForwardGraphNode[],
  edges: ForwardGraphEdge[],
): LayoutPartition {
  const peers: ForwardGraphNode[] = []
  const messages: ForwardGraphNode[] = []
  for (const node of nodes) {
    if (isMessageNode(node)) messages.push(node)
    else peers.push(node)
  }
  const peerEdges: ForwardGraphEdge[] = []
  const messageEdges: ForwardGraphEdge[] = []
  for (const edge of edges) {
    const kind = edgeKind(edge)
    if (kind === 'sent_to' || kind === 'forwarded_from') messageEdges.push(edge)
    else peerEdges.push(edge)
  }
  return { peers, messages, peerEdges, messageEdges }
}

/** Full n-body on tens of thousands of message nodes is what makes the page hitch. */
export function shouldSatelliteMessages(
  partition: LayoutPartition,
  nodeCount: number,
  edgeCount: number,
): boolean {
  if (partition.messages.length === 0 || partition.peers.length === 0) return false
  return partition.messages.length >= 1_500 || nodeCount >= 8_000 || edgeCount >= 12_000
}

function hashAngle(id: string): number {
  let hash = 2166136261
  for (let i = 0; i < id.length; i++) hash = Math.imul(hash ^ id.charCodeAt(i), 16777619)
  return (hash >>> 0) / 4294967295
}

/**
 * Park each message on the chord between its origin and destination peers
 * (or in a small spiral around a single peer). Peers keep doing the force layout.
 */
export function placeMessageSatellites(
  partition: LayoutPartition,
  peerPositions: Map<string, [number, number]>,
  view: GraphViewConfig = DEFAULT_GRAPH_VIEW,
): Map<string, [number, number]> {
  const sentTo = new Map<string, string>()
  const forwardedFrom = new Map<string, string>()
  for (const edge of partition.messageEdges) {
    const kind = edgeKind(edge)
    if (kind === 'sent_to') sentTo.set(edge.source, edge.target)
    else if (kind === 'forwarded_from' && !forwardedFrom.has(edge.target)) {
      forwardedFrom.set(edge.target, edge.source)
    }
  }

  const pairCounts = new Map<string, number>()
  const pairSlot = new Map<string, number>()
  const ringCounts = new Map<string, number>()
  const anchors = new Map<string, { origin?: [number, number]; dest?: [number, number]; peerId: string }>()

  for (const node of partition.messages) {
    const destId = sentTo.get(node.id)
    const originId = forwardedFrom.get(node.id)
    const dest = destId ? peerPositions.get(destId) : undefined
    const origin = originId ? peerPositions.get(originId) : undefined
    if (origin && dest) {
      const key = `${originId}\0${destId}`
      pairCounts.set(key, (pairCounts.get(key) ?? 0) + 1)
      anchors.set(node.id, { origin, dest, peerId: destId ?? originId ?? '' })
    } else {
      const peerId = destId ?? originId
      const pos = dest ?? origin
      if (!peerId || !pos) continue
      ringCounts.set(peerId, (ringCounts.get(peerId) ?? 0) + 1)
      anchors.set(node.id, { origin: pos, dest: pos, peerId })
    }
  }

  const placed = new Map<string, [number, number]>()
  const spaceSize = view.layout.spaceSize
  const pad = spaceSize * 0.04
  const golden = Math.PI * (3 - Math.sqrt(5))

  for (const node of partition.messages) {
    const anchor = anchors.get(node.id)
    if (!anchor?.origin) continue
    if (anchor.dest && anchor.origin !== anchor.dest) {
      const destId = sentTo.get(node.id)
      const originId = forwardedFrom.get(node.id)
      const key = `${originId}\0${destId}`
      const total = Math.max(1, pairCounts.get(key) ?? 1)
      const slot = pairSlot.get(key) ?? 0
      pairSlot.set(key, slot + 1)
      const [ox, oy] = anchor.origin
      const [dx, dy] = anchor.dest
      const frac = total === 1 ? 0.5 : 0.28 + (0.44 * slot) / Math.max(1, total - 1)
      const mx = ox + (dx - ox) * frac
      const my = oy + (dy - oy) * frac
      const vx = dx - ox
      const vy = dy - oy
      const len = Math.hypot(vx, vy) || 1
      const side = (slot % 2 === 0 ? 1 : -1) * (3.5 + (Math.floor(slot / 2) % 10) * 2.4)
      placed.set(node.id, [
        clampCoord(mx + (-vy / len) * side, spaceSize, pad),
        clampCoord(my + (vx / len) * side, spaceSize, pad),
      ])
      continue
    }
    const peerId = anchor.peerId
    const slot = ringCounts.get(`#${peerId}`) ?? 0
    ringCounts.set(`#${peerId}`, slot + 1)
    const [hx, hy] = anchor.origin
    const radius = 16 + Math.sqrt(slot + 1) * 6.5
    const angle = slot * golden + hashAngle(node.id) * 0.4
    placed.set(node.id, [
      clampCoord(hx + radius * Math.cos(angle), spaceSize, pad),
      clampCoord(hy + radius * Math.sin(angle), spaceSize, pad),
    ])
  }
  return placed
}

export function capturePositionsById(
  nodes: ForwardGraphNode[],
  positions: Float32Array | ArrayLike<number>,
): Map<string, [number, number]> {
  const out = new Map<string, [number, number]>()
  for (let i = 0; i < nodes.length; i++) {
    const x = positions[i * 2]
    const y = positions[i * 2 + 1]
    if (typeof x === 'number' && typeof y === 'number') {
      out.set(nodes[i].id, [x, y])
    }
  }
  return out
}

export function physicsConfigKey(view: GraphViewConfig): string {
  const c = view.cosmos
  return [
    c.simulationFriction,
    c.simulationDecay,
    c.simulationCenter,
    c.simulationGravity,
    c.simulationLinkSpring,
    c.simulationLinkDistance,
    c.simulationRepulsion,
    c.simulationRepulsionTheta,
    c.simulationLinkDistRandomVariationRange[0],
    c.simulationLinkDistRandomVariationRange[1],
    c.linkDefaultWidth,
    c.linkWidthScale,
    c.linkOpacity,
    c.linkColor,
    c.linkVisibilityDistanceRange[0],
    c.linkVisibilityDistanceRange[1],
    c.linkVisibilityMinTransparency,
  ].join('|')
}

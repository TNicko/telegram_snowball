import type { ForwardGraphEdge, ForwardGraphNode, GraphEdgeKind } from './api'
import {
  DEFAULT_GRAPH_LAYERS,
  type GraphLayersConfig,
  type MediaFilterKey,
} from './graphConfig'

export function edgeKind(edge: ForwardGraphEdge): GraphEdgeKind {
  return edge.kind ?? 'forward_from'
}

export function mediaFilterKey(node: ForwardGraphNode): MediaFilterKey {
  return node.media_kind ?? 'none'
}

export function isSelfForwardMessage(nodeId: string, edges: ForwardGraphEdge[]): boolean {
  return selfForwardMessageIds(edges).has(nodeId)
}

/** Messages whose only forwarded-from peers are also their posted-in peers. O(edges). */
export function selfForwardMessageIds(edges: ForwardGraphEdge[]): Set<string> {
  const sentTo = new Map<string, Set<string>>()
  const forwardedFrom = new Map<string, Set<string>>()
  for (const edge of edges) {
    const kind = edgeKind(edge)
    if (kind === 'sent_to') {
      let peers = sentTo.get(edge.source)
      if (!peers) {
        peers = new Set()
        sentTo.set(edge.source, peers)
      }
      peers.add(edge.target)
    } else if (kind === 'forwarded_from') {
      let peers = forwardedFrom.get(edge.target)
      if (!peers) {
        peers = new Set()
        forwardedFrom.set(edge.target, peers)
      }
      peers.add(edge.source)
    }
  }
  const ids = new Set<string>()
  for (const [id, fromPeers] of forwardedFrom) {
    const toPeers = sentTo.get(id)
    if (!toPeers || toPeers.size === 0 || fromPeers.size === 0) continue
    let self = true
    for (const peer of fromPeers) {
      if (!toPeers.has(peer)) {
        self = false
        break
      }
    }
    if (self) ids.add(id)
  }
  return ids
}

export function isMessageNode(node: ForwardGraphNode): boolean {
  return node.kind === 'message'
}

export function isImageNode(node: ForwardGraphNode): boolean {
  return node.kind === 'image'
}

export function isPeerNode(node: ForwardGraphNode): boolean {
  return node.kind !== 'message' && node.kind !== 'image'
}

function expandEdges(edges: ForwardGraphEdge[], layers: GraphLayersConfig): ForwardGraphEdge[] {
  const out: ForwardGraphEdge[] = []
  for (const edge of edges) {
    const kind = edgeKind(edge)
    if (kind === 'forward_from') {
      if (layers.forwardFrom) out.push({ ...edge, kind: 'forward_from' })
      if (layers.forwardTo) {
        out.push({
          source: edge.target,
          target: edge.source,
          count: edge.count,
          kind: 'forward_to',
        })
      }
      continue
    }
    if (kind === 'forward_to' && layers.forwardTo) out.push({ ...edge, kind: 'forward_to' })
    else if (kind === 'sent_to' && (layers.sentTo ?? true)) out.push(edge)
    else if (kind === 'forwarded_from' && (layers.forwardedFrom ?? true)) out.push(edge)
    else if (kind === 'appeared_in' && (layers.appearedIn ?? true)) out.push(edge)
  }
  return out
}

function nodeVisible(node: ForwardGraphNode, layers: GraphLayersConfig): boolean {
  if (isImageNode(node)) return layers.sharedImages ?? false
  if (isMessageNode(node)) {
    if (!layers.forwardMessages) return false
    return layers.mediaFilter[mediaFilterKey(node)]
  }
  if (node.scraped || node.is_scraping) return layers.scrapedPeers
  return layers.unscrapedPeers
}

export function filterGraph(
  nodes: ForwardGraphNode[],
  edges: ForwardGraphEdge[],
  layers: GraphLayersConfig = DEFAULT_GRAPH_LAYERS,
): { nodes: ForwardGraphNode[]; edges: ForwardGraphEdge[] } {
  const hideSelfForwards = !(layers.selfForwards ?? false)
  const selfForwardIds = hideSelfForwards ? selfForwardMessageIds(edges) : new Set<string>()
  const visibleNodes = nodes.filter((node) => {
    if (hideSelfForwards && selfForwardIds.has(node.id)) return false
    return nodeVisible(node, layers)
  })
  const visibleIds = new Set(visibleNodes.map((node) => node.id))
  const visibleEdges = expandEdges(edges, layers).filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
  )
  const hasSent = new Set<string>()
  const hasForwardedFrom = new Set<string>()
  const hasAppearedIn = new Set<string>()
  for (const edge of visibleEdges) {
    const kind = edgeKind(edge)
    if (kind === 'sent_to') hasSent.add(edge.source)
    else if (kind === 'forwarded_from') hasForwardedFrom.add(edge.target)
    else if (kind === 'appeared_in') hasAppearedIn.add(edge.source)
  }
  const keptNodes = visibleNodes.filter((node) => {
    if (isImageNode(node)) return hasAppearedIn.has(node.id)
    if (!isMessageNode(node)) return true
    return hasSent.has(node.id) && hasForwardedFrom.has(node.id)
  })
  const keptIds = new Set(keptNodes.map((node) => node.id))
  return {
    nodes: keptNodes,
    edges: visibleEdges.filter((edge) => keptIds.has(edge.source) && keptIds.has(edge.target)),
  }
}

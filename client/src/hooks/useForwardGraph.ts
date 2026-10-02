import { useEffect, useMemo, useState } from 'react'
import {
  api,
  type ForwardGraphResponse,
  type ForwardGraphStats,
  type GraphForwardsParams,
  type SharedImageGraphStats,
} from '../lib/api'
import { mediaQueryParam } from '../lib/graphQuery'
import type { GraphLayersConfig } from '../lib/graphConfig'

let cachedPeers: ForwardGraphResponse | null = null
let peerFingerprint = ''
let cachedMessages: ForwardGraphResponse | null = null
let messageFingerprint = ''
let cachedStats: ForwardGraphStats | null = null
let statsFingerprint = ''
let cachedShared: ForwardGraphResponse | null = null
let sharedFingerprint = ''
let cachedSharedStats: SharedImageGraphStats | null = null
let sharedStatsFingerprint = ''

function mix(hash: number, value: string): number {
  let next = hash
  for (let i = 0; i < value.length; i++) next = (next * 33 + value.charCodeAt(i)) | 0
  return next
}

function graphFingerprint(data: ForwardGraphResponse, includeMessages: boolean): string {
  let hash = mix(
    2166136261,
    `${includeMessages ? 1 : 0}|${data.meta.node_count}|${data.meta.edge_count}|${data.meta.scraped_count}|${data.meta.message_count ?? 0}|${data.meta.scoped_message_total ?? 0}`,
  )
  for (const node of data.nodes) {
    hash = mix(hash, node.id)
    hash = mix(hash, node.kind ?? 'peer')
    hash = (hash * 33 + (node.scraped ? 1 : 0)) | 0
    hash = (hash * 33 + (node.is_scraping ? 2 : 0)) | 0
    hash = (hash * 33 + (node.degree | 0)) | 0
    hash = (hash * 33 + (node.forward_volume | 0)) | 0
    hash = mix(hash, node.media_kind ?? '')
  }
  for (const edge of data.edges) {
    hash = mix(hash, edge.source)
    hash = mix(hash, edge.kind ?? 'forward_from')
    hash = mix(hash, edge.target)
    hash = (hash * 33 + (edge.count | 0)) | 0
  }
  return `${data.nodes.length}:${data.edges.length}:${hash}`
}

function statsKey(data: ForwardGraphStats): string {
  return [
    data.peer_count,
    data.peer_edge_count,
    data.message_forward_count,
    data.scoped_message_count,
    data.band,
    data.scope.peer_id ?? '',
    data.scope.date_from ?? '',
    data.scope.date_to ?? '',
    (data.scope.media ?? []).join(','),
  ].join('|')
}

function mergeGraph(
  peers: ForwardGraphResponse | null,
  messages: ForwardGraphResponse | null,
): ForwardGraphResponse | null {
  if (!peers) return messages
  if (!messages) return peers
  const messageNodes = messages.nodes.filter((node) => node.kind === 'message')
  const messageEdges = messages.edges.filter(
    (edge) => edge.kind === 'sent_to' || edge.kind === 'forwarded_from',
  )
  const peerNodes = peers.nodes.filter((node) => node.kind !== 'message')
  const peerEdges = peers.edges.filter(
    (edge) => edge.kind !== 'sent_to' && edge.kind !== 'forwarded_from',
  )
  return {
    nodes: [...peerNodes, ...messageNodes],
    edges: [...peerEdges, ...messageEdges],
    meta: {
      ...peers.meta,
      ...messages.meta,
      node_count: peerNodes.length,
      edge_count: peerEdges.filter((edge) => (edge.kind ?? 'forward_from') === 'forward_from').length,
      scraped_count: peerNodes.filter((node) => node.scraped).length,
      message_count: messageNodes.length,
      messages_included: messages.meta.messages_included,
    },
  }
}

export type GraphLoadOptions = {
  live: boolean
  includeMessages: boolean
  includeSharedImages: boolean
  wantedSharedImages: boolean
  peerId: number | null
  dateFrom: string | null
  dateTo: string | null
  layers: GraphLayersConfig
}

export function useForwardGraph({
  live,
  includeMessages,
  includeSharedImages,
  wantedSharedImages,
  peerId,
  dateFrom,
  dateTo,
  layers,
}: GraphLoadOptions) {
  const media = mediaQueryParam(layers.mediaFilter)
  const query: GraphForwardsParams = useMemo(
    () => ({
      peerId,
      dateFrom,
      dateTo,
      media,
    }),
    [peerId, dateFrom, dateTo, media],
  )
  const queryKey = `${peerId ?? ''}|${dateFrom ?? ''}|${dateTo ?? ''}|${media ?? ''}`

  const [peers, setPeers] = useState<ForwardGraphResponse | null>(cachedPeers)
  const [messages, setMessages] = useState<ForwardGraphResponse | null>(
    cachedMessages != null && includeMessages ? cachedMessages : null,
  )
  const [shared, setShared] = useState<ForwardGraphResponse | null>(
    cachedShared != null && includeSharedImages ? cachedShared : null,
  )
  const [stats, setStats] = useState<ForwardGraphStats | null>(cachedStats)
  const [sharedStats, setSharedStats] = useState<SharedImageGraphStats | null>(cachedSharedStats)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(cachedPeers != null)
  const [messagesReady, setMessagesReady] = useState(!includeMessages || cachedMessages != null)
  const [imagesReady, setImagesReady] = useState(!includeSharedImages || cachedShared != null)

  useEffect(() => {
    if (includeSharedImages) return
    let cancelled = false
    const load = () => {
      void api
        .graphForwards()
        .then((res) => {
          if (cancelled) return
          const next = graphFingerprint(res, false)
          if (next !== peerFingerprint) {
            peerFingerprint = next
            cachedPeers = res
            setPeers(res)
          } else if (cachedPeers == null) {
            cachedPeers = res
            setPeers(res)
          }
          setReady(true)
          setError(null)
        })
        .catch((err: Error) => {
          if (cancelled) return
          setError(err.message || 'Could not load the forward graph')
          setReady(true)
        })
    }
    load()
    const timer = live ? window.setInterval(load, 2000) : null
    return () => {
      cancelled = true
      if (timer != null) window.clearInterval(timer)
    }
  }, [live, includeSharedImages])

  useEffect(() => {
    if (includeSharedImages) return
    let cancelled = false
    const load = () => {
      void api
        .graphForwardsStats(query)
        .then((res) => {
          if (cancelled) return
          const next = statsKey(res)
          if (next !== statsFingerprint) {
            statsFingerprint = next
            cachedStats = res
            setStats(res)
          } else if (cachedStats == null) {
            cachedStats = res
            setStats(res)
          }
        })
        .catch(() => {
          /* stats are advisory */
        })
    }
    load()
    const timer = live ? window.setInterval(load, 2000) : null
    return () => {
      cancelled = true
      if (timer != null) window.clearInterval(timer)
    }
  }, [live, query, includeSharedImages])

  useEffect(() => {
    if (includeSharedImages || !includeMessages) {
      cachedMessages = null
      messageFingerprint = ''
      setMessages(null)
      setMessagesReady(true)
      return
    }
    let cancelled = false
    setMessagesReady(false)
    const load = () => {
      void api
        .graphForwards({ ...query, messages: true })
        .then((res) => {
          if (cancelled) return
          const next = graphFingerprint(res, true)
          if (next !== messageFingerprint) {
            messageFingerprint = next
            cachedMessages = res
            setMessages(res)
          } else if (cachedMessages == null) {
            cachedMessages = res
            setMessages(res)
          }
          setMessagesReady(true)
          setError(null)
        })
        .catch((err: Error) => {
          if (cancelled) return
          setError(err.message || 'Could not load message forwards')
          setMessagesReady(true)
        })
    }
    load()
    const neighborhoodLive = live && peerId != null
    const timer = neighborhoodLive ? window.setInterval(load, 15_000) : null
    return () => {
      cancelled = true
      if (timer != null) window.clearInterval(timer)
    }
  }, [includeMessages, includeSharedImages, query, queryKey, live, peerId])

  const sharedQueryKey = `${peerId ?? ''}|${dateFrom ?? ''}|${dateTo ?? ''}`

  useEffect(() => {
    if (!includeSharedImages) {
      cachedShared = null
      sharedFingerprint = ''
      setShared(null)
      setImagesReady(true)
      return
    }
    let cancelled = false
    setImagesReady(false)
    const params = { peerId, dateFrom, dateTo }
    const load = () => {
      void api
        .graphSharedImages(params)
        .then((res) => {
          if (cancelled) return
          const next = graphFingerprint(res, false)
          if (next !== sharedFingerprint) {
            sharedFingerprint = next
            cachedShared = res
            setShared(res)
          } else if (cachedShared == null) {
            cachedShared = res
            setShared(res)
          }
          setImagesReady(true)
          setReady(true)
          setError(null)
        })
        .catch((err: Error) => {
          if (cancelled) return
          setError(err.message || 'Could not load shared images')
          setImagesReady(true)
          setReady(true)
        })
    }
    load()
    const neighborhoodLive = live && peerId != null
    const timer = neighborhoodLive ? window.setInterval(load, 15_000) : null
    return () => {
      cancelled = true
      if (timer != null) window.clearInterval(timer)
    }
  }, [includeSharedImages, sharedQueryKey, live, peerId, dateFrom, dateTo])

  useEffect(() => {
    if (!wantedSharedImages) return
    let cancelled = false
    const load = () => {
      void api
        .graphSharedImagesStats({ peerId, dateFrom, dateTo })
        .then((res) => {
          if (cancelled) return
          const next = [
            res.image_count,
            res.peer_count,
            res.edge_count,
            res.scoped_image_count,
            res.band,
            res.scope.peer_id ?? '',
            res.scope.date_from ?? '',
            res.scope.date_to ?? '',
          ].join('|')
          if (next !== sharedStatsFingerprint) {
            sharedStatsFingerprint = next
            cachedSharedStats = res
            setSharedStats(res)
          } else if (cachedSharedStats == null) {
            cachedSharedStats = res
            setSharedStats(res)
          }
        })
        .catch(() => {
          /* stats are advisory */
        })
    }
    load()
    const timer = live ? window.setInterval(load, 2000) : null
    return () => {
      cancelled = true
      if (timer != null) window.clearInterval(timer)
    }
  }, [wantedSharedImages, live, peerId, dateFrom, dateTo])

  const data = useMemo(
    () => (includeSharedImages ? shared : mergeGraph(peers, includeMessages ? messages : null)),
    [shared, peers, messages, includeMessages, includeSharedImages],
  )

  return {
    data,
    stats,
    sharedStats,
    error,
    ready: includeSharedImages ? imagesReady || shared != null || Boolean(error) : ready,
    messagesReady,
    imagesReady,
  }
}

import { useEffect, useMemo, useRef, useState } from 'react'
import type { DateRange } from 'react-day-picker'
import { Link } from 'react-router'
import { Pause, Play } from 'lucide-react'
import CosmosGraph, { type CosmosGraphHandle } from '../components/CosmosGraph'
import { DateRangeField } from '../components/DateRangeField'
import { GraphControls } from '../components/GraphControls'
import { GraphMessageInspector, GraphImageInspector } from '../components/GraphMessageInspector'
import { isLiveJob, jobCurrentPeerId } from '../components/HomeJobs'
import { LoadingText } from '../components/LoadingText'
import { PeerAvatar } from '../components/PeerAvatar'
import { SnowballConfigModal } from '../components/SnowballConfigModal'
import { StopSyncConfirm } from '../components/StopSyncConfirm'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { useForwardGraph } from '../hooks/useForwardGraph'
import { useSnowballJobs } from '../hooks/useSnowballJobs'
import { useAppStatus } from '../layout/statusContext'
import { api, type ForwardGraphNode, type ForwardGraphResponse, type Job } from '../lib/api'
import {
  DEFAULT_GRAPH_QUERY,
  GRAPH_CONFIG,
  GRAPH_LAYER_PRESETS,
  MEDIA_FILTER_LABELS,
  cloneGraphLayers,
  cloneGraphQuery,
  cloneGraphView,
  loadStoredGraphView,
  persistGraphView,
  type GraphViewConfig,
  type MediaFilterKey,
} from '../lib/graphConfig'
import { endOfDayIso, isoToDate, mediaQueryParam, startOfDayIso } from '../lib/graphQuery'
import { filterGraph, isImageNode, isMessageNode, isPeerNode, mediaFilterKey } from '../lib/graphLayers'
import { graphPeerAsPeer, peerTypeLabel } from '../lib/peer'
import s from './GraphPage.module.css'

const numberFmt = new Intl.NumberFormat()
const bytesFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${bytesFmt.format(bytes / (1024 * 1024))} MB`
}

function graphNodeName(node: ForwardGraphNode | null | undefined): string {
  if (!node) return '—'
  return node.label || node.username || node.id
}

function formatPeerList(peers: ForwardGraphNode[]): string {
  if (!peers.length) return '—'
  const names = peers.map((peer) => graphNodeName(peer))
  if (names.length <= 3) return names.join(', ')
  return `${names.slice(0, 3).join(', ')} +${names.length - 3}`
}

function countNewNodeIds(current: ForwardGraphResponse, next: ForwardGraphResponse): number {
  const have = new Set(current.nodes.map((node) => node.id))
  let count = 0
  for (const node of next.nodes) {
    if (!have.has(node.id)) count += 1
  }
  return count
}

function jobTouchesPeer(job: Job, peerId: number): boolean {
  return jobCurrentPeerId(job) === peerId || Number(job.params.seed_external_id) === peerId
}

function LegendItem({
  color,
  label,
  count,
  scraping = false,
}: {
  color: string
  label: string
  count: number
  scraping?: boolean
}) {
  return (
    <span className={s.legendItem}>
      <span
        className={`${s.swatch}${scraping ? ` ${s.swatchScraping}` : ''}`}
        style={{ background: color }}
      />
      {label} - {numberFmt.format(count)}
    </span>
  )
}

export default function GraphPage({ active = true }: { active?: boolean }) {
  const status = useAppStatus()
  const { jobs, setJobs } = useSnowballJobs()
  const { running: dialoguesRunning, stop: stopChatSync } = useDialogueSync()
  const live = jobs.some((job) => isLiveJob(job.status))
  const liveJob = jobs.find((job) => isLiveJob(job.status)) ?? null
  const [view, setView] = useState<GraphViewConfig>(() => loadStoredGraphView())
  const [selected, setSelected] = useState<ForwardGraphNode | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [budgetOpen, setBudgetOpen] = useState(false)
  const [messagesUnlocked, setMessagesUnlocked] = useState(false)
  const [imagesUnlocked, setImagesUnlocked] = useState(false)
  const [viewBeforeBudget, setViewBeforeBudget] = useState<GraphViewConfig | null>(null)
  const [budgetDates, setBudgetDates] = useState<DateRange | undefined>()
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pausedJob, setPausedJob] = useState<Job | null>(null)
  const [pendingSnowball, setPendingSnowball] = useState<Record<string, unknown> | null>(null)
  const graphRef = useRef<CosmosGraphHandle | null>(null)

  const currentScrapeId = liveJob ? jobCurrentPeerId(liveJob) : null
  const scopePeerId = selected && isPeerNode(selected) ? selected.external_id : null
  const dateFrom = view.query?.dateFrom ?? DEFAULT_GRAPH_QUERY.dateFrom
  const dateTo = view.query?.dateTo ?? DEFAULT_GRAPH_QUERY.dateTo
  const dateScoped = Boolean(dateFrom || dateTo)
  const scoped = scopePeerId != null || dateScoped
  const wantedMessages = view.layers.forwardMessages
  const wantedShared = view.layers.sharedImages ?? false
  const includeMessages = wantedMessages && !wantedShared && (dateScoped || messagesUnlocked)
  const includeSharedImages =
    wantedShared && (dateScoped || imagesUnlocked || scopePeerId != null)
  const gatingMessages = wantedMessages && !wantedShared && !includeMessages
  const gatingShared = wantedShared && !includeSharedImages

  const commitView = (next: GraphViewConfig) => {
    const turningOnMessages = !view.layers.forwardMessages && next.layers.forwardMessages
    const turningOnShared = !(view.layers.sharedImages ?? false) && (next.layers.sharedImages ?? false)
    if (turningOnMessages || turningOnShared) setViewBeforeBudget(cloneGraphView(view))
    if (view.layers.forwardMessages && !next.layers.forwardMessages) {
      setMessagesUnlocked(false)
    }
    if ((view.layers.sharedImages ?? false) && !(next.layers.sharedImages ?? false)) {
      setImagesUnlocked(false)
    }
    if (
      (view.layers.forwardMessages && !next.layers.forwardMessages) ||
      ((view.layers.sharedImages ?? false) && !(next.layers.sharedImages ?? false))
    ) {
      setViewBeforeBudget(null)
    }
    setView(next)
  }

  const { data, stats, sharedStats, error, ready, messagesReady, imagesReady } = useForwardGraph({
    live,
    includeMessages,
    includeSharedImages,
    wantedSharedImages: wantedShared,
    peerId: scopePeerId,
    dateFrom,
    dateTo,
    layers: view.layers,
  })

  // The poll keeps fetching. The canvas stays on the last snapshot until the user
  // loads new nodes, or until they change the query (dates, peer, messages, images).
  const graphQueryKey = [
    includeMessages ? 1 : 0,
    includeSharedImages ? 1 : 0,
    scopePeerId ?? '',
    dateFrom ?? '',
    dateTo ?? '',
    mediaQueryParam(view.layers.mediaFilter) ?? '',
  ].join('|')
  const [graphSnapshot, setGraphSnapshot] = useState<ForwardGraphResponse | null>(null)
  const snapshotQueryRef = useRef<string | null>(null)
  useEffect(() => {
    if (!data) return
    if (graphSnapshot == null) {
      snapshotQueryRef.current = graphQueryKey
      setGraphSnapshot(data)
      return
    }
    if (snapshotQueryRef.current !== graphQueryKey) {
      if (data === graphSnapshot) return
      snapshotQueryRef.current = graphQueryKey
      setGraphSnapshot(data)
      return
    }
    if (data === graphSnapshot) return
    if (countNewNodeIds(graphSnapshot, data) === 0) setGraphSnapshot(data)
  }, [data, graphQueryKey, graphSnapshot])
  const displayedGraph = graphSnapshot ?? data
  const pendingNewNodes = useMemo(() => {
    if (!data || !graphSnapshot) return 0
    if (snapshotQueryRef.current !== graphQueryKey) return 0
    if (data === graphSnapshot) return 0
    return countNewNodeIds(graphSnapshot, data)
  }, [data, graphSnapshot, graphQueryKey])
  const loadNewNodes = () => {
    if (!data) return
    snapshotQueryRef.current = graphQueryKey
    setGraphSnapshot(data)
  }

  useEffect(() => {
    persistGraphView(view)
  }, [view])

  useEffect(() => {
    if (!wantedMessages || wantedShared) {
      if (!wantedMessages) setMessagesUnlocked(false)
      if (!wantedMessages && !wantedShared) setBudgetOpen(false)
      return
    }
    if (dateScoped || messagesUnlocked) {
      setBudgetOpen(false)
      return
    }
    if (!stats) return
    const sliceCount = stats.scoped_message_count || stats.message_forward_count
    const sliceTooBig = sliceCount > 25_000
    if (stats.band === 'auto' && !sliceTooBig) {
      setMessagesUnlocked(true)
      setBudgetOpen(false)
      return
    }
    if (!budgetOpen) {
      setBudgetDates(
        dateFrom || dateTo
          ? { from: isoToDate(dateFrom), to: isoToDate(dateTo) }
          : undefined,
      )
      setBudgetOpen(true)
    }
  }, [
    wantedMessages,
    wantedShared,
    dateScoped,
    messagesUnlocked,
    stats,
    dateFrom,
    dateTo,
    budgetOpen,
  ])

  useEffect(() => {
    if (!wantedShared) {
      setImagesUnlocked(false)
      if (!wantedMessages) setBudgetOpen(false)
      return
    }
    if (dateScoped || imagesUnlocked || scopePeerId != null) {
      setBudgetOpen(false)
      return
    }
    if (!sharedStats) return
    const sliceTooBig = sharedStats.scoped_image_count > 25_000
    if (sharedStats.band === 'auto' && !sliceTooBig) {
      setImagesUnlocked(true)
      setBudgetOpen(false)
      return
    }
    if (!budgetOpen) {
      setBudgetDates(
        dateFrom || dateTo
          ? { from: isoToDate(dateFrom), to: isoToDate(dateTo) }
          : undefined,
      )
      setBudgetOpen(true)
    }
  }, [
    wantedShared,
    wantedMessages,
    dateScoped,
    imagesUnlocked,
    scopePeerId,
    sharedStats,
    dateFrom,
    dateTo,
    budgetOpen,
  ])

  useEffect(() => {
    if (!active) return
    const id = window.requestAnimationFrame(() => graphRef.current?.resume())
    return () => window.cancelAnimationFrame(id)
  }, [active])

  useEffect(() => {
    const save = () => graphRef.current?.persistLayout()
    window.addEventListener('pagehide', save)
    return () => {
      save()
      window.removeEventListener('pagehide', save)
    }
  }, [])

  const sourceNodes = displayedGraph?.nodes ?? []
  const sourceEdges = displayedGraph?.edges ?? []
  const sourceWithScrape = useMemo(() => {
    if (currentScrapeId == null) return sourceNodes
    return sourceNodes.map((node) => {
      const scraping = isPeerNode(node) && node.external_id === currentScrapeId
      if (Boolean(node.is_scraping) === scraping) return node
      return { ...node, is_scraping: scraping }
    })
  }, [sourceNodes, currentScrapeId])
  const canvasView = gatingMessages || gatingShared
    ? {
        ...view,
        layers:
          viewBeforeBudget?.layers ??
          cloneGraphLayers(
            GRAPH_LAYER_PRESETS.find((item) => item.id === 'peer-forwards')?.layers,
          ),
      }
    : view
  const { nodes, edges } = useMemo(
    () => filterGraph(sourceWithScrape, sourceEdges, canvasView.layers),
    [sourceWithScrape, sourceEdges, canvasView.layers],
  )
  const selectedId = selected?.id
  const selectedLive = useMemo(() => {
    if (!selectedId) return null
    return nodes.find((node) => node.id === selectedId) ?? sourceWithScrape.find((node) => node.id === selectedId) ?? null
  }, [nodes, sourceWithScrape, selectedId])
  const sentToPeer = useMemo(() => {
    if (!selectedLive || !isMessageNode(selectedLive)) return null
    const edge = sourceEdges.find((item) => item.source === selectedLive.id && item.kind === 'sent_to')
    if (!edge) return null
    return sourceNodes.find((node) => isPeerNode(node) && node.id === edge.target) ?? null
  }, [selectedLive, sourceEdges, sourceNodes])
  const forwardedFromPeers = useMemo(() => {
    if (!selectedLive || !isMessageNode(selectedLive)) return []
    const ids = sourceEdges
      .filter((item) => item.target === selectedLive.id && item.kind === 'forwarded_from')
      .map((item) => item.source)
    return ids
      .map((id) => sourceNodes.find((node) => isPeerNode(node) && node.id === id) ?? null)
      .filter((node): node is ForwardGraphNode => node != null)
  }, [selectedLive, sourceEdges, sourceNodes])
  const appearedInPeers = useMemo(() => {
    if (!selectedLive || !isImageNode(selectedLive)) return []
    const ids = sourceEdges
      .filter((item) => item.source === selectedLive.id && item.kind === 'appeared_in')
      .map((item) => item.target)
    return ids
      .map((id) => sourceNodes.find((node) => isPeerNode(node) && node.id === id) ?? null)
      .filter((node): node is ForwardGraphNode => node != null)
  }, [selectedLive, sourceEdges, sourceNodes])

  const hasData = sourceNodes.length > 0
  const emptyCatalog = ready && !hasData && !wantedShared
  const emptyShared = ready && wantedShared && includeSharedImages && imagesReady && !hasData && !error
  const filteredEmpty = hasData && nodes.length === 0
  const showGraph = nodes.length > 0
  const loadingMessages = wantedMessages && includeMessages && !messagesReady
  const loadingImages = wantedShared && includeSharedImages && !imagesReady
  const graphLoading =
    !error &&
    (loadingImages || loadingMessages || (!ready && !hasData))
  const loadingLabel = loadingImages
    ? 'Loading shared images'
    : loadingMessages
      ? 'Loading messages'
      : 'Loading graph'
  const messageCount = nodes.filter(isMessageNode).length
  const imageCount = nodes.filter(isImageNode).length
  const scrapingCount = nodes.filter((node) => isPeerNode(node) && node.is_scraping).length
  const scrapedCount = nodes.filter(
    (node) => isPeerNode(node) && node.scraped && !node.is_scraping,
  ).length
  const unscrapedCount = nodes.filter(
    (node) => isPeerNode(node) && !node.scraped && !node.is_scraping,
  ).length
  const selectedPeer = selectedLive && isPeerNode(selectedLive) ? selectedLive : null
  const scrapingOnGraph = scrapingCount > 0
  const scrapingThisPeer = Boolean(
    selectedPeer &&
      (selectedPeer.is_scraping || (currentScrapeId != null && currentScrapeId === selectedPeer.external_id)),
  )
  const seedIsThis = Boolean(
    selectedPeer && liveJob && Number(liveJob.params.seed_external_id) === selectedPeer.external_id,
  )
  const playbackJob = selectedPeer
    ? scrapingThisPeer && liveJob
      ? liveJob
      : pausedJob && jobTouchesPeer(pausedJob, selectedPeer.external_id)
        ? pausedJob
        : seedIsThis
          ? liveJob
          : null
    : null
  const canPause = Boolean(liveJob && (scrapingThisPeer || seedIsThis))
  const scrapeDetail =
    (selectedPeer?.scrape_detail && selectedPeer.scrape_detail.trim()) ||
    (scrapingThisPeer && typeof liveJob?.progress?.detail === 'string' ? liveJob.progress.detail : null)
  const imageReady = status?.models.image.ready ?? false
  const textReady = status?.models.text.ready ?? false

  const pauseJob = async (job: Job) => {
    setBusy(true)
    setActionError(null)
    try {
      const stopped = await api.cancelJob(job.id)
      setPausedJob(stopped)
      setJobs((current) => current.map((item) => (item.id === stopped.id ? stopped : item)))
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not pause job')
    } finally {
      setBusy(false)
    }
  }

  const startJob = async (params: Record<string, unknown>) => {
    if (dialoguesRunning) {
      setPendingSnowball(params)
      return
    }
    await launchJob(params)
  }

  const launchJob = async (params: Record<string, unknown>) => {
    setBusy(true)
    setActionError(null)
    try {
      if (dialoguesRunning) await stopChatSync()
      const job = await api.createJob('forward_snowball', params)
      setPausedJob(null)
      setModalOpen(false)
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not start scrape')
    } finally {
      setBusy(false)
    }
  }

  const openScrape = async () => {
    if (!selectedPeer || busy) return
    setBusy(true)
    setActionError(null)
    try {
      if (liveJob) {
        const stopped = await api.cancelJob(liveJob.id)
        setPausedJob(stopped)
        setJobs((current) => current.map((item) => (item.id === stopped.id ? stopped : item)))
      }
      setModalOpen(true)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not pause the active job')
    } finally {
      setBusy(false)
    }
  }

  const revertBudget = () => {
    const previous = viewBeforeBudget
    setBudgetOpen(false)
    setMessagesUnlocked(false)
    setImagesUnlocked(false)
    setBudgetDates(undefined)
    const peerPreset = GRAPH_LAYER_PRESETS.find((item) => item.id === 'peer-forwards')
    setView(
      previous ?? {
        ...view,
        layers: cloneGraphLayers(peerPreset?.layers),
      },
    )
    setViewBeforeBudget(null)
  }

  const applyBudgetDates = () => {
    if (!budgetDates?.from && !budgetDates?.to) return
    setView({
      ...view,
      query: cloneGraphQuery({
        ...(view.query ?? DEFAULT_GRAPH_QUERY),
        dateFrom: budgetDates.from ? startOfDayIso(budgetDates.from) : null,
        dateTo: budgetDates.to
          ? endOfDayIso(budgetDates.to)
          : budgetDates.from
            ? endOfDayIso(budgetDates.from)
            : null,
      }),
    })
    setBudgetOpen(false)
    setViewBeforeBudget(null)
  }

  return (
    <div className={s.root}>
      {showGraph ? (
        <CosmosGraph
          ref={graphRef}
          nodes={nodes}
          edges={edges}
          selectedId={selectedId}
          view={canvasView}
          onNodeClick={setSelected}
        />
      ) : null}

      {graphLoading ? (
        <div className={s.loadingStage} role="status" aria-live="polite">
          <span className={`spinner ${s.loadingSpinner}`} aria-hidden />
          <LoadingText>{loadingLabel}</LoadingText>
        </div>
      ) : null}

      {emptyCatalog && !graphLoading ? (
        <div className={s.empty}>
          <h1 className={s.title}>Begin crawling Telegram to build a graph</h1>
          <Link to="/" className={`btn btnPrimary ${s.action}`}>
            Go to Home
          </Link>
        </div>
      ) : null}

      {emptyShared && !graphLoading ? (
        <div className={s.empty}>
          <h1 className={s.title}>No images appear in more than one peer yet</h1>
        </div>
      ) : null}

      {filteredEmpty && !graphLoading ? (
        <div className={s.empty}>
          <h1 className={s.title}>No nodes match the current layer filters</h1>
        </div>
      ) : null}

      {error && !hasData && !graphLoading ? (
        <div className={s.empty}>
          <h1 className={s.title}>{error}</h1>
        </div>
      ) : null}

      {hasData && showGraph ? (
        <div className={s.hud}>
            <div className={s.legend}>
              {scrapingOnGraph ? (
                <LegendItem
                  color={GRAPH_CONFIG.colors.scraping}
                  label="Scraping"
                  count={scrapingCount}
                  scraping
                />
              ) : null}
              {canvasView.layers.scrapedPeers ? (
                <LegendItem
                  color={GRAPH_CONFIG.colors.scraped}
                  label="Scraped"
                  count={scrapedCount}
                />
              ) : null}
              {canvasView.layers.unscrapedPeers ? (
                <LegendItem
                  color={GRAPH_CONFIG.colors.unscraped}
                  label="Not scraped"
                  count={unscrapedCount}
                />
              ) : null}
              {canvasView.layers.forwardMessages ? (
                canvasView.layers.colorByMedia ? (
                  (Object.keys(GRAPH_CONFIG.colors.media) as MediaFilterKey[]).map((key) =>
                    canvasView.layers.mediaFilter[key] ? (
                      <LegendItem
                        key={key}
                        color={GRAPH_CONFIG.colors.media[key]}
                        label={MEDIA_FILTER_LABELS[key]}
                        count={nodes.filter((node) => isMessageNode(node) && mediaFilterKey(node) === key).length}
                      />
                    ) : null,
                  )
                ) : (
                  <LegendItem
                    color={GRAPH_CONFIG.colors.message}
                    label="Messages"
                    count={messageCount}
                  />
                )
              ) : null}
              {canvasView.layers.sharedImages ? (
                <LegendItem
                  color={GRAPH_CONFIG.colors.media.image}
                  label="Images"
                  count={imageCount}
                />
              ) : null}
              {(canvasView.layers.forwardMessages || canvasView.layers.sharedImages) &&
              scoped &&
              scopePeerId != null ? (
                <span className={s.live}>Peer</span>
              ) : null}
              {data?.meta.messages_truncated || data?.meta.images_truncated ? (
                <span className={s.live}>Capped</span>
              ) : null}
              {loadingMessages ? <span className={s.live}>Messages…</span> : null}
              {loadingImages ? <span className={s.live}>Images…</span> : null}
            </div>
          </div>
      ) : null}

      <GraphControls
        view={view}
        onChange={commitView}
        pendingNewNodes={pendingNewNodes}
        onLoadNewNodes={loadNewNodes}
        onFitView={() => graphRef.current?.fitView()}
      />

      {selectedLive && isImageNode(selectedLive) ? (
        <GraphImageInspector
          key={selectedLive.id}
          node={selectedLive}
          appearedIn={formatPeerList(appearedInPeers)}
          appearedInTitle={appearedInPeers.map((peer) => graphNodeName(peer)).join(', ') || undefined}
        />
      ) : null}

      {selectedLive && isMessageNode(selectedLive) ? (
        <GraphMessageInspector
          node={selectedLive}
          sentTo={graphNodeName(sentToPeer)}
          forwardedFrom={formatPeerList(forwardedFromPeers)}
          forwardedFromTitle={forwardedFromPeers.map((peer) => graphNodeName(peer)).join(', ') || undefined}
        />
      ) : null}

      {selectedPeer ? (
        <div className={s.inspector}>
          <div className={s.inspectorHead}>
            <PeerAvatar peer={graphPeerAsPeer(selectedPeer)} />
            <div className={s.inspectorHeadBody}>
              <p className={s.inspectorTitle}>
                <span className={s.inspectorTitleText}>
                  {selectedPeer.label || selectedPeer.username || selectedPeer.id}
                </span>
                {scrapingThisPeer ? (
                  <span className={`spinner ${s.scrapeSpinner}`} aria-label="Scraping" />
                ) : null}
              </p>
              <p className={s.inspectorMeta}>
                {peerTypeLabel(selectedPeer.peer_type)}
                {selectedPeer.username ? ` · @${selectedPeer.username.replace(/^@/, '')}` : ''}
              </p>
              {scrapingThisPeer && scrapeDetail ? (
                <p className={s.inspectorLive}>
                  <LoadingText>{scrapeDetail}</LoadingText>
                </p>
              ) : null}
            </div>
          </div>
          {actionError ? <p className={s.inspectorError}>{actionError}</p> : null}
          <dl className={s.inspectorStats}>
            <div>
              <dt>Status</dt>
              <dd>
                {scrapingThisPeer
                  ? 'Scraping'
                  : selectedPeer.scraped
                    ? 'Scraped'
                    : 'Not scraped'}
              </dd>
            </div>
            <div>
              <dt>{wantedShared ? 'Shared images' : 'Unique peers'}</dt>
              <dd>{numberFmt.format(selectedPeer.degree)}</dd>
            </div>
            <div>
              <dt>{wantedShared ? 'Image appearances' : 'Unique forwards'}</dt>
              <dd>{numberFmt.format(selectedPeer.forwards_unique)}</dd>
            </div>
            <div>
              <dt>{wantedShared ? 'Total appearances' : 'Total forwards'}</dt>
              <dd>{numberFmt.format(selectedPeer.forwards_total)}</dd>
            </div>
          </dl>
          <div className={s.inspectorBar}>
            <button
              type="button"
              className={s.scrapeBtn}
              disabled={busy}
              onClick={() => void openScrape()}
            >
              Scrape
            </button>
            <button
              type="button"
              className={s.inspectorIconBtn}
              disabled={busy || !canPause}
              aria-label="Pause"
              title="Pause"
              onClick={() => {
                if (liveJob && canPause) void pauseJob(liveJob)
              }}
            >
              <Pause size={16} strokeWidth={1.75} aria-hidden />
            </button>
            <button
              type="button"
              className={s.inspectorIconBtn}
              disabled={busy || liveJob != null || playbackJob == null || isLiveJob(playbackJob.status)}
              aria-label="Play"
              title="Play"
              onClick={() => {
                if (playbackJob && !isLiveJob(playbackJob.status)) void startJob(playbackJob.params)
              }}
            >
              <Play size={16} strokeWidth={1.75} aria-hidden />
            </button>
          </div>
        </div>
      ) : null}

      {modalOpen && selectedPeer ? (
        <SnowballConfigModal
          peer={graphPeerAsPeer(selectedPeer)}
          busy={busy}
          imageReady={imageReady}
          textReady={textReady}
          snowballChoice
          defaultSnowball={false}
          title="Scrape peer"
          startLabel="Start scrape"
          onClose={() => setModalOpen(false)}
          onStart={(params) => void startJob(params)}
        />
      ) : null}

      {budgetOpen && (wantedShared ? sharedStats : stats) ? (
        <div className="modalScrim" onClick={revertBudget}>
          <div
            className={`modal ${s.budgetModal}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="graph-budget-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="graph-budget-title" className={s.budgetTitle}>
              {wantedShared ? 'Shared image graph is too large' : 'Message graph is too large'}
            </h3>
            <p className={s.budgetCopy}>
              {wantedShared && sharedStats ? (
                <>
                  This catalog has {numberFmt.format(sharedStats.scoped_image_count)} images that
                  appear in more than one peer (~{numberFmt.format(sharedStats.estimated_nodes)}{' '}
                  nodes, {numberFmt.format(sharedStats.estimated_edges)} edges,{' '}
                  {formatBytes(sharedStats.bytes_estimate)}). Choose a date range to load a slice
                  {sharedStats.band === 'confirm' ? ', load everything,' : ''} or cancel to stay on
                  the previous preset. You can also cancel, click a peer, and try again.
                </>
              ) : stats ? (
                <>
                  This catalog has {numberFmt.format(stats.scoped_message_count)} message-forwards (~
                  {numberFmt.format(stats.estimated_nodes)} nodes,{' '}
                  {numberFmt.format(stats.estimated_edges)} edges, {formatBytes(stats.bytes_estimate)}
                  ). Choose a date range to load a slice
                  {stats.band === 'confirm' ? ', load everything,' : ''} or cancel to stay on the
                  previous preset. You can also cancel, click a peer, and try again.
                </>
              ) : null}
            </p>
            <p className={s.budgetLabel}>Date range</p>
            <DateRangeField value={budgetDates} onChange={setBudgetDates} popoverZIndex={90} />
            <div className={s.budgetActions}>
              <button type="button" className={s.budgetCancel} onClick={revertBudget}>
                Cancel
              </button>
              {wantedShared &&
              sharedStats?.band === 'confirm' &&
              (sharedStats.scoped_image_count || 0) <= 80_000 ? (
                <button
                  type="button"
                  className={s.budgetCancel}
                  onClick={() => {
                    setImagesUnlocked(true)
                    setBudgetOpen(false)
                    setViewBeforeBudget(null)
                  }}
                >
                  Load all
                </button>
              ) : null}
              {!wantedShared && stats?.band === 'confirm' && (stats.scoped_message_count || 0) <= 80_000 ? (
                <button
                  type="button"
                  className={s.budgetCancel}
                  onClick={() => {
                    setMessagesUnlocked(true)
                    setBudgetOpen(false)
                    setViewBeforeBudget(null)
                  }}
                >
                  Load all
                </button>
              ) : null}
              <button
                type="button"
                className="btn btnPrimary"
                disabled={!budgetDates?.from && !budgetDates?.to}
                onClick={applyBudgetDates}
              >
                Load range
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {pendingSnowball ? (
        <StopSyncConfirm
          busy={busy}
          onClose={() => setPendingSnowball(null)}
          onConfirm={() => {
            const params = pendingSnowball
            setPendingSnowball(null)
            if (params) void launchJob(params)
          }}
        />
      ) : null}
    </div>
  )
}

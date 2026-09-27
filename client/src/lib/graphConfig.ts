/**
 * Tunable catalog forward-graph visualisation.
 * Physics / sizing / labels can be changed live from Graph page controls.
 */

export const MEDIA_FILTER_KEYS = ['none', 'image', 'video', 'audio', 'gif', 'document'] as const
export type MediaFilterKey = (typeof MEDIA_FILTER_KEYS)[number]

export const MEDIA_FILTER_LABELS: Record<MediaFilterKey, string> = {
  none: 'None',
  image: 'Image',
  video: 'Video',
  audio: 'Audio',
  gif: 'GIF',
  document: 'Document',
}

export const GRAPH_EDGE_LAYER_LABELS = {
  forwardFrom: 'Forwards from',
  forwardTo: 'Forwards into',
  sentTo: 'Posted in',
  forwardedFrom: 'Forwarded by',
  appearedIn: 'Appeared in',
} as const

export const GRAPH_CONFIG = {
  colors: {
    /** Peers whose messages / forwards have been scraped. */
    scraped: '#75beff',
    /** Catalog peers that appear on the graph but have not been scraped yet. */
    unscraped: '#3d5a80',
    /** Live scrape target — bright lime, distinct from every other node color. */
    scraping: '#7dff6a',
    /** Forwarded-message nodes when color-by-media is off. */
    message: '#c5c9d0',
    media: {
      none: '#c5c9d0',
      image: '#e5484d',
      video: '#f5a05a',
      audio: '#c9a57a',
      gif: '#f0c83a',
      document: '#c9a57a',
    },
    edges: {
      forward_from: '#5c5d74',
      forward_to: '#7a6a90',
      sent_to: '#4f6a8a',
      forwarded_from: '#a78bfa',
      appeared_in: '#c45c64',
    },
    fallbackRgba: [0.55, 0.62, 0.78, 1] as [number, number, number, number],
  },

  layout: {
    spaceSize: 8192,
    spawnJitterMin: 0.497,
    spawnJitterMax: 0.503,
    /** Tight disk at the world centre — the force sim unfolds from here. */
    centerJitterFraction: 0.012,
    hubMinDegree: 4,
    hubLeafRingRadiusFactor: 1.55,
    simulationStartAlpha: 0.7,
  },

  sizing: {
    /** Unique neighbour count (unique forward peers). */
    degreeWeight: 1.2,
    /** Total forward volume on incident edges. */
    volumeWeight: 0.4,
    baseSize: 4.4,
    scoreScale: 0.7,
    maxSize: 16,
    messageSize: 2.2,
  },

  labels: {
    zoomAtMaxSize: 0.2,
    zoomAtMinSize: 8,
    sizeToZoomPower: 1.35,
    /** Zoom span over which a label fades in after crossing its threshold. */
    fadeSpan: 0.9,
    maxVisible: 400,
    maxChars: 18,
    offsetY: 5,
    viewportPaddingPx: 48,
    /** Hide a smaller label if another kept label is this close (px). */
    minGapPx: 36,
  },

  cosmos: {
    backgroundColor: '#0a0a0a',
    linkDefaultWidth: 0.26,
    linkWidthScale: 0.55,
    linkColor: '#58596e',
    linkOpacity: 0.48,
    linkVisibilityDistanceRange: [4000, 14000] as [number, number],
    linkVisibilityMinTransparency: 1,
    fitViewDelay: 0,
    fitViewPadding: 0.18,
    pointSize: 1.5,
    pointGreyoutColor: '#1a1d26',
    pointGreyoutOpacity: 1.0,
    linkGreyoutOpacity: 0.05,
    simulationFriction: 0.35,
    simulationDecay: 4800,
    simulationStopAlpha: 0.016,
    simulationCenter: 0.42,
    simulationGravity: 0.12,
    simulationLinkSpring: 0.089,
    simulationLinkDistance: 110,
    simulationLinkDistRandomVariationRange: [0.88, 1.42] as [number, number],
    simulationRepulsion: 3.5,
    simulationRepulsionTheta: 1.15,
    hoveredPointRingColor: '#888aaa',
  },
} as const

export type GraphConfig = typeof GRAPH_CONFIG

type Widen<T> = T extends number
  ? number
  : T extends string
    ? string
    : T extends boolean
      ? boolean
      : T extends readonly [infer A, infer B]
        ? [Widen<A>, Widen<B>]
        : T extends object
          ? { [K in keyof T]: Widen<T[K]> }
          : T

export type GraphLayersConfig = {
  scrapedPeers: boolean
  unscrapedPeers: boolean
  forwardMessages: boolean
  sharedImages: boolean
  selfForwards: boolean
  forwardFrom: boolean
  forwardTo: boolean
  sentTo: boolean
  forwardedFrom: boolean
  appearedIn: boolean
  colorByMedia: boolean
  mediaFilter: Record<MediaFilterKey, boolean>
}

export const DEFAULT_GRAPH_LAYERS: GraphLayersConfig = {
  scrapedPeers: true,
  unscrapedPeers: true,
  forwardMessages: false,
  sharedImages: false,
  selfForwards: false,
  forwardFrom: true,
  forwardTo: false,
  sentTo: true,
  forwardedFrom: true,
  appearedIn: true,
  colorByMedia: false,
  mediaFilter: {
    none: true,
    image: true,
    video: true,
    audio: true,
    gif: true,
    document: true,
  },
}

export type GraphQueryConfig = {
  dateFrom: string | null
  dateTo: string | null
}

export const DEFAULT_GRAPH_QUERY: GraphQueryConfig = {
  dateFrom: null,
  dateTo: null,
}

export function cloneGraphQuery(query: GraphQueryConfig = DEFAULT_GRAPH_QUERY): GraphQueryConfig {
  return {
    dateFrom: query.dateFrom ?? null,
    dateTo: query.dateTo ?? null,
  }
}

export type GraphViewConfig = {
  layout: Widen<GraphConfig['layout']>
  sizing: Widen<GraphConfig['sizing']>
  labels: Widen<GraphConfig['labels']>
  cosmos: Widen<GraphConfig['cosmos']>
  layers: GraphLayersConfig
  query: GraphQueryConfig
}

export function cloneGraphLayers(layers: GraphLayersConfig = DEFAULT_GRAPH_LAYERS): GraphLayersConfig {
  return {
    scrapedPeers: layers.scrapedPeers,
    unscrapedPeers: layers.unscrapedPeers,
    forwardMessages: layers.forwardMessages,
    sharedImages: layers.sharedImages ?? false,
    selfForwards: layers.selfForwards ?? false,
    forwardFrom: layers.forwardFrom,
    forwardTo: layers.forwardTo,
    sentTo: layers.sentTo,
    forwardedFrom: layers.forwardedFrom,
    appearedIn: layers.appearedIn ?? true,
    colorByMedia: layers.colorByMedia,
    mediaFilter: { ...layers.mediaFilter },
  }
}

export type GraphLayerPresetId = 'peer-forwards' | 'message-forwards' | 'shared-images'

export type GraphLayerPreset = {
  id: GraphLayerPresetId
  label: string
  description: string
  layers: GraphLayersConfig
}

export const GRAPH_LAYER_PRESETS: GraphLayerPreset[] = [
  {
    id: 'peer-forwards',
    label: 'Peer forward graph',
    description: 'Who forwards from whom across the catalog.',
    layers: cloneGraphLayers(),
  },
  {
    id: 'message-forwards',
    label: 'Message forward graph',
    description: 'Each forwarded message, where it was posted, and who forwarded it.',
    layers: cloneGraphLayers({
      ...DEFAULT_GRAPH_LAYERS,
      forwardMessages: true,
      forwardFrom: false,
      colorByMedia: true,
    }),
  },
  {
    id: 'shared-images',
    label: 'Shared image graph',
    description:
      'The same photo reused in two or more peers — including copies that were never forwarded.',
    layers: cloneGraphLayers({
      ...DEFAULT_GRAPH_LAYERS,
      sharedImages: true,
      forwardMessages: false,
      forwardFrom: false,
      forwardTo: false,
      sentTo: false,
      forwardedFrom: false,
      appearedIn: true,
      colorByMedia: false,
    }),
  },
]

function layerConfigsEqual(a: GraphLayersConfig, b: GraphLayersConfig): boolean {
  return (
    a.scrapedPeers === b.scrapedPeers &&
    a.unscrapedPeers === b.unscrapedPeers &&
    a.forwardMessages === b.forwardMessages &&
    (a.sharedImages ?? false) === (b.sharedImages ?? false) &&
    (a.selfForwards ?? false) === (b.selfForwards ?? false) &&
    a.forwardFrom === b.forwardFrom &&
    a.forwardTo === b.forwardTo &&
    (a.sentTo ?? true) === (b.sentTo ?? true) &&
    (a.forwardedFrom ?? true) === (b.forwardedFrom ?? true) &&
    (a.appearedIn ?? true) === (b.appearedIn ?? true) &&
    a.colorByMedia === b.colorByMedia &&
    MEDIA_FILTER_KEYS.every((key) => a.mediaFilter[key] === b.mediaFilter[key])
  )
}

export function matchingLayerPresetId(layers: GraphLayersConfig): GraphLayerPresetId | 'custom' {
  const current = cloneGraphLayers(layers)
  for (const preset of GRAPH_LAYER_PRESETS) {
    if (layerConfigsEqual(current, preset.layers)) return preset.id
  }
  return 'custom'
}

export const DEFAULT_GRAPH_VIEW: GraphViewConfig = {
  layout: { ...GRAPH_CONFIG.layout },
  sizing: { ...GRAPH_CONFIG.sizing },
  labels: { ...GRAPH_CONFIG.labels },
  cosmos: {
    ...GRAPH_CONFIG.cosmos,
    linkVisibilityDistanceRange: [...GRAPH_CONFIG.cosmos.linkVisibilityDistanceRange] as [
      number,
      number,
    ],
    simulationLinkDistRandomVariationRange: [
      ...GRAPH_CONFIG.cosmos.simulationLinkDistRandomVariationRange,
    ] as [number, number],
  },
  layers: cloneGraphLayers(),
  query: cloneGraphQuery(),
}

export function cloneGraphView(view: GraphViewConfig = DEFAULT_GRAPH_VIEW): GraphViewConfig {
  return {
    layout: { ...view.layout },
    sizing: { ...view.sizing },
    labels: { ...view.labels },
    cosmos: {
      ...view.cosmos,
      linkVisibilityDistanceRange: [...view.cosmos.linkVisibilityDistanceRange] as [number, number],
      simulationLinkDistRandomVariationRange: [
        ...view.cosmos.simulationLinkDistRandomVariationRange,
      ] as [number, number],
    },
    layers: cloneGraphLayers(view.layers ?? DEFAULT_GRAPH_LAYERS),
    query: cloneGraphQuery(view.query ?? DEFAULT_GRAPH_QUERY),
  }
}

const VIEW_STORAGE_KEY = 'snowball.graphView.v9'
const LEGACY_VIEW_STORAGE_KEYS = [
  'snowball.graphView.v8',
  'snowball.graphView.v7',
  'snowball.graphView.v6',
  'snowball.graphView.v5',
  'snowball.graphView.v4',
]
const PREVIOUS_DEFAULT_FRICTION = 0.3
const PREVIOUS_DEFAULT_LINK_SPRING = 0.02
const PREVIOUS_DEFAULT_BASE_SIZE = 1.4
const PREVIOUS_DEFAULT_DEGREE_WEIGHT = 1.0
const PREVIOUS_DEFAULT_SCORE_SCALE = 0.4
const PREVIOUS_DEFAULT_MAX_SIZE = 12
const PREVIOUS_DEFAULT_REPULSION_THETAS = new Set([0.15, 0.55])
const PREVIOUS_LINK_VISIBILITY: [number, number][] = [
  [40, 2500],
  [50, 280],
]
const PREVIOUS_LINK_WIDTH_SCALES = new Set([0.4, 1.1])
const PREVIOUS_LINK_DEFAULT_WIDTHS = new Set([0.18, 0.45])
const PREVIOUS_LINK_OPACITIES = new Set([0.75, 0.85])
const PREVIOUS_LINK_MIN_TRANSPARENCY = new Set([0.12, 0.55])
export const LINK_STYLE_REVISION = 2

function isPreviousLinkVisibility(stored: [number, number] | undefined): boolean {
  if (!stored) return true
  return PREVIOUS_LINK_VISIBILITY.some((item) => item[0] === stored[0] && item[1] === stored[1])
}

export function applyLinkVisibilityDefaults(view: GraphViewConfig): GraphViewConfig {
  const next = cloneGraphView(view)
  const c = view.cosmos
  if (isPreviousLinkVisibility(c.linkVisibilityDistanceRange)) {
    next.cosmos.linkVisibilityDistanceRange = [...GRAPH_CONFIG.cosmos.linkVisibilityDistanceRange] as [
      number,
      number,
    ]
  }
  if (c.linkWidthScale == null || PREVIOUS_LINK_WIDTH_SCALES.has(c.linkWidthScale)) {
    next.cosmos.linkWidthScale = GRAPH_CONFIG.cosmos.linkWidthScale
  }
  if (c.linkDefaultWidth == null || PREVIOUS_LINK_DEFAULT_WIDTHS.has(c.linkDefaultWidth)) {
    next.cosmos.linkDefaultWidth = GRAPH_CONFIG.cosmos.linkDefaultWidth
  }
  if (c.linkOpacity == null || PREVIOUS_LINK_OPACITIES.has(c.linkOpacity)) {
    next.cosmos.linkOpacity = GRAPH_CONFIG.cosmos.linkOpacity
  }
  if (
    c.linkVisibilityMinTransparency == null ||
    PREVIOUS_LINK_MIN_TRANSPARENCY.has(c.linkVisibilityMinTransparency)
  ) {
    next.cosmos.linkVisibilityMinTransparency = GRAPH_CONFIG.cosmos.linkVisibilityMinTransparency
  }
  return next
}

export function loadStoredGraphView(): GraphViewConfig {
  const base = cloneGraphView()
  try {
    const raw =
      localStorage.getItem(VIEW_STORAGE_KEY) ??
      LEGACY_VIEW_STORAGE_KEYS.reduce<string | null>(
        (found, key) => found ?? localStorage.getItem(key),
        null,
      )
    if (!raw) return base
    const parsed = JSON.parse(raw) as Partial<GraphViewConfig>
    const friction = parsed.cosmos?.simulationFriction
    const spring = parsed.cosmos?.simulationLinkSpring
    const storedBaseSize = parsed.sizing?.baseSize
    const storedDegreeWeight = parsed.sizing?.degreeWeight
    const storedScoreScale = parsed.sizing?.scoreScale
    const storedMaxSize = parsed.sizing?.maxSize
    return {
      layout: { ...base.layout, ...parsed.layout },
      sizing: {
        ...base.sizing,
        ...parsed.sizing,
        baseSize:
          storedBaseSize == null || storedBaseSize === PREVIOUS_DEFAULT_BASE_SIZE
            ? base.sizing.baseSize
            : storedBaseSize,
        degreeWeight:
          storedDegreeWeight == null || storedDegreeWeight === PREVIOUS_DEFAULT_DEGREE_WEIGHT
            ? base.sizing.degreeWeight
            : storedDegreeWeight,
        scoreScale:
          storedScoreScale == null || storedScoreScale === PREVIOUS_DEFAULT_SCORE_SCALE
            ? base.sizing.scoreScale
            : storedScoreScale,
        maxSize:
          storedMaxSize == null || storedMaxSize === PREVIOUS_DEFAULT_MAX_SIZE
            ? base.sizing.maxSize
            : storedMaxSize,
      },
      labels: { ...base.labels, ...parsed.labels },
      cosmos: {
        ...base.cosmos,
        ...parsed.cosmos,
        simulationFriction:
          friction == null || friction === PREVIOUS_DEFAULT_FRICTION
            ? base.cosmos.simulationFriction
            : friction,
        simulationLinkSpring:
          spring == null || spring === PREVIOUS_DEFAULT_LINK_SPRING
            ? base.cosmos.simulationLinkSpring
            : spring,
        simulationRepulsionTheta:
          parsed.cosmos?.simulationRepulsionTheta == null ||
          PREVIOUS_DEFAULT_REPULSION_THETAS.has(parsed.cosmos.simulationRepulsionTheta)
            ? base.cosmos.simulationRepulsionTheta
            : parsed.cosmos.simulationRepulsionTheta,
        linkVisibilityDistanceRange: isPreviousLinkVisibility(
          parsed.cosmos?.linkVisibilityDistanceRange as [number, number] | undefined,
        )
          ? base.cosmos.linkVisibilityDistanceRange
          : (parsed.cosmos?.linkVisibilityDistanceRange as [number, number]),
        linkWidthScale:
          parsed.cosmos?.linkWidthScale == null ||
          PREVIOUS_LINK_WIDTH_SCALES.has(parsed.cosmos.linkWidthScale)
            ? base.cosmos.linkWidthScale
            : parsed.cosmos.linkWidthScale,
        linkDefaultWidth:
          parsed.cosmos?.linkDefaultWidth == null ||
          PREVIOUS_LINK_DEFAULT_WIDTHS.has(parsed.cosmos.linkDefaultWidth)
            ? base.cosmos.linkDefaultWidth
            : parsed.cosmos.linkDefaultWidth,
        linkOpacity:
          parsed.cosmos?.linkOpacity == null ||
          PREVIOUS_LINK_OPACITIES.has(parsed.cosmos.linkOpacity)
            ? base.cosmos.linkOpacity
            : parsed.cosmos.linkOpacity,
        linkVisibilityMinTransparency:
          parsed.cosmos?.linkVisibilityMinTransparency == null ||
          PREVIOUS_LINK_MIN_TRANSPARENCY.has(parsed.cosmos.linkVisibilityMinTransparency)
            ? base.cosmos.linkVisibilityMinTransparency
            : parsed.cosmos.linkVisibilityMinTransparency,
        simulationLinkDistRandomVariationRange: (parsed.cosmos
          ?.simulationLinkDistRandomVariationRange ??
          base.cosmos.simulationLinkDistRandomVariationRange) as [number, number],
      },
      layers: cloneGraphLayers({
        ...base.layers,
        ...parsed.layers,
        sentTo:
          parsed.layers?.sentTo ??
          (parsed.layers as { sentIn?: boolean } | undefined)?.sentIn ??
          base.layers.sentTo,
        forwardedFrom:
          parsed.layers?.forwardedFrom ??
          (parsed.layers as { forwardedTo?: boolean } | undefined)?.forwardedTo ??
          base.layers.forwardedFrom,
        selfForwards: parsed.layers?.selfForwards ?? base.layers.selfForwards,
        sharedImages: parsed.layers?.sharedImages ?? base.layers.sharedImages,
        appearedIn: parsed.layers?.appearedIn ?? base.layers.appearedIn,
        mediaFilter: {
          ...base.layers.mediaFilter,
          ...parsed.layers?.mediaFilter,
        },
      }),
      query: cloneGraphQuery({
        ...base.query,
        ...parsed.query,
      }),
    }
  } catch {
    return base
  }
}

export function persistGraphView(view: GraphViewConfig) {
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify(view))
  } catch {
    /* ignore quota / private mode */
  }
}

export function colorForNode(
  node: {
    kind?: string
    scraped?: boolean
    is_scraping?: boolean
    stub?: boolean
    media_kind?: string | null
  },
  layers: GraphLayersConfig = DEFAULT_GRAPH_LAYERS,
): string {
  if (node.kind === 'image') return GRAPH_CONFIG.colors.media.image
  if (node.kind === 'message') {
    if (layers.colorByMedia) {
      const key = (node.media_kind ?? 'none') as MediaFilterKey
      return GRAPH_CONFIG.colors.media[key] ?? GRAPH_CONFIG.colors.message
    }
    return GRAPH_CONFIG.colors.message
  }
  if (node.is_scraping) return GRAPH_CONFIG.colors.scraping
  if (node.scraped) return GRAPH_CONFIG.colors.scraped
  return GRAPH_CONFIG.colors.unscraped
}

export function colorForEdge(kind: string, fallback: string = GRAPH_CONFIG.cosmos.linkColor): string {
  const colors = GRAPH_CONFIG.colors.edges
  if (kind === 'forward_from') return colors.forward_from
  if (kind === 'forward_to') return colors.forward_to
  if (kind === 'sent_to') return colors.sent_to
  if (kind === 'forwarded_from') return colors.forwarded_from
  if (kind === 'appeared_in') return colors.appeared_in
  return fallback
}

export function nodeImportance(
  degree: number,
  forwardVolume: number,
  sizing: GraphViewConfig['sizing'] = GRAPH_CONFIG.sizing,
): number {
  const { degreeWeight, volumeWeight } = sizing
  return (
    Math.sqrt(Math.max(0, degree)) * degreeWeight +
    Math.sqrt(Math.max(0, forwardVolume)) * volumeWeight
  )
}

export function sizeForNode(
  node: { kind?: string; degree: number; forward_volume: number; is_scraping?: boolean },
  sizing: GraphViewConfig['sizing'] = GRAPH_CONFIG.sizing,
): number {
  const messageSize = Math.max(0.6, sizing.messageSize ?? GRAPH_CONFIG.sizing.messageSize)
  if (node.kind === 'message') return messageSize
  if (node.kind === 'image') {
    const { scoreScale, maxSize } = sizing
    const minImage = Math.max(sizing.baseSize * 0.7, messageSize * 1.35)
    const score = nodeImportance(node.degree, node.forward_volume, sizing)
    return Math.min(maxSize, minImage + score * scoreScale)
  }
  const { scoreScale, maxSize } = sizing
  const minPeer = Math.max(sizing.baseSize, messageSize * 2)
  const score = nodeImportance(node.degree, node.forward_volume, sizing)
  const size = Math.min(maxSize, minPeer + score * scoreScale)
  if (node.is_scraping) return Math.min(maxSize * 1.25, size * 1.28)
  return size
}

export function labelZoomThreshold(
  size: number,
  view: Pick<GraphViewConfig, 'labels' | 'sizing'> = GRAPH_CONFIG,
): number {
  const { zoomAtMaxSize, zoomAtMinSize, sizeToZoomPower } = view.labels
  const { baseSize, maxSize } = view.sizing
  const span = maxSize - baseSize
  const clamped = Math.min(maxSize, Math.max(baseSize, size))
  const t = span <= 0 ? 0 : (maxSize - clamped) / span
  const curved = Math.pow(t, sizeToZoomPower)
  return Math.max(0, zoomAtMaxSize + (zoomAtMinSize - zoomAtMaxSize) * curved)
}

export function labelOpacityForZoom(
  size: number,
  zoom: number,
  view: Pick<GraphViewConfig, 'labels' | 'sizing'> = GRAPH_CONFIG,
): number {
  const threshold = labelZoomThreshold(size, view)
  const fadeSpan = Math.max(0.05, view.labels.fadeSpan)
  return Math.min(1, Math.max(0, (zoom - threshold) / fadeSpan))
}

export function truncateLabel(text: string, maxChars: number = GRAPH_CONFIG.labels.maxChars): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxChars) return trimmed
  if (maxChars <= 1) return '…'
  return `${trimmed.slice(0, maxChars - 1)}…`
}

export function titleForNode(node: {
  kind?: string
  stub?: boolean
  label?: string | null
  username?: string | null
  external_id?: number | string
  date?: string | null
}): string | null {
  if (node.kind === 'message') {
    if (!node.date) return null
    const parsed = Date.parse(node.date)
    if (Number.isNaN(parsed)) return null
    return new Date(parsed).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  }
  if (node.kind === 'image') {
    const title = node.label?.trim()
    return title ? `Shared · ${title}` : 'Shared image'
  }
  const title = node.label?.trim()
  if (title) return title
  const username = node.username?.trim()
  if (username) return username.startsWith('@') ? username : `@${username}`
  if (node.external_id != null) return String(node.external_id)
  return null
}

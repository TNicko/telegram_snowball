/**
 * Single place to tune the catalog forward-graph.
 *
 * - `colors` — node / edge / label palette (legend, Cosmograph points, CSS labels)
 * - `cosmograph` — @cosmograph/react camera, data accessors, label behaviour
 * - `cosmos` — force-layout physics (also live-editable from Graph → Physics)
 * - `sizing` / `labels` / `layout` — values copied into the live Graph view
 *
 * Graph page Physics sliders save a copy of `cosmos` in the browser.
 * Graph → Physics → Reset reloads the values from this file.
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

/** Optional force-layout overrides. Absent fields use the Cosmograph library default. */
export type CosmosOverrides = {
  backgroundColor?: string
  linkDefaultWidth?: number
  linkWidthScale?: number
  linkColor?: string
  linkOpacity?: number
  linkVisibilityDistanceRange?: [number, number]
  linkVisibilityMinTransparency?: number
  fitViewDelay?: number
  fitViewPadding?: number
  pointSize?: number
  /** Pixel size of every node when no per-node size is set. Library default is 4. */
  pointDefaultSize?: number
  pointGreyoutColor?: string
  pointGreyoutOpacity?: number
  linkGreyoutOpacity?: number
  simulationFriction?: number
  simulationDecay?: number
  simulationStopAlpha?: number
  simulationCenter?: number
  simulationGravity?: number
  simulationLinkSpring?: number
  simulationLinkDistance?: number
  simulationLinkDistRandomVariationRange?: [number, number]
  simulationRepulsion?: number
  simulationRepulsionTheta?: number
  /** Pulls points that share `group` toward each other. Library default is 0.1. */
  simulationCluster?: number
  hoveredPointRingColor?: string
  /** When true, nodes grow as you zoom in and shrink as you zoom out. */
  scalePointsOnZoom?: boolean
  /** When true, edges grow as you zoom in and shrink as you zoom out. */
  scaleLinksOnZoom?: boolean
}

export const GRAPH_CONFIG = {
  colors: {
    /** Scraped peer nodes + their Cosmograph labels. */
    scraped: '#75beff',
    /** Catalog peers not yet scraped. Labels mix this toward white so they stay readable. */
    unscraped: '#3d5a80',
    /** Live scrape target — bright lime, distinct from every other node color. */
    scraping: '#7dff6a',
    /** Forwarded-message nodes (and their labels) when color-by-media is off. */
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

  /**
   * Cosmograph library config (`<Cosmograph {...} />`).
   * Point/link colours are not set here — they come from `colors` via colorForNode / colorForEdge.
   */
  cosmograph: {
    /** Point object field used as the unique id. Must match link `source` / `target`. */
    pointIdBy: 'id',
    /** Point object field shown as the CSS label. */
    pointLabelBy: 'label',
    /** Point object field that already holds a CSS colour string. */
    pointColorBy: 'color',
    /** `'direct'` = use `pointColorBy` as-is (our scraped / unscraped / media hexes). */
    pointColorStrategy: 'direct' as const,
    /** Link object field for the source point id. */
    linkSourceBy: 'source',
    /** Link object field for the target point id. */
    linkTargetBy: 'target',
    /** Link object field that already holds a CSS colour string. */
    linkColorBy: 'color',
    /** `'direct'` = use `linkColorBy` as-is (from `colors.edges`). */
    linkColorStrategy: 'direct' as const,
    /**
     * Frame every node on first paint. When true, Cosmograph ignores a fixed start zoom.
     * Leave false if you want `initialZoomLevel` to control first paint.
     */
    fitViewOnInit: true,
    /**
     * First-paint zoom (higher = closer). The Cosmograph React wrapper does not apply this
     * itself — CosmosGraph calls `setZoomLevel` from this value after the WebGL graph is ready.
     */
		initialZoomLevel: 3,
    /** Show a CSS label while the cursor is over a point. */
    showHoveredPointLabel: true,
    /** Clicking a point selects it (and its neighbours, Cosmograph default). */
    selectPointOnClick: true as const,
    /** Clicking a label selects the same way as clicking the point. */
    selectPointOnLabelClick: true as const,
  },

  layout: {
    spaceSize: 8192,
    spawnJitterMin: 0.495,
    spawnJitterMax: 0.505,
    /** Tight disk at the world centre — the force sim unfolds from here. */
    centerJitterFraction: 0.012,
    hubMinDegree: 4,
    hubLeafRingRadiusFactor: 1.55,
    simulationStartAlpha: 0.7,
  },

  sizing: {
    /** Unique neighbour count (unique forward peers). */
    degreeWeight: 1.2,
    /** How strongly incident forward volume grows a peer. 0 keeps every peer at the base size. */
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

  /**
   * Force-layout and appearance overrides.
   * A commented-out field is left to the Cosmograph library default.
   * Uncomment a field to use the value here (Physics sliders can still change it live).
   */
  cosmos: {
    /** Canvas clear colour. */
    backgroundColor: '#0a0a0a',
    // linkDefaultWidth: 0.26,
    /** Edge thickness scale (Graph → Physics → Link width). */
    // linkWidthScale: 0.55,
    /** Fallback edge colour when the kind is unknown. */
    linkColor: '#58596e',
    // linkOpacity: 0.48,
    // linkVisibilityDistanceRange: [4000, 14000] as [number, number],
    // linkVisibilityMinTransparency: 1,
    // fitViewDelay: 0,
    /** Extra space around the cluster when Fit is clicked (0–1). */
    // fitViewPadding: 0.22,
    // pointSize: 1.5,
    /** Pixel size of every node at zoom 1. Library default is 4. Grows and shrinks with zoom. */
    pointDefaultSize: 8,
    /**
     * Leave false. True multiplies every node by the camera zoom, and WebGL then
     * clamps them all to one maximum sprite size, so volume differences vanish.
     * False keeps each node's screen size, so a hub stays larger than a leaf.
     */
    scalePointsOnZoom: false,
    /**
     * Leave unset for the library default. Edges thin out when zoomed out and
     * keep a fixed screen width when zoomed in. Set true to thicken them on zoom-in.
     */
    // scaleLinksOnZoom: true,
    pointGreyoutColor: '#1a1d26',
    // pointGreyoutOpacity: 1.0,
    // linkGreyoutOpacity: 0.05,
    /** Damping: higher keeps nodes moving longer (Graph → Physics → Friction). */
    // simulationFriction: 0.85,
    /** How long the layout runs before it freezes (Graph → Physics → Cooling). */
    // simulationDecay: 5000,
    // simulationStopAlpha: 0.016,
    /** Extra pull toward world centre (Graph → Physics → Center force). */
    // simulationCenter: 0,
    /** Pull toward the centre of the world (Graph → Physics → Gravity). */
    // simulationGravity: 0.02,
    /** How tightly connected nodes pull together (Graph → Physics → Link strength). 0 leaves edges slack. */
    simulationLinkSpring: 0.2,
    /**
     * Preferred edge length (Graph → Physics → Link distance). Library default is 20.
     * Raise this with node size so neighbours sit apart.
     */
    simulationLinkDistance: 1,
    // simulationLinkDistRandomVariationRange: [1, 1.2] as [number, number],
    /** How hard unconnected nodes push apart (Graph → Physics → Repulsion). */
		 simulationRepulsion: 0.02,
    // simulationRepulsionTheta: 1.15,
    /** Pulls same-kind nodes together (Graph → Physics → Cluster strength). Library default is 0.1. */
    simulationCluster: 0,
    /** Ring drawn around the hovered / selected point. */
    hoveredPointRingColor: '#888aaa',
  } satisfies CosmosOverrides,
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
          ? { -readonly [K in keyof T]: Widen<T[K]> }
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
  cosmos: CosmosOverrides
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

function copyRange(value: readonly [number, number] | undefined): [number, number] | undefined {
  return value ? [value[0], value[1]] : undefined
}

function copyCosmos(source: CosmosOverrides): CosmosOverrides {
  return {
    ...source,
    linkVisibilityDistanceRange: copyRange(source.linkVisibilityDistanceRange),
    simulationLinkDistRandomVariationRange: copyRange(source.simulationLinkDistRandomVariationRange),
  }
}

/** Saved slider values only stick for fields that are currently set in GRAPH_CONFIG.cosmos. */
function cosmosFromStorage(stored: CosmosOverrides | undefined): CosmosOverrides {
  const next = copyCosmos(GRAPH_CONFIG.cosmos)
  if (!stored) return next
  const allowed = new Set(Object.keys(GRAPH_CONFIG.cosmos))
  for (const key of Object.keys(stored) as (keyof CosmosOverrides)[]) {
    if (!allowed.has(key)) continue
    const value = stored[key]
    if (value == null) continue
    if (key === 'linkVisibilityDistanceRange' || key === 'simulationLinkDistRandomVariationRange') {
      const pair = value as [number, number]
      next[key] = [pair[0], pair[1]]
    } else {
      Object.assign(next, { [key]: value })
    }
  }
  return next
}

export const DEFAULT_GRAPH_VIEW: GraphViewConfig = {
  layout: { ...GRAPH_CONFIG.layout },
  sizing: { ...GRAPH_CONFIG.sizing },
  labels: { ...GRAPH_CONFIG.labels },
  cosmos: copyCosmos(GRAPH_CONFIG.cosmos),
  layers: cloneGraphLayers(),
  query: cloneGraphQuery(),
}

export function cloneGraphView(view: GraphViewConfig = DEFAULT_GRAPH_VIEW): GraphViewConfig {
  return {
    layout: { ...view.layout },
    sizing: { ...view.sizing },
    labels: { ...view.labels },
    cosmos: copyCosmos(view.cosmos),
    layers: cloneGraphLayers(view.layers ?? DEFAULT_GRAPH_LAYERS),
    query: cloneGraphQuery(view.query ?? DEFAULT_GRAPH_QUERY),
  }
}

const VIEW_STORAGE_KEY = 'snowball.graphView'

export function loadStoredGraphView(): GraphViewConfig {
  const base = cloneGraphView()
  try {
    const raw = localStorage.getItem(VIEW_STORAGE_KEY)
    if (!raw) return base
    const parsed = JSON.parse(raw) as Partial<GraphViewConfig>
    return {
      layout: { ...base.layout, ...parsed.layout },
      sizing: { ...base.sizing, ...parsed.sizing },
      labels: { ...base.labels, ...parsed.labels },
      cosmos: cosmosFromStorage(parsed.cosmos),
      layers: cloneGraphLayers({
        ...base.layers,
        ...parsed.layers,
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

/**
 * Screen-pixel size. Peers grow with incident forward volume (edges on both ends).
 * The biggest peer is several times `pointDefaultSize`; a volume of 1 stays near the floor.
 */
export function sizeForNode(
  node: { kind?: string; forward_volume?: number; is_scraping?: boolean },
  sizing: GraphViewConfig['sizing'] = GRAPH_CONFIG.sizing,
  defaultSize = GRAPH_CONFIG.cosmos.pointDefaultSize ?? 8,
  maxVolume = 1,
): number {
  const base = defaultSize > 0 ? defaultSize : 8
  if (node.kind === 'message' || node.kind === 'image') return Math.max(1, base * 0.28)
  // volumeWeight 0 keeps every peer at `base`. The default 0.4 uses the full span.
  const spread = Math.min(1, Math.max(0, sizing.volumeWeight) / 0.4)
  const floor = base * (1 - 0.7 * spread)
  const ceil = base * (1 + 1.6 * spread)
  const volume = Math.max(0, node.forward_volume ?? 0)
  const t = Math.log1p(volume) / Math.log1p(Math.max(1, maxVolume))
  let px = floor + (ceil - floor) * t
  if (node.is_scraping) px *= 1.2
  return px
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

export function colorForEdge(kind: string, fallback: string = GRAPH_CONFIG.cosmos.linkColor ?? '#58596e'): string {
  const colors = GRAPH_CONFIG.colors.edges
  if (kind === 'forward_from') return colors.forward_from
  if (kind === 'forward_to') return colors.forward_to
  if (kind === 'sent_to') return colors.sent_to
  if (kind === 'forwarded_from') return colors.forwarded_from
  if (kind === 'appeared_in') return colors.appeared_in
  return fallback
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

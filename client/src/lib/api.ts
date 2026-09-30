export type ModelSlot = 'image' | 'text'

export type ModelHealth = {
  id: string
  slot?: ModelSlot
  ready: boolean
  label: string
  title?: string
  license?: string | null
  default?: boolean
  recommended?: boolean
  download_gb?: number
  ram_gb?: number
  vram_gb?: number
  hardware?: string
  purpose?: string
  selected?: boolean
  group?: string | null
  group_label?: string | null
  multimodal?: boolean
}

export type ModelCatalog = {
  slots: Record<ModelSlot, ModelHealth>
  catalog: Record<ModelSlot, ModelHealth[]>
  copy: Record<ModelSlot, { title: string; blurb: string }>
  download?: {
    id: string
    status: string
    params: Record<string, unknown>
    progress?: Record<string, unknown> | null
    error?: string | null
  } | null
  queued?: boolean
  ready?: boolean
}

export type Account = {
  telegram_user_id: number
  phone: string | null
  username: string | null
  first_name: string | null
  last_name: string | null
  photo_path?: string | null
  photo_url?: string | null
  photo_media_kind?: 'image' | 'video' | null
}

export type AppStatus = {
  has_credentials: boolean
  has_session: boolean
  setup_complete: boolean
  setup_phone?: string | null
  account: Account | null
  models: {
    image: ModelHealth
    text: ModelHealth
  }
  active_job: Job | null
}

export type CatalogMessage = {
  id: string
  telegram_message_id: number
  date: string
  content: string | null
  from_external_id: number | null
  forwarded: boolean
  media_kind: 'image' | 'video' | 'gif' | 'audio' | 'document' | null
  peer: Peer
  score?: number | null
}

export type CatalogImagePeer = {
  peer: Peer
  appearances: number
  forwarded: number
}

export type GraphMediaKind = 'image' | 'video' | 'audio' | 'gif' | 'document'

export type ForwardGraphNode = {
  id: string
  kind?: 'peer' | 'message' | 'image'
  external_id: number
  peer_type: string
  label: string | null
  username: string | null
  photo_url?: string | null
  photo_media_kind?: 'image' | 'video' | null
  scraped: boolean
  is_scraping: boolean
  scrape_detail?: string | null
  degree: number
  forward_volume: number
  forwards_unique: number
  forwards_total: number
  forwarded?: boolean
  media_kind?: GraphMediaKind | null
  date?: string | null
  telegram_message_id?: number | null
  peer_external_id?: number | null
  origin_peer_id?: number | null
  origin_telegram_id?: number | null
  excerpt?: string | null
  stub?: boolean
  message_id?: string | null
  phash?: string | null
}

export type MessageMediaPreview = {
  kind: GraphMediaKind
  phash?: string | null
  file_url?: string | null
  size_bytes?: number | null
  size_label?: string | null
  mime_type?: string | null
  file_name?: string | null
  duration?: number | null
  width?: number | null
  height?: number | null
}

export type GraphMessageDetail = {
  id: string
  telegram_message_id: number
  date: string | null
  content: string | null
  media_kind: GraphMediaKind | null
  media: MessageMediaPreview | null
}

export type GraphEdgeKind = 'forward_from' | 'forward_to' | 'sent_to' | 'forwarded_from' | 'appeared_in'

export type ForwardGraphEdge = {
  source: string
  target: string
  count: number
  kind?: GraphEdgeKind
}

export type GraphBudgetBand = 'auto' | 'confirm' | 'block'

export type GraphScopeMeta = {
  peer_id: number | null
  date_from: string | null
  date_to: string | null
  media: string[] | null
  sample?: string
}

export type ForwardGraphResponse = {
  nodes: ForwardGraphNode[]
  edges: ForwardGraphEdge[]
  meta: {
    node_count: number
    edge_count: number
    scraped_count: number
    message_count?: number
    messages_included?: boolean
    messages_truncated?: boolean
    messages_omitted?: boolean
    omit_reason?: string | null
    message_forward_total?: number
    scoped_message_total?: number
    returned_message_count?: number
    image_count?: number
    images_included?: boolean
    images_truncated?: boolean
    images_omitted?: boolean
    scoped_image_total?: number
    returned_image_count?: number
    bytes_estimate?: number
    band?: GraphBudgetBand
    limit?: number
    scope?: GraphScopeMeta
  }
}

export type ForwardGraphStats = {
  peer_count: number
  peer_edge_count: number
  message_forward_count: number
  scoped_message_count: number
  estimated_nodes: number
  estimated_edges: number
  bytes_estimate: number
  band: GraphBudgetBand
  limit: number
  scope: GraphScopeMeta
}

export type SharedImageGraphStats = {
  peer_count: number
  image_count: number
  edge_count: number
  scoped_image_count: number
  estimated_nodes: number
  estimated_edges: number
  bytes_estimate: number
  band: GraphBudgetBand
  limit: number
  scope: GraphScopeMeta
}

export type GraphSharedImagesParams = {
  peerId?: number | null
  dateFrom?: string | null
  dateTo?: string | null
}

export function graphSharedImagesQuery(params?: GraphSharedImagesParams): string {
  const query = new URLSearchParams()
  if (params?.peerId != null && Number.isFinite(params.peerId) && params.peerId !== 0) {
    query.set('peer_id', String(params.peerId))
  }
  if (params?.dateFrom) query.set('date_from', params.dateFrom)
  if (params?.dateTo) query.set('date_to', params.dateTo)
  const text = query.toString()
  return text ? `?${text}` : ''
}

export type GraphForwardsParams = {
  messages?: boolean
  peerId?: number | null
  dateFrom?: string | null
  dateTo?: string | null
  media?: string | null
}

export function graphForwardsQuery(params?: GraphForwardsParams): string {
  const query = new URLSearchParams()
  if (params?.messages) query.set('messages', 'true')
  if (params?.peerId != null && Number.isFinite(params.peerId) && params.peerId !== 0) {
    query.set('peer_id', String(params.peerId))
  }
  if (params?.dateFrom) query.set('date_from', params.dateFrom)
  if (params?.dateTo) query.set('date_to', params.dateTo)
  if (params?.media) query.set('media', params.media)
  const text = query.toString()
  return text ? `?${text}` : ''
}

export type CatalogImage = {
  phash: string
  file_url: string
  appearances: number
  unique_peers: number
  last_seen_at: string | null
  refcount: number
  persisted: boolean
  peers: CatalogImagePeer[]
  score?: number | null
}

export type CatalogFile = {
  id: string
  file_url: string
  size_bytes: number | null
  size_label: string | null
  mime_type: string | null
  file_name: string | null
  appearances: number
  unique_peers: number
  last_seen_at: string | null
  persisted: boolean
  peers: CatalogImagePeer[]
}

export type CatalogStorageBucket = {
  count: number
  bytes: number
  bytes_label: string
}

export type CatalogStorageStats = {
  messages: CatalogStorageBucket
  images: CatalogStorageBucket
  hashed_images: CatalogStorageBucket
  videos: CatalogStorageBucket
}

export type CatalogVideo = {
  id: string
  file_url: string
  size_bytes: number | null
  size_label: string | null
  mime_type: string | null
  file_name: string | null
  duration: number | null
  width: number | null
  height: number | null
  appearances: number
  unique_peers: number
  last_seen_at: string | null
  persisted: boolean
  peers: CatalogImagePeer[]
}

export type Job = {
  id: string
  task_type: string
  status: string
  params: Record<string, unknown>
  progress: Record<string, unknown>
  error?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  seed_peer?: Peer | null
}

export type MediaBucket = {
  total: number
  downloaded: number
  hashed?: number
  unique?: number
}

export type CoverageWindow = {
  covered_after?: string | null
  covered_before?: string | null
  updated_at?: string | null
  fill?: number
}

export type CoverageLayer = {
  covered_after?: string | null
  covered_before?: string | null
  fill: number
}

export type PeerCoverage = {
  peer: Peer
  timeline: {
    start: string | null
    end: string
    first_message_id?: number | null
  }
  posts: CoverageWindow & { count: number }
  media_pass: (CoverageWindow & {
    videos_excluded?: boolean
    large_excluded?: boolean
    max_media_bytes?: number | null
  }) | null
  media_layers?: {
    image: CoverageLayer
    video: CoverageLayer
    audio: CoverageLayer
    gif: CoverageLayer
    document: CoverageLayer
  }
  forwards?: { fill: number }
  embeds: {
    text: { total: number; done: number } & CoverageLayer
    images: { total: number; done: number } & CoverageLayer
  }
}

export type RemainderLayer =
  | 'all'
  | 'posts'
  | 'image'
  | 'image_phash'
  | 'image_download'
  | 'video'
  | 'audio'
  | 'gif'
  | 'document'
  | 'embed_text'
  | 'embed_images'

export type Peer = {
  external_id: number
  peer_type: string
  title: string | null
  username: string | null
  about?: string | null
  participants_count?: number | null
  photo_path: string | null
  photo_url?: string | null
  photo_media_kind?: 'image' | 'video' | null
  is_scraping: boolean
  scrape_detail: string | null
  messages_scraped: number
  created_at: string
  updated_at: string
  has_fetch_coverage?: boolean
  has_media_coverage?: boolean
  posts?: number | null
  forwards_unique?: number | null
  forwards_total?: number | null
  media?: {
    image: MediaBucket | null
    video: MediaBucket | null
    audio: MediaBucket | null
    gif: MediaBucket | null
    document: MediaBucket | null
  }
  videos_excluded?: boolean
  large_excluded?: boolean
  max_media_bytes?: number | null
  embed_text?: boolean
  embed_images?: boolean
  scope_score?: number
  forward_score?: number
}

export type ScopeInput = {
  id: string
  kind: 'text' | 'file'
  text: string | null
  filename: string | null
  content_type: string | null
  model_id?: string | null
  created_at: string
  has_embedding?: boolean
}

export type ScopeState = {
  inputs: ScopeInput[]
  tau: number
  gamma: number
  alpha: number
  delta: number
  lambda_fwd: number
  version: number
  last_rerank_at: string | null
  needs_rescore?: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header)
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"(.*)"$/, '$1'))
    } catch {
      return star[1].trim()
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain ? plain[1] : null
}

export async function downloadExport(path: string, body: Record<string, unknown>): Promise<void> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const parsed = (await response.json()) as { detail?: string }
      if (parsed.detail) detail = parsed.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const blob = await response.blob()
  const name = filenameFromDisposition(response.headers.get('Content-Disposition')) || 'snowball-export'
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export const api = {
  status: () => request<AppStatus>('/api/status'),
  models: () => request<ModelCatalog>('/api/models'),
  selectModels: (body: Partial<Record<ModelSlot, string>>) =>
    request<ModelCatalog>('/api/models/selection', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  downloadModel: (model_id: string) =>
    request<ModelCatalog>('/api/models/download', {
      method: 'POST',
      body: JSON.stringify({ model_id }),
    }),
  saveCredentials: (api_id: number, api_hash: string) =>
    request('/api/setup/credentials', {
      method: 'PUT',
      body: JSON.stringify({ api_id, api_hash }),
    }),
  removeSession: () => request<{ ok: boolean }>('/api/setup/session', { method: 'DELETE' }),
  peers: () => request<{ peers: Peer[] }>('/api/peers'),
  catalogStats: () => request<CatalogStorageStats>('/api/catalog/stats'),
  jobs: () => request<{ jobs: Job[] }>('/api/jobs'),
  message: (id: string) => request<GraphMessageDetail>(`/api/messages/${id}`),
  lookupMessage: (origin_peer_id: number, origin_telegram_id: number) => {
    const query = new URLSearchParams({
      origin_peer_id: String(origin_peer_id),
      origin_telegram_id: String(origin_telegram_id),
    })
    return request<GraphMessageDetail>(`/api/messages/lookup?${query.toString()}`)
  },
  messages: (params?: { peer_external_id?: number; limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params?.peer_external_id != null) query.set('peer_external_id', String(params.peer_external_id))
    if (params?.limit != null) query.set('limit', String(params.limit))
    if (params?.offset != null) query.set('offset', String(params.offset))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<{ messages: CatalogMessage[]; total: number; limit: number; offset: number }>(
      `/api/messages${suffix}`,
    )
  },
  images: (params?: {
    peer_external_id?: number
    sort?: 'peers' | 'date'
    limit?: number
    offset?: number
  }) => {
    const query = new URLSearchParams()
    if (params?.peer_external_id != null) query.set('peer_external_id', String(params.peer_external_id))
    if (params?.sort) query.set('sort', params.sort)
    if (params?.limit != null) query.set('limit', String(params.limit))
    if (params?.offset != null) query.set('offset', String(params.offset))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<{ images: CatalogImage[]; total: number; limit: number; offset: number }>(
      `/api/images${suffix}`,
    )
  },
  persistImage: (phash: string) =>
    request<{ phash: string; persisted: boolean; file_url: string }>(`/api/images/${phash}/persist`, {
      method: 'POST',
    }),
  clearImagePersist: (phash: string) =>
    request<{ phash: string; persisted: boolean; file_url: string }>(`/api/images/${phash}/persist`, {
      method: 'DELETE',
    }),
  videos: (params?: { peer_external_id?: number; limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params?.peer_external_id != null) query.set('peer_external_id', String(params.peer_external_id))
    if (params?.limit != null) query.set('limit', String(params.limit))
    if (params?.offset != null) query.set('offset', String(params.offset))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<{ videos: CatalogVideo[]; total: number; limit: number; offset: number }>(
      `/api/videos${suffix}`,
    )
  },
  files: (params?: { peer_external_id?: number; limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params?.peer_external_id != null) query.set('peer_external_id', String(params.peer_external_id))
    if (params?.limit != null) query.set('limit', String(params.limit))
    if (params?.offset != null) query.set('offset', String(params.offset))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<{ files: CatalogFile[]; total: number; limit: number; offset: number }>(
      `/api/files${suffix}`,
    )
  },
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (
    task_type: 'fetch_dialogues' | 'forward_snowball' | 'embed' | 'scope_rerank',
    params: Record<string, unknown>,
  ) =>
    request<Job>('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({ task_type, params }),
    }),
  scope: () => request<ScopeState>('/api/scope'),
  addScopeText: (text: string) =>
    request<ScopeState & { added: ScopeInput }>('/api/scope/inputs/text', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  addScopeFile: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch('/api/scope/inputs/file', { method: 'POST', body: form })
    if (!response.ok) {
      let detail = response.statusText
      try {
        const body = (await response.json()) as { detail?: string }
        if (body.detail) detail = body.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    return (await response.json()) as ScopeState & { added: ScopeInput }
  },
  removeScopeInput: (id: string) =>
    request<ScopeState>(`/api/scope/inputs/${id}`, { method: 'DELETE' }),
  searchMessages: (params: { q: string; peer_external_id?: number; limit?: number }) => {
    const query = new URLSearchParams({ q: params.q })
    if (params.peer_external_id != null) query.set('peer_external_id', String(params.peer_external_id))
    if (params.limit != null) query.set('limit', String(params.limit))
    return request<{ messages: CatalogMessage[]; total: number; model_id: string; q: string }>(
      `/api/search/messages?${query.toString()}`,
    )
  },
  searchImages: (params: { q: string; peer_external_id?: number; limit?: number }) => {
    const query = new URLSearchParams({ q: params.q })
    if (params.peer_external_id != null) query.set('peer_external_id', String(params.peer_external_id))
    if (params.limit != null) query.set('limit', String(params.limit))
    return request<{ images: CatalogImage[]; total: number; model_id: string; q: string }>(
      `/api/search/images?${query.toString()}`,
    )
  },
  cancelJob: (id: string) =>
    request<Job>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  syncDialogues: (force = false) =>
    request<{ started: boolean; blocked?: boolean; job: Job | null }>(
      `/api/dialogues/sync${force ? '?force=true' : ''}`,
      { method: 'POST' },
    ),
  resolveSeed: (query: string) =>
    request<{ peer: Peer; resolved: boolean }>('/api/snowball/resolve', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
  graphForwards: (params?: GraphForwardsParams) => {
    const query = graphForwardsQuery(params)
    return request<ForwardGraphResponse>(`/api/graph/forwards${query}`)
  },
  graphForwardsStats: (params?: GraphForwardsParams) => {
    const query = graphForwardsQuery(params)
    return request<ForwardGraphStats>(`/api/graph/forwards/stats${query}`)
  },
  graphSharedImages: (params?: GraphSharedImagesParams) => {
    const query = graphSharedImagesQuery(params)
    return request<ForwardGraphResponse>(`/api/graph/shared-images${query}`)
  },
  graphSharedImagesStats: (params?: GraphSharedImagesParams) => {
    const query = graphSharedImagesQuery(params)
    return request<SharedImageGraphStats>(`/api/graph/shared-images/stats${query}`)
  },
  peerCoverage: (external_id: number) =>
    request<PeerCoverage>(`/api/peers/${external_id}/coverage`),
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}${path}`
}

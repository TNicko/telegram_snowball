export type ModelHealth = {
  id: string
  ready: boolean
  label: string
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
  account: Account | null
  models: {
    image: ModelHealth
    text: ModelHealth
    caption: ModelHealth
  }
  active_job: Job | null
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
}

export type MediaBucket = {
  total: number
  downloaded: number
}

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

export const api = {
  status: () => request<AppStatus>('/api/status'),
  saveCredentials: (api_id: number, api_hash: string) =>
    request('/api/setup/credentials', {
      method: 'PUT',
      body: JSON.stringify({ api_id, api_hash }),
    }),
  peers: () => request<{ peers: Peer[] }>('/api/peers'),
  jobs: () => request<{ jobs: Job[] }>('/api/jobs'),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (task_type: 'fetch_dialogues' | 'forward_snowball', params: Record<string, unknown>) =>
    request<Job>('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({ task_type, params }),
    }),
  syncDialogues: () =>
    request<{ started: boolean; blocked?: boolean; job: Job | null }>('/api/dialogues/sync', {
      method: 'POST',
    }),
  resolveSeed: (query: string) =>
    request<{ peer: Peer; resolved: boolean }>('/api/snowball/resolve', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}${path}`
}

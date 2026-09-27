/** In-memory + sessionStorage layout so a refresh does not respawn the graph. */

const STORAGE_KEY = 'snowball.graphLayout.v1'

let nodeOrder: string[] = []
let positions = new Map<string, [number, number]>()
let persistTimer: number | null = null

type StoredLayout = {
  order: string[]
  positions: Record<string, [number, number]>
}

function isCoord(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    typeof value[0] === 'number' &&
    Number.isFinite(value[0]) &&
    typeof value[1] === 'number' &&
    Number.isFinite(value[1])
  )
}

function hydrateFromStorage(): void {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as StoredLayout
    if (Array.isArray(parsed.order)) {
      nodeOrder = parsed.order.filter((id) => typeof id === 'string')
    }
    if (parsed.positions && typeof parsed.positions === 'object') {
      const next = new Map<string, [number, number]>()
      for (const [id, coord] of Object.entries(parsed.positions)) {
        if (isCoord(coord)) next.set(id, [coord[0], coord[1]])
      }
      positions = next
    }
  } catch {
    /* ignore quota / private mode / bad JSON */
  }
}

function persistNow(): void {
  if (positions.size > 8_000) return
  try {
    const coords: Record<string, [number, number]> = {}
    for (const [id, pos] of positions) coords[id] = pos
    const payload: StoredLayout = { order: nodeOrder, positions: coords }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    /* ignore */
  }
}

function schedulePersist(): void {
  if (typeof window === 'undefined') return
  if (positions.size > 8_000) return
  if (persistTimer != null) window.clearTimeout(persistTimer)
  persistTimer = window.setTimeout(() => {
    persistTimer = null
    persistNow()
  }, 200)
}

hydrateFromStorage()

export function readGraphLayoutSession(): {
  nodeOrder: string[]
  positions: Map<string, [number, number]>
} {
  return { nodeOrder: nodeOrder.slice(), positions: new Map(positions) }
}

export function writeGraphNodeOrder(order: string[]): void {
  nodeOrder = order
}

export function writeGraphPositions(
  next: Map<string, [number, number]>,
  immediate = false,
): void {
  positions = new Map(next)
  if (immediate) {
    if (persistTimer != null) {
      window.clearTimeout(persistTimer)
      persistTimer = null
    }
    persistNow()
    return
  }
  schedulePersist()
}

export function clearGraphLayoutSession(): void {
  nodeOrder = []
  positions = new Map()
  if (persistTimer != null) {
    window.clearTimeout(persistTimer)
    persistTimer = null
  }
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

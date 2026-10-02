/** Catalog rows change only while a dialogue sync or a snowball scrape is running. */

const listeners = new Set<() => void>()
let syncLive = false
let scrapeLive = false

function emit() {
  for (const listener of listeners) listener()
}

export function setSyncLive(next: boolean) {
  if (syncLive === next) return
  syncLive = next
  emit()
}

export function setScrapeLive(next: boolean) {
  if (scrapeLive === next) return
  scrapeLive = next
  emit()
}

export function catalogIsChanging(): boolean {
  return syncLive || scrapeLive
}

export function subscribeLiveWork(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

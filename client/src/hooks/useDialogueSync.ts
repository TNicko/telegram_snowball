import { useEffect, useState } from 'react'
import { api, type Job, type Peer } from '../lib/api'

type Snapshot = {
  job: Job | null
  peers: Peer[]
  error: string | null
  ready: boolean
}

let snapshot: Snapshot = {
  job: null,
  peers: [],
  error: null,
  ready: false,
}

const listeners = new Set<() => void>()
let subscribers = 0
let timer: number | null = null
let pollGeneration = 0
let peersInFlight = false

function emit(patch: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...patch }
  for (const listener of listeners) listener()
}

function isLiveJob(job: Job | null | undefined): boolean {
  return job != null && (job.status === 'queued' || job.status === 'running')
}

function isDialogueJob(job: Job | null | undefined): boolean {
  return job?.task_type === 'fetch_dialogues'
}

function tick(generation: number) {
  void api
    .status()
    .then((status) => {
      if (generation !== pollGeneration) return
      const active = status.active_job
      if (isDialogueJob(active) && isLiveJob(active)) {
        emit({ job: active })
        return
      }
      const prev = snapshot.job
      if (isDialogueJob(prev) && isLiveJob(prev)) {
        emit({ job: { ...prev, status: 'succeeded' } })
      } else if (prev && !isDialogueJob(prev)) {
        emit({ job: null })
      }
    })
    .catch(() => undefined)

  if (peersInFlight) return
  peersInFlight = true
  void api
    .peers()
    .then((res) => {
      if (generation !== pollGeneration) return
      emit({ peers: res.peers, ready: true, error: null })
    })
    .catch((err: Error) => {
      if (generation !== pollGeneration) return
      emit({ error: err.message, ready: true })
    })
    .finally(() => {
      peersInFlight = false
    })
}

let refreshInFlight = false

async function refreshDialogues() {
  const running = isDialogueJob(snapshot.job) && isLiveJob(snapshot.job)
  if (refreshInFlight || running) return
  refreshInFlight = true
  try {
    const res = await api.syncDialogues(true)
    if (res.blocked) {
      emit({ error: 'A job is already running.' })
      return
    }
    if (res.job && isDialogueJob(res.job) && !res.blocked) emit({ job: res.job, error: null })
  } catch (err) {
    emit({ error: err instanceof Error ? err.message : 'Sync failed' })
  } finally {
    refreshInFlight = false
  }
}

function subscribe() {
  subscribers += 1
  if (subscribers === 1) {
    pollGeneration += 1
    const generation = pollGeneration
    void api
      .peers()
      .then((res) => {
        if (generation !== pollGeneration) return
        emit({ peers: res.peers, ready: true, error: null })
        if (res.peers.length > 0) return null
        return api.syncDialogues()
      })
      .then((res) => {
        if (!res || generation !== pollGeneration) return
        if (isDialogueJob(res.job)) emit({ job: res.job })
      })
      .catch((err: Error) => {
        if (generation !== pollGeneration) return
        emit({ error: err.message, ready: true })
      })
    tick(generation)
    timer = window.setInterval(() => tick(generation), 1000)
  }
  return () => {
    subscribers -= 1
    if (subscribers === 0 && timer != null) {
      pollGeneration += 1
      window.clearInterval(timer)
      timer = null
    }
  }
}

export function useDialogueSync() {
  const [, setVersion] = useState(0)

  useEffect(() => {
    const onChange = () => setVersion((n) => n + 1)
    listeners.add(onChange)
    const stop = subscribe()
    return () => {
      listeners.delete(onChange)
      stop()
    }
  }, [])

  const running = isDialogueJob(snapshot.job) && isLiveJob(snapshot.job)
  const loaded = Number(snapshot.job?.progress?.dialogues_materialized ?? snapshot.peers.length)
  return { ...snapshot, running, loaded, refresh: refreshDialogues }
}

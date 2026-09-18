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

function emit(patch: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...patch }
  for (const listener of listeners) listener()
}

function tick(generation: number) {
  void api
    .status()
    .then((status) => {
      if (generation !== pollGeneration) return
      if (status.active_job?.task_type === 'fetch_dialogues') {
        emit({ job: status.active_job })
      } else if (status.active_job == null) {
        const prev = snapshot.job
        if (prev && (prev.status === 'queued' || prev.status === 'running')) {
          emit({ job: { ...prev, status: 'succeeded' } })
        }
      }
    })
    .catch(() => undefined)

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
}

function subscribe() {
  subscribers += 1
  if (subscribers === 1) {
    pollGeneration += 1
    const generation = pollGeneration
    void api
      .syncDialogues()
      .then((res) => {
        if (generation !== pollGeneration) return
        if (res.job) emit({ job: res.job })
      })
      .catch((err: Error) => {
        if (generation !== pollGeneration) return
        emit({ error: err.message })
      })
    tick(generation)
    timer = window.setInterval(() => tick(generation), 1500)
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

  const running = snapshot.job?.status === 'queued' || snapshot.job?.status === 'running'
  const loaded = Number(snapshot.job?.progress?.dialogues_materialized ?? snapshot.peers.length)
  return { ...snapshot, running, loaded }
}

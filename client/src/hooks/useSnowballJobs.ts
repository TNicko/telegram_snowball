import { useEffect, useState } from 'react'
import { api, type Job } from '../lib/api'
import { setScrapeLive } from '../lib/liveWork'

const STORAGE_KEY = 'snowball.snowballJobs'

function snowballJobs(jobs: Job[]): Job[] {
  return jobs.filter((job) => job.task_type === 'forward_snowball')
}

function readStoredJobs(): Job[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return snowballJobs(parsed as Job[])
  } catch {
    return []
  }
}

function writeStoredJobs(jobs: Job[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(jobs))
  } catch {
    /* ignore quota / private mode */
  }
}

let cached = readStoredJobs()
const listeners = new Set<() => void>()
let subscribers = 0
let timer: number | null = null
let pollGeneration = 0
let jobsInFlight = false

function snowballLive(jobs: Job[]): boolean {
  return jobs.some((job) => job.status === 'queued' || job.status === 'running')
}

function ensureJobPolling() {
  if (subscribers === 0 || !snowballLive(cached)) {
    if (timer != null) {
      window.clearInterval(timer)
      timer = null
    }
    return
  }
  if (timer == null) {
    timer = window.setInterval(() => tick(pollGeneration), 1000)
  }
}

function emit(jobs: Job[]) {
  cached = jobs
  writeStoredJobs(jobs)
  setScrapeLive(snowballLive(cached))
  ensureJobPolling()
  for (const listener of listeners) listener()
}

export function hydrateSnowballJobs(jobs: Job[]) {
  emit(snowballJobs(jobs))
}

function tick(generation: number) {
  if (jobsInFlight) return
  jobsInFlight = true
  void api
    .jobs()
    .then((res) => {
      if (generation !== pollGeneration) return
      emit(snowballJobs(res.jobs))
    })
    .catch(() => undefined)
    .finally(() => {
      jobsInFlight = false
    })
}

function subscribe() {
  subscribers += 1
  if (subscribers === 1) {
    pollGeneration += 1
    const generation = pollGeneration
    tick(generation)
    ensureJobPolling()
  }
  return () => {
    subscribers -= 1
    if (subscribers === 0) {
      pollGeneration += 1
      if (timer != null) {
        window.clearInterval(timer)
        timer = null
      }
    }
  }
}

export function useSnowballJobs() {
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

  const setJobs = (update: Job[] | ((current: Job[]) => Job[])) => {
    const next = typeof update === 'function' ? update(cached) : update
    emit(snowballJobs(next))
  }

  return { jobs: cached, setJobs }
}

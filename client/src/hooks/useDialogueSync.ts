import { useEffect, useState } from 'react'
import { api, type Job, type Peer } from '../lib/api'

export function useDialogueSync() {
  const [job, setJob] = useState<Job | null>(null)
  const [peers, setPeers] = useState<Peer[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void api
      .syncDialogues()
      .then((res) => {
        if (!cancelled && res.job) setJob(res.job)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })

    const tick = () => {
      void api
        .status()
        .then((status) => {
          if (cancelled) return
          if (status.active_job?.task_type === 'fetch_dialogues') {
            setJob(status.active_job)
          } else if (status.active_job == null) {
            setJob((prev) =>
              prev && (prev.status === 'queued' || prev.status === 'running')
                ? { ...prev, status: 'succeeded' }
                : prev,
            )
          }
        })
        .catch(() => undefined)
      void api
        .peers()
        .then((res) => {
          if (!cancelled) setPeers(res.peers)
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message)
        })
    }
    tick()
    const timer = window.setInterval(tick, 1500)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const running = job?.status === 'queued' || job?.status === 'running'
  const loaded = Number(job?.progress?.dialogues_materialized ?? peers.length)
  return { job, peers, error, running, loaded }
}

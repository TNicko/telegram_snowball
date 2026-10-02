import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { LoadingText } from '../components/LoadingText'
import { PeerAvatar } from '../components/PeerAvatar'
import { api, type Job, type Peer } from '../lib/api'

export default function JobPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState<Job | null>(null)
  const [peers, setPeers] = useState<Peer[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!jobId) return
    let timer: number | null = null
    const tick = () => {
      void api
        .job(jobId)
        .then((next) => {
          setJob(next)
          const running = next.status === 'queued' || next.status === 'running'
          if (running) {
            void api.peers().then((res) => setPeers(res.peers)).catch(() => undefined)
            return
          }
          if (timer != null) {
            window.clearInterval(timer)
            timer = null
          }
        })
        .catch((err: Error) => setError(err.message))
    }
    tick()
    timer = window.setInterval(tick, 2000)
    return () => {
      if (timer != null) window.clearInterval(timer)
    }
  }, [jobId])

  const current = Number(job?.progress?.current_peer ?? 0)
  const ordered = [...peers].sort((a, b) => {
    if (a.is_scraping && !b.is_scraping) return -1
    if (!a.is_scraping && b.is_scraping) return 1
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })

  return (
    <div>
      <p className="muted">
        <Link to="/">Home</Link>
      </p>
      <h1 className="pageTitle">{job?.task_type ?? 'Job'}</h1>
      <p className="lede">
        {job && (job.status === 'queued' || job.status === 'running') ? (
          <LoadingText>{String(job.progress?.detail ?? job.status)}</LoadingText>
        ) : (
          <>
            {job?.status ?? 'loading'} · {String(job?.progress?.detail ?? '')}
          </>
        )}
      </p>
      {error ? <p className="error">{error}</p> : null}
      <div className="list">
        {ordered.map((peer) => (
          <div className="peerRow" key={peer.external_id}>
            <PeerAvatar peer={peer} />
            <div>
              <div>{peer.title ?? peer.username ?? peer.external_id}</div>
              <div className="muted">
                {peer.messages_scraped} messages
                {peer.external_id === current ? ' · current' : ''}
              </div>
              {peer.scrape_detail ? <div className="muted">{peer.scrape_detail}</div> : null}
            </div>
            {peer.is_scraping ? <div className="spinner" /> : null}
          </div>
        ))}
      </div>
    </div>
  )
}

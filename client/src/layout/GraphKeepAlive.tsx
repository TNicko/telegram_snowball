import { useEffect, useState } from 'react'
import GraphPage from '../pages/GraphPage'

/** Keep the Cosmos canvas mounted after the first visit so route changes do not destroy WebGL. */
export function GraphKeepAlive({ active }: { active: boolean }) {
  const [seen, setSeen] = useState(active)

  useEffect(() => {
    if (active) setSeen(true)
  }, [active])

  if (!seen) return null

  return (
    <div
      className={`graphKeepAlive${active ? ' isActive' : ''}`}
      aria-hidden={!active}
      inert={!active}
    >
      <GraphPage active={active} />
    </div>
  )
}

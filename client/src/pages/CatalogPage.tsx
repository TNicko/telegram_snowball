import { useMemo, useState } from 'react'
import { Navigate, useParams } from 'react-router'
import { CatalogPeerTable } from '../components/CatalogPeerTable'
import { CatalogSearchBar } from '../components/CatalogSearchBar'
import { LoadingText } from '../components/LoadingText'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { peerMatchesQuery } from '../lib/peer'

export default function CatalogPage() {
  const { kind = 'peers' } = useParams()
  if (kind === 'images') {
    return (
      <div>
        <h1 className="pageTitle">Image catalog</h1>
        <p className="lede">
          Deduped pHash list (unique peers vs total appearances) ships after media download + hash
          landing in the worker.
        </p>
      </div>
    )
  }
  if (kind === 'videos') {
    return (
      <div>
        <h1 className="pageTitle">Video catalog</h1>
        <p className="lede">Keyframe pHash / PDQ catalog — same layout as images, after video hashing lands.</p>
      </div>
    )
  }
  if (kind !== 'peers') return <Navigate to="/catalog/peers" replace />
  return <CatalogPeersPage />
}

function CatalogPeersPage() {
  const { peers, error, running, loaded } = useDialogueSync()
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')

  const visible = useMemo(() => {
    return peers
      .filter((peer) => peerMatchesQuery(peer, query))
      .slice()
      .sort((a, b) => {
        const ta = new Date(a.created_at ?? a.updated_at).getTime()
        const tb = new Date(b.created_at ?? b.updated_at).getTime()
        if (tb !== ta) return tb - ta
        return b.external_id - a.external_id
      })
  }, [peers, query])

  return (
    <div>
      <CatalogSearchBar
        query={draft}
        onQueryChange={(value) => {
          setDraft(value)
          setQuery(value)
        }}
        onSearch={setQuery}
        isLoading={running}
      />
      {running ? (
        <p>
          <LoadingText>
            {loaded > 0 ? `Loading dialogues · ${loaded} so far` : 'Loading dialogues'}
          </LoadingText>
        </p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <CatalogPeerTable
        peers={visible}
        totalCount={query ? visible.length : peers.length}
        emptyMessage={
          peers.length === 0
            ? running
              ? 'Loading peers…'
              : 'No peers in this account yet.'
            : 'No peers match that search.'
        }
      />
    </div>
  )
}

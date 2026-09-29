import { useEffect, useRef, useState } from 'react'
import { ImagePlus, Sparkles, X } from 'lucide-react'
import { InfoTip } from './InfoTip'
import { api, type Job, type ScopeInput, type ScopeState } from '../lib/api'
import { isLiveJob } from './HomeJobs'
import h from '../pages/HomePage.module.css'

function isLiveJobStatus(job: Job | null): boolean {
  return job != null && isLiveJob(job.status)
}

function pendingFrom(state: ScopeState): boolean {
  if (!state.inputs.length) return false
  if (typeof state.needs_rescore === 'boolean') return state.needs_rescore
  return state.last_rerank_at == null
}

function inputNeedsApply(item: ScopeInput, lastRerankAt: string | null): boolean {
  if (!lastRerankAt) return true
  const added = Date.parse(item.created_at)
  const applied = Date.parse(lastRerankAt)
  if (Number.isNaN(added) || Number.isNaN(applied)) return true
  return added > applied
}

function rescoreIdleCopy(inputs: ScopeInput[], lastRerankAt: string | null): string {
  const count = inputs.filter((item) => inputNeedsApply(item, lastRerankAt)).length
  const rest = 'Rescore the catalog so snowball prefers matching channels.'
  if (count === 0) return rest
  const noun = count === 1 ? 'input' : 'inputs'
  return `${count} new ${noun} added. ${rest}`
}

export function ScopeInputsCard({
  imageReady,
  multimodal,
  disabled,
  onInputsChange,
}: {
  imageReady: boolean
  multimodal: boolean
  disabled?: boolean
  onInputsChange?: (count: number) => void
}) {
  const [scope, setScope] = useState<ScopeState | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [addingText, setAddingText] = useState(false)
  const [addingFile, setAddingFile] = useState(false)
  const [rerank, setRerank] = useState<Job | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [dirty, setDirty] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api
      .scope()
      .then((next) => {
        setScope(next)
        setDirty(pendingFrom(next))
        onInputsChange?.(next.inputs.length)
      })
      .catch(() => undefined)
  }, [onInputsChange])

  useEffect(() => {
    if (!rerank || !isLiveJob(rerank.status)) return
    const timer = window.setInterval(() => {
      void api
        .job(rerank.id)
        .then(setRerank)
        .catch(() => undefined)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [rerank])

  useEffect(() => {
    if (rerank?.status !== 'succeeded') return
    void api
      .scope()
      .then((next) => {
        setScope(next)
        setDirty(pendingFrom(next))
        onInputsChange?.(next.inputs.length)
      })
      .catch(() => undefined)
  }, [rerank?.status, onInputsChange])

  const inputs = scope?.inputs ?? []
  const textOk = imageReady && multimodal
  const fileOk = imageReady
  const reranking = isLiveJobStatus(rerank)

  const apply = (next: ScopeState) => {
    setScope(next)
    setDirty(next.inputs.length > 0)
    onInputsChange?.(next.inputs.length)
    setError(null)
  }

  const addText = async () => {
    const value = text.trim()
    if (!value || busy || !textOk) return
    setBusy(true)
    setAddingText(true)
    setError(null)
    try {
      apply(await api.addScopeText(value))
      setText('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add that prompt')
    } finally {
      setAddingText(false)
      setBusy(false)
    }
  }

  const addFiles = async (files: FileList | File[]) => {
    const list = Array.from(files).filter((file) => file.type.startsWith('image/'))
    if (!list.length || busy || !fileOk) return
    setBusy(true)
    setAddingFile(true)
    setError(null)
    try {
      let next: ScopeState | null = null
      for (const file of list) {
        next = await api.addScopeFile(file)
      }
      if (next) apply(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add that image')
    } finally {
      setAddingFile(false)
      setBusy(false)
    }
  }

  const remove = async (item: ScopeInput) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      apply(await api.removeScopeInput(item.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove that input')
    } finally {
      setBusy(false)
    }
  }

  const rescore = async () => {
    if (busy || reranking || disabled) return
    setBusy(true)
    setError(null)
    try {
      const job = await api.createJob('scope_rerank', {})
      setRerank(job)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start rescore')
    } finally {
      setBusy(false)
    }
  }

  const rerankDetail =
    rerank && typeof rerank.progress?.detail === 'string' ? rerank.progress.detail : null
  const showRescore =
    inputs.length > 0 && (dirty || reranking || rerank?.status === 'failed')

  return (
    <section className={`homeCol ${h.scopeCol}`}>
      <div className={h.scopeHead}>
        <h2 className="sectionTitle">
          <InfoTip text={"Enhance forward snowballing by prioritizing more relevant channels based on your context. Add text prompts here, and any images that look similar to the content you are trying to crawl.\n\nExample: investigating cryptocurrency pump-and-dump channels? Add “cryptocurrency”, “bitcoin”, “new token launch”, “wallet connect airdrop”, and as many more as you want."}>
            Scope
          </InfoTip>
        </h2>
      </div>
      <div
        className={`card ${h.scopeCard}${dragOver ? ` ${h.scopeDropActive}` : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          if (fileOk && !busy) setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragOver(false)
          if (busy || !fileOk) return
          if (event.dataTransfer.files.length) void addFiles(event.dataTransfer.files)
        }}
      >
        {!imageReady ? (
          <p className={h.scopeWarn}>Set up a vision model first.</p>
        ) : null}
        {imageReady && !multimodal ? (
          <p className={h.scopeWarn}>Text needs CLIP or SigLIP. Images still work.</p>
        ) : null}
        <div className={h.scopeBody}>
          <div className={h.scopeComposer}>
            <div className={h.scopeRow}>
              <input
                className={h.scopeInput}
                value={text}
                placeholder={textOk ? 'Describe the media you are interested in crawling' : 'Vision model required'}
                disabled={busy || !textOk}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void addText()
                  }
                }}
                aria-label="Scope text prompt"
              />
              <button
                type="button"
                className={`btn ${h.scopeAction}${addingText ? ' btnLoading' : ''}`}
                disabled={busy || !textOk || !text.trim()}
                aria-busy={addingText || undefined}
                onClick={() => void addText()}
              >
                {addingText ? (
                  <span className="btnBusy">
                    <span className="spinner" aria-hidden />
                    Add
                  </span>
                ) : (
                  'Add'
                )}
              </button>
              <button
                type="button"
                className={`btn ${h.scopeAction}${addingFile ? ' btnLoading' : ''}`}
                disabled={busy || !fileOk}
                aria-busy={addingFile || undefined}
                onClick={() => fileRef.current?.click()}
                aria-label="Add Scope image"
              >
                {addingFile ? (
                  <span className="spinner" aria-hidden />
                ) : (
                  <ImagePlus size={15} strokeWidth={2} aria-hidden />
                )}
                Image
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                multiple
                hidden
                onChange={(event) => {
                  if (event.target.files?.length) void addFiles(event.target.files)
                  event.target.value = ''
                }}
              />
            </div>
            {showRescore ? (
              <div className={h.scopeRescoreBar}>
                <p className={h.scopeRescoreCopy}>
                  {reranking
                    ? rerankDetail || 'Rescoring stored images against these inputs.'
                    : rescoreIdleCopy(inputs, scope?.last_rerank_at ?? null)}
                </p>
                <button
                  type="button"
                  className="btn btnPrimary"
                  disabled={busy || reranking || disabled || !imageReady}
                  onClick={() => void rescore()}
                >
                  {reranking ? (
                    <span className="spinner" aria-hidden />
                  ) : (
                    <Sparkles size={14} strokeWidth={2} aria-hidden />
                  )}
                  Apply new scoring
                </button>
              </div>
            ) : rerank?.status === 'succeeded' ? (
              <p className={h.scopeMeta}>{rerankDetail || 'Catalog rescored.'}</p>
            ) : null}
            {rerank?.status === 'failed' ? (
              <p className="error">{rerank.error || 'Rescore failed'}</p>
            ) : null}
            {error ? <p className="error">{error}</p> : null}
          </div>
          <div className={h.scopeSaved}>
            <h3 className={h.scopeListTitle}>Saved inputs</h3>
            {inputs.length ? (
              <ul className={h.scopeList} aria-label="Scope inputs">
                {inputs.map((item) => (
                  <li key={item.id} className={h.scopeChip}>
                    {item.kind === 'file' ? (
                      <img
                        className={h.scopeThumb}
                        src={`/api/scope/inputs/${item.id}/file`}
                        alt={item.filename ?? 'Scope image'}
                      />
                    ) : null}
                    <span className={h.scopeChipLabel}>
                      {item.kind === 'text' ? item.text : item.filename}
                    </span>
                    {inputNeedsApply(item, scope?.last_rerank_at ?? null) ? (
                      <span className={h.scopePending}>Not applied</span>
                    ) : null}
                    <button
                      type="button"
                      className={h.scopeChipRemove}
                      aria-label="Remove Scope input"
                      disabled={busy}
                      onClick={() => void remove(item)}
                    >
                      <X size={12} strokeWidth={2.2} aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={h.scopeEmpty}>
                None saved yet. Add images, keywords, phrases, or a prompt to scope your crawling.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}


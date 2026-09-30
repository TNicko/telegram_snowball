import s from './StopSyncConfirm.module.css'

export function StopSyncConfirm({
  busy,
  onConfirm,
  onClose,
}: {
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <div className={`modalScrim ${s.scrim}`} onClick={onClose}>
      <div
        className={`modal ${s.modal}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="stop-sync-title"
        aria-describedby="stop-sync-copy"
        onClick={(event) => event.stopPropagation()}
      >
        <h3 id="stop-sync-title" className={s.title}>
          Stop chat sync?
        </h3>
        <p id="stop-sync-copy" className={s.copy}>
          You can start this scrape now, but it will stop the chat sync that is running.
        </p>
        <div className={s.actions}>
          <button
            type="button"
            className={`btn btnPrimary${busy ? ' btnLoading' : ''}`}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? (
              <span className="btnBusy">
                <span className="spinner" aria-hidden />
                Starting
              </span>
            ) : (
              'Stop sync and scrape'
            )}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

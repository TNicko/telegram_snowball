import { useEffect, useRef, useState } from 'react'
import { ArrowLeftRight, EllipsisVertical, LogOut } from 'lucide-react'
import h from '../pages/HomePage.module.css'

type Props = {
  busy?: boolean
  onChangeAccount: () => void
  onRemoveAccount: () => void
}

export function AccountCardMenu({ busy, onChangeAccount, onRemoveAccount }: Props) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className={h.accountMenuWrap} ref={wrapRef}>
      <button
        type="button"
        className={h.accountMenuBtn}
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        onClick={() => setOpen((value) => !value)}
      >
        <EllipsisVertical size={16} strokeWidth={2} aria-hidden />
      </button>
      {open ? (
        <div className={h.accountMenu} role="menu">
          <button
            type="button"
            className={h.accountMenuItem}
            role="menuitem"
            disabled={busy}
            onClick={() => {
              setOpen(false)
              onChangeAccount()
            }}
          >
            <span className={h.accountMenuIcon} aria-hidden>
              <ArrowLeftRight size={16} strokeWidth={2} />
            </span>
            Change account
          </button>
          <button
            type="button"
            className={h.accountMenuItem}
            data-danger="true"
            role="menuitem"
            disabled={busy}
            onClick={() => {
              setOpen(false)
              onRemoveAccount()
            }}
          >
            <span className={h.accountMenuIcon} aria-hidden>
              <LogOut size={16} strokeWidth={2} />
            </span>
            Remove account
          </button>
        </div>
      ) : null}
    </div>
  )
}

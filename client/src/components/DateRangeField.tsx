import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { Calendar, X } from 'lucide-react'
import { DayPicker, type DateRange, type Matcher } from 'react-day-picker'
import 'react-day-picker/style.css'
import s from './DateRangeField.module.css'

function formatDay(date: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function DatePart({
  label,
  value,
  open,
  disabled,
  popoverZIndex = 40,
  onToggle,
  onClose,
  onChange,
  onClear,
}: {
  label: string
  value?: Date
  open: boolean
  disabled?: Matcher
  popoverZIndex?: number
  onToggle: () => void
  onClose: () => void
  onChange: (date: Date | undefined) => void
  onClear: () => void
}) {
  const btnRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<CSSProperties>({})

  useLayoutEffect(() => {
    if (!open || !btnRef.current) return
    const place = () => {
      const r = btnRef.current!.getBoundingClientRect()
      const width = Math.max(r.width, 16.5 * 16)
      const left = Math.min(r.left, window.innerWidth - width - 12)
      setPos({
        position: 'fixed',
        top: r.bottom + 6,
        left: Math.max(12, left),
        zIndex: popoverZIndex,
      })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, popoverZIndex])

  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node
      if (btnRef.current?.contains(target) || popRef.current?.contains(target)) return
      onClose()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  return (
    <div className={s.col}>
      <span className={s.label}>{label}</span>
      <div className={s.inputRow}>
        <button
          ref={btnRef}
          type="button"
          className={`${s.input}${open ? ` ${s.inputOpen}` : ''}`}
          aria-label={label}
          aria-expanded={open}
          aria-haspopup="dialog"
          onClick={onToggle}
        >
          <Calendar size={14} strokeWidth={2} aria-hidden />
          <span className={value ? s.value : s.placeholder}>
            {value ? formatDay(value) : 'Select date'}
          </span>
        </button>
        {value ? (
          <button
            type="button"
            className={s.clear}
            aria-label={`Clear ${label.toLowerCase()} date`}
            onClick={() => {
              onClear()
              onClose()
            }}
          >
            <X size={13} strokeWidth={2.2} />
          </button>
        ) : null}
      </div>
      {open
        ? createPortal(
            <div
              ref={popRef}
              className={s.pop}
              style={pos}
              role="dialog"
              aria-label={`Choose ${label.toLowerCase()} date`}
            >
              <DayPicker
                mode="single"
                selected={value}
                onSelect={(date) => {
                  if (date) onChange(date)
                  onClose()
                }}
                disabled={disabled}
                className={s.calendar}
              />
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}

export function DateRangeField({
  value,
  onChange,
  popoverZIndex,
}: {
  value?: DateRange
  onChange: (range: DateRange | undefined) => void
  popoverZIndex?: number
}) {
  const [open, setOpen] = useState<'from' | 'to' | null>(null)
  const close = useCallback(() => setOpen(null), [])

  const commit = (from?: Date, to?: Date) => {
    onChange(from || to ? { from, to } : undefined)
  }

  return (
    <div className={s.root}>
      <div className={s.pair}>
        <DatePart
          label="From"
          value={value?.from}
          open={open === 'from'}
          disabled={value?.to ? { after: value.to } : undefined}
          popoverZIndex={popoverZIndex}
          onToggle={() => setOpen((cur) => (cur === 'from' ? null : 'from'))}
          onClose={close}
          onChange={(from) => commit(from, value?.to)}
          onClear={() => commit(undefined, value?.to)}
        />
        <DatePart
          label="To"
          value={value?.to}
          open={open === 'to'}
          disabled={value?.from ? { before: value.from } : undefined}
          popoverZIndex={popoverZIndex}
          onToggle={() => setOpen((cur) => (cur === 'to' ? null : 'to'))}
          onClose={close}
          onChange={(to) => commit(value?.from, to)}
          onClear={() => commit(value?.from, undefined)}
        />
      </div>
    </div>
  )
}

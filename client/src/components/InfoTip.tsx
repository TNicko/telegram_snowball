import { type ReactNode } from 'react'
import { Info } from 'lucide-react'
import s from './InfoTip.module.css'

export function InfoTip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className={s.wrap} tabIndex={0}>
      <span className={s.text}>{children}</span>
      <Info className={s.icon} size={11} strokeWidth={2} aria-hidden />
      <span className={s.tip} role="tooltip">
        {text}
      </span>
    </span>
  )
}

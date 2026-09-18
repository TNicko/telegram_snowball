import lt from './LoadingText.module.css'

type Props = {
  children: string
  className?: string
}

/** Shimmering status text (same pattern as messenger client LoadingText). */
export function LoadingText({ children, className }: Props) {
  return (
    <span className={[lt.text, className].filter(Boolean).join(' ')} aria-label={children}>
      {children}
    </span>
  )
}

export const TextLoading = LoadingText

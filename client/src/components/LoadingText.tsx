import lt from './LoadingText.module.css'

type Props = {
  children: string
  className?: string
}

/** Shimmering status text. */
export function LoadingText({ children, className }: Props) {
  return (
    <span className={[lt.text, className].filter(Boolean).join(' ')} aria-label={children}>
      {children}
    </span>
  )
}

export const TextLoading = LoadingText

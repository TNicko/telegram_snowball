import { type FormEvent, type ReactNode } from 'react'
import s from './CatalogSearchBar.module.css'

function SearchIcon() {
  return (
    <svg className={s.iconSvg} width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M15.8 15.8 21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function CatalogSearchBar({
  query,
  onQueryChange,
  onSearch,
  isLoading = false,
  placeholder = 'Search peers by name, @username, or id',
  ariaLabel = 'Search peers',
  flush = false,
  results,
}: {
  query: string
  onQueryChange: (query: string) => void
  onSearch: (query: string) => void
  isLoading?: boolean
  placeholder?: string
  ariaLabel?: string
  flush?: boolean
  results?: ReactNode
}) {
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSearch(query.trim())
  }
  const open = Boolean(results)

  return (
    <form
      className={`${s.bar}${flush ? ` ${s.barFlush}` : ''}${open ? ` ${s.barOpen}` : ''}`}
      onSubmit={submit}
      noValidate
    >
      <div className={`${s.composer}${open ? ` ${s.composerOpen}` : ''}`}>
        <input
          className={s.input}
          type="search"
          name="q"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          aria-label={ariaLabel}
          aria-expanded={open}
          aria-controls={open ? 'search-bar-results' : undefined}
        />
        <button className={s.iconBtn} type="submit" aria-label="Search" aria-busy={isLoading}>
          {isLoading ? <span className="spinner" aria-hidden /> : <SearchIcon />}
        </button>
      </div>
      {open ? (
        <div className={s.results} id="search-bar-results" role="listbox">
          {results}
        </div>
      ) : null}
    </form>
  )
}

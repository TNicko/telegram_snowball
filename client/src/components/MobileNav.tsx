import { useCallback, useEffect, useId, useRef, useState, type CSSProperties } from 'react'
import { NavLink } from 'react-router'
import './MobileNav.css'

export type NavMenuItem = {
  label: string
  description: string
  href: string
}

export type NavMenuSection = {
  heading: string
  items: NavMenuItem[]
}

export type MobileNavGroup = {
  id: string
  label: string
  columns: NavMenuSection[][]
  isActive?: boolean
}

export type MobileNavLink = {
  label: string
  href: string
  end?: boolean
  isActive?: boolean
}

type Props = {
  groups: MobileNavGroup[]
  links: MobileNavLink[]
  leadingLinks?: MobileNavLink[]
}

function MenuSection({ section, onNavigate }: { section: NavMenuSection; onNavigate: () => void }) {
  return (
    <section className="navDropdown__section">
      {section.heading ? <h3 className="navDropdown__heading">{section.heading}</h3> : null}
      <ul className="navDropdown__list">
        {section.items.map((item) => (
          <li key={item.href}>
            <NavLink
              className={({ isActive }) =>
                `navDropdown__item${isActive ? ' navDropdown__item--active' : ''}`
              }
              to={item.href}
              end
              onClick={onNavigate}
            >
              <span className="navDropdown__label">{item.label}</span>
              {item.description ? (
                <span className="navDropdown__description">{item.description}</span>
              ) : null}
            </NavLink>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Chevron() {
  return (
    <svg
      className="mobileNav__chevron"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

function NavItem({ link, onNavigate }: { link: MobileNavLink; onNavigate: () => void }) {
  return (
    <NavLink
      to={link.href}
      end={link.end}
      className={({ isActive }) => `mobileNav__link${isActive || link.isActive ? ' mobileNav__link--active' : ''}`}
      onClick={onNavigate}
    >
      {link.label}
    </NavLink>
  )
}

export function MobileNav({ groups, links, leadingLinks = [] }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [panelTop, setPanelTop] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelId = useId()

  const close = useCallback(() => {
    setMenuOpen(false)
    setExpandedId(null)
  }, [])

  const toggleGroup = (id: string) => {
    setExpandedId((current) => (current === id ? null : id))
  }

  const toggleMenu = () => {
    setMenuOpen((open) => {
      if (!open) {
        const nav = document.querySelector('.sidebar')
        if (nav) setPanelTop(nav.getBoundingClientRect().bottom)
      }
      return !open
    })
  }

  useEffect(() => {
    if (!menuOpen) return

    const updateTop = () => {
      const nav = document.querySelector('.sidebar')
      if (nav) setPanelTop(nav.getBoundingClientRect().bottom)
    }

    updateTop()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }

    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close()
    }

    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', updateTop)
    window.addEventListener('scroll', updateTop, true)
    document.addEventListener('mousedown', onPointerDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', updateTop)
      window.removeEventListener('scroll', updateTop, true)
      document.removeEventListener('mousedown', onPointerDown)
    }
  }, [menuOpen, close])

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 901px)')
    const onChange = () => {
      if (mq.matches) close()
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [close])

  return (
    <div ref={rootRef} className="mobileNav">
      <button
        type="button"
        className="mobileNav__toggle"
        aria-expanded={menuOpen}
        aria-controls={panelId}
        aria-label={menuOpen ? 'Close menu' : 'Open menu'}
        onClick={toggleMenu}
      >
        {menuOpen ? (
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
          </svg>
        ) : (
          <svg
            width="26"
            height="26"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <line x1="4" x2="20" y1="6" y2="6" />
            <line x1="4" x2="20" y1="12" y2="12" />
            <line x1="4" x2="20" y1="18" y2="18" />
          </svg>
        )}
      </button>

      <div
        className={`mobileNav__panelWrap${menuOpen ? ' mobileNav__panelWrap--open' : ''}`}
        aria-hidden={!menuOpen}
        inert={!menuOpen}
        style={
          {
            top: panelTop,
            ['--mobile-nav-panel-top']: `${panelTop}px`,
          } as CSSProperties
        }
      >
        <div className="mobileNav__panelInner">
          <nav id={panelId} className="mobileNav__panel" aria-label="Main">
            <div className="mobileNav__panelCard">
              <div className="mobileNav__list">
                {leadingLinks.map((link) => (
                  <NavItem key={link.href} link={link} onNavigate={close} />
                ))}

                {groups.map((group) => {
                  const expanded = expandedId === group.id
                  const columnsClass =
                    group.columns.length >= 3
                      ? ' navDropdown__columns--three'
                      : group.columns.length > 1
                        ? ' navDropdown__columns--multi'
                        : ''

                  return (
                    <div
                      key={group.id}
                      className={`mobileNav__group${group.isActive ? ' mobileNav__group--active' : ''}`}
                    >
                      <button
                        type="button"
                        className="mobileNav__groupTrigger"
                        aria-expanded={expanded}
                        onClick={() => toggleGroup(group.id)}
                      >
                        <span>{group.label}</span>
                        <Chevron />
                      </button>

                      <div
                        className={`mobileNav__groupBodyWrap${expanded ? ' mobileNav__groupBodyWrap--open' : ''}`}
                        aria-hidden={!expanded}
                      >
                        <div className="mobileNav__groupBodyInner">
                          <div className="mobileNav__groupBody">
                            <div className={`navDropdown__columns${columnsClass}`}>
                              {group.columns.map((columnSections, colIndex) => (
                                <div key={colIndex} className="navDropdown__column">
                                  {columnSections.map((section) => (
                                    <MenuSection
                                      key={section.heading || section.items[0]?.href || String(colIndex)}
                                      section={section}
                                      onNavigate={close}
                                    />
                                  ))}
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}

                {links.map((link) => (
                  <NavItem key={link.href} link={link} onNavigate={close} />
                ))}
              </div>
            </div>
          </nav>
        </div>
      </div>
    </div>
  )
}

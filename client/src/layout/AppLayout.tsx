import { useRef, useState } from 'react'
import { FileText, House, Image, LayoutList, Library, MessageSquareText, Share2, Video, type LucideIcon } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import brandIcon from '../assets/snowball-icon.png'
import { AccountAvatar } from '../components/AccountAvatar'
import { CatalogStorageBar } from '../components/CatalogStorageBar'
import { MobileNav } from '../components/MobileNav'
import { useDialogueSync } from '../hooks/useDialogueSync'
import { GraphKeepAlive } from './GraphKeepAlive'
import { accountDisplayName } from '../lib/account'
import { useAppStatus } from './statusContext'

const CATALOG_HOME = '/catalog/peers'

const catalogTabs: { to: string; label: string; icon: LucideIcon }[] = [
  { to: '/catalog/peers', label: 'General', icon: LayoutList },
  { to: '/catalog/messages', label: 'Messages', icon: MessageSquareText },
  { to: '/catalog/images', label: 'Images', icon: Image },
  { to: '/catalog/videos', label: 'Videos', icon: Video },
  { to: '/catalog/files', label: 'Files', icon: FileText },
]

export function AppLayout() {
  const { pathname } = useLocation()
  const onCatalog = pathname.startsWith('/catalog')
  const onGraph = pathname === '/graph'
  const lastCatalogPath = useRef(CATALOG_HOME)
  if (onCatalog) lastCatalogPath.current = pathname
  const catalogTo = onCatalog ? pathname : lastCatalogPath.current
  const [hoverExpanded, setHoverExpanded] = useState(false)
  const collapsed = !hoverExpanded
  const status = useAppStatus()
  const account = status?.account ?? null
  const accountName = account ? accountDisplayName(account) : null
  useDialogueSync()

  return (
    <div className="shell">
      <div className="bodyRow">
        <aside
          className={`sidebar${hoverExpanded ? ' sidebarHoverExpanded' : ''}`}
          data-collapsed={collapsed ? 'true' : 'false'}
        >
          <div
            className="sidebarPanel"
            onPointerEnter={() => setHoverExpanded(true)}
            onPointerLeave={() => setHoverExpanded(false)}
          >
            <Link to="/" className="sidebarBrand" title={collapsed ? 'Telegram Snowball' : undefined}>
              <img className="brandIcon" src={brandIcon} alt="" width={22} height={22} />
              <span>Telegram Snowball</span>
            </Link>
            <nav className="sidebarNav" aria-label="Main">
              <NavLink
                to="/"
                end
                title={collapsed ? 'Home' : undefined}
                className={({ isActive }) => `navLink${isActive ? ' active' : ''}`}
              >
                <span className="navIcon">
                  <House size={16} strokeWidth={1.75} aria-hidden />
                </span>
                <span className="navLabel">Home</span>
              </NavLink>
              <NavLink
                to={catalogTo}
                title={collapsed ? 'Catalog' : undefined}
                className={() => `navLink${onCatalog ? ' active' : ''}`}
              >
                <span className="navIcon">
                  <Library size={16} strokeWidth={1.75} aria-hidden />
                </span>
                <span className="navLabel">Catalog</span>
              </NavLink>
              <NavLink
                to="/graph"
                title={collapsed ? 'Graph' : undefined}
                className={({ isActive }) => `navLink${isActive ? ' active' : ''}`}
              >
                <span className="navIcon">
                  <Share2 size={16} strokeWidth={1.75} aria-hidden />
                </span>
                <span className="navLabel">Graph</span>
              </NavLink>
            </nav>
            <div className="sidebarEnd">
              {account ? (
                <div className="sidebarAccount" title={collapsed ? accountName ?? undefined : undefined}>
                  <AccountAvatar
                    photoUrl={account.photo_url}
                    mediaKind={account.photo_media_kind}
                    name={accountName ?? ''}
                    size="sm"
                  />
                  <span className="sidebarAccountName">{accountName}</span>
                </div>
              ) : null}
              <MobileNav
                leadingLinks={[{ label: 'Home', href: '/', end: true }]}
                groups={[]}
                links={[
                  { label: 'Catalog', href: catalogTo, isActive: onCatalog },
                  { label: 'Graph', href: '/graph' },
                ]}
              />
            </div>
          </div>
        </aside>
        <div className="mainPane">
          {onCatalog ? (
            <>
              <nav className="catalogNav" aria-label="Catalog">
                {catalogTabs.map((tab) => (
                  <NavLink
                    key={tab.to}
                    to={tab.to}
                    end
                    className={({ isActive }) => `catalogNavLink${isActive ? ' active' : ''}`}
                  >
                    <tab.icon size={14} strokeWidth={1.75} aria-hidden />
                    {tab.label}
                  </NavLink>
                ))}
              </nav>
              <CatalogStorageBar />
            </>
          ) : null}
          <main className={`content${onGraph ? ' contentFlush' : ''}`}>
            <Outlet />
          </main>
          <GraphKeepAlive active={onGraph} />
        </div>
      </div>
    </div>
  )
}

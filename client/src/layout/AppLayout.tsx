import { NavLink, Outlet, useLocation } from 'react-router'
import brandIcon from '../assets/snowball-icon.png'
import { AccountAvatar } from '../components/AccountAvatar'
import { accountDisplayName } from '../lib/account'
import { useAppStatus } from './statusContext'

const links = [
  { to: '/', label: 'Home', end: true },
  {
    to: '/catalog/peers',
    label: 'Catalog',
    isActive: (pathname: string) => pathname.startsWith('/catalog'),
  },
  { to: '/graph', label: 'Graph' },
]

const catalogTabs = [
  { to: '/catalog/peers', label: 'Peers' },
  { to: '/catalog/images', label: 'Images' },
  { to: '/catalog/videos', label: 'Videos' },
]

function pageLabel(pathname: string) {
  if (pathname.startsWith('/catalog')) return 'Catalog'
  if (pathname.startsWith('/graph')) return 'Graph'
  if (pathname.startsWith('/jobs')) return 'Job'
  return 'Home'
}

export function AppLayout() {
  const { pathname } = useLocation()
  const onCatalog = pathname.startsWith('/catalog')
  const status = useAppStatus()
  const account = status?.account ?? null
  const accountName = account ? accountDisplayName(account) : null

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbarBrand">
          <img className="brandIcon" src={brandIcon} alt="" width={22} height={22} />
          <span>Telegram Snowball</span>
        </div>
        <div className="topbarMain">
          <div className="topbarNav">
            <span className="topbarTitle">{pageLabel(pathname)}</span>
            {onCatalog ? (
              <nav className="pageTabs" aria-label="Catalog">
                {catalogTabs.map((tab) => (
                  <NavLink
                    key={tab.to}
                    to={tab.to}
                    end
                    className={({ isActive }) => `pageTab${isActive ? ' active' : ''}`}
                  >
                    {tab.label}
                  </NavLink>
                ))}
              </nav>
            ) : null}
          </div>
          {account ? (
            <span className="topbarAccount">
              <AccountAvatar
                photoUrl={account.photo_url}
                mediaKind={account.photo_media_kind}
                name={accountName ?? ''}
                size="sm"
              />
              <span className="topbarAccountName">{accountName}</span>
            </span>
          ) : null}
        </div>
      </header>
      <div className="bodyRow">
        <aside className="sidebar">
          <nav className="sidebarNav" aria-label="Main">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `navLink${(link.isActive ? link.isActive(pathname) : isActive) ? ' active' : ''}`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

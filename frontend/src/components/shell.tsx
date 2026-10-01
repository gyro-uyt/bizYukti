'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, type ReactNode } from 'react'
import { Bell, Bookmark, ClipboardList, Compass, Gift, House, LayoutDashboard, Map as MapIcon, MapPin, MessageSquare, Plus } from 'lucide-react'
import { canUse, type Feature } from '@/lib/access'
import { useAuth } from '@/lib/auth'
import { num } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import { AiAssistant } from './ai-assistant'
import { Logo } from './brand'
import { LocationPicker } from './location-picker'

export { Logo } from './brand'

const NAV: { href: string; label: string; short?: string; icon: typeof House; feature?: Feature }[] = [
  { href: '/home', label: 'Home', icon: House },
  { href: '/explore', label: 'Explore', icon: Compass, feature: 'explore' },
  { href: '/map', label: 'Map', icon: MapIcon, feature: 'map' },
  { href: '/neighbourhood', label: 'Map', icon: MapIcon, feature: 'neighbourhood' },
  { href: '/demands/mine', label: 'My activity', short: 'Activity', icon: ClipboardList, feature: 'activity' },
  { href: '/saved', label: 'Saved', icon: Bookmark, feature: 'saved' },
  // On desktop this renders as the pink button beside rewards/location (see topbar-right), not in the tab row.
  { href: '/post', label: 'Post', icon: Plus, feature: 'post' },
]
const MOBILE_MAX = 4

export function AppShell({ children, wide }: { children: ReactNode; wide?: boolean }) {
  const path = usePathname() || '/'
  const { user } = useAuth()
  const { loc } = useLocation()
  const [picking, setPicking] = useState(false)
  const active = (href: string) => path === href || path.startsWith(`${href}/`)
  const nav = NAV.filter((n) => !n.feature || canUse(user, n.feature))
  // The bottom bar holds four items; Map gives way first when a role sees all five.
  const mobile = nav.length > MOBILE_MAX ? nav.filter((n) => n.href !== '/map') : nav
  // Residents get their points in the top bar; their location button lives on the home screen instead.
  const showPost = nav.some((n) => n.href === '/post')
  const rewardsTop = canUse(user, 'rewards.topbar')
  const rewards = useApi<{ balance: number }>(user && rewardsTop ? '/rewards' : null)
  const initials = (user?.name || user?.display_name || '?').split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  const unread = user?.unread_notifications || 0
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href={user ? '/home' : '/'} aria-label="BizYukti home" className="logo"><Logo /></Link>
          <nav className="topnav" aria-label="Main">
            {nav.filter((n) => n.href !== '/post').map((n) => (
              <Link key={n.href} href={n.href} className={active(n.href) ? 'is-active' : ''} aria-current={active(n.href) ? 'page' : undefined}>{n.label}</Link>
            ))}
          </nav>
          <div className="topbar-right">
            {rewardsTop ? (
              <Link href="/rewards" className={`loc-btn reward-top${active('/rewards') ? ' is-active' : ''}`} aria-label={`Rewards${rewards.data ? `: ${rewards.data.balance} points` : ''}`}>
                <Gift size={16} aria-hidden /><span>{rewards.data ? `${num(rewards.data.balance)} points` : 'Rewards'}</span>
              </Link>
            ) : (
              <button type="button" className="loc-btn" onClick={() => setPicking(true)} aria-label={`Location: ${loc.label}. Change location`}>
                <MapPin size={16} aria-hidden /><span>{loc.label}</span>
              </button>
            )}
            {showPost ? (
              <Link href="/post" className={`post-btn hide-mobile${active('/post') ? ' is-active' : ''}`} aria-current={active('/post') ? 'page' : undefined}>
                <Plus size={18} strokeWidth={3} aria-hidden />Post
              </Link>
            ) : null}
            {user ? (
              <>
                {user.roles.includes('admin') ? <Link href="/admin" className="icon-btn hide-mobile" aria-label="Admin review"><LayoutDashboard size={20} /></Link> : null}
                <Link href="/inquiries" className="icon-btn hide-mobile" aria-label={`Messages${user.unread_messages ? `, ${user.unread_messages} unread` : ''}`}>
                  <MessageSquare size={20} />{user.unread_messages ? <span className="dot" /> : null}
                </Link>
                <Link href="/notifications" className="icon-btn" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}>
                  <Bell size={20} />{unread ? <span className="count">{unread > 9 ? '9+' : unread}</span> : null}
                </Link>
                <Link href="/profile" className="avatar" aria-label="Your profile">{initials}</Link>
              </>
            ) : (
              <Link href={`/login?next=${encodeURIComponent(path)}`} className="btn btn-primary btn-sm">Sign in</Link>
            )}
          </div>
        </div>
      </header>
      <main id="main" className={wide ? 'main main-wide' : 'main'}>{children}</main>
      <nav className="bottomnav" aria-label="Main" style={{ gridTemplateColumns: `repeat(${mobile.length}, 1fr)` }}>
        {mobile.map((n) => (
          <Link key={n.href} href={n.href} className={`${active(n.href) ? 'is-active' : ''}${n.href === '/post' ? ' is-post' : ''}`}
            aria-current={active(n.href) ? 'page' : undefined}>
            <n.icon size={22} aria-hidden />{n.short || n.label}
          </Link>
        ))}
      </nav>
      <LocationPicker open={picking} onClose={() => setPicking(false)} />
      {/* Hidden on the full-screen map, where the list rail already holds the same information. */}
      {user && canUse(user, 'assistant') && !active('/neighbourhood') ? <AiAssistant user={user} /> : null}
    </>
  )
}

'use client'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ChevronRight, Flame, MapPin, Search, ShieldCheck } from 'lucide-react'
import { SpaceCard } from '@/components/cards'
import { AppShell } from '@/components/shell'
import { Empty, LinkButton, PageHeader, Segmented, Skeleton, Tabs } from '@/components/ui'
import OrbitCarousel, { type OrbitItem } from '@/components/ui/orbiting-carousel-with-animated-icons'
import { canUse, type Feature } from '@/lib/access'
import { useAuth } from '@/lib/auth'
import { CATEGORY_PHOTOS, categoryIcon } from '@/lib/category-media'
import { num } from '@/lib/format'
import { useApi, useDebounced } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { AreaRef, Demand, Paged, Space } from '@/lib/types'

// 'top' ranks the whole city by verified supporters; 'near' lists requests around the chosen location, nearest first;
// 'spotlight' shows the city's top requests in an orbiting carousel.
type Tab = 'top' | 'near' | 'spotlight' | 'spaces' | 'areas'
const TABS: Tab[] = ['top', 'near', 'spotlight', 'spaces', 'areas']
const FEATURE: Record<Tab, Feature> = { top: 'explore.requests', near: 'explore.requests', spotlight: 'explore.requests', spaces: 'explore.spaces', areas: 'explore.areas' }
const SPOTLIGHT_COUNT = 8
const NEAR_KM = 10
// Requests at or above this many verified supporters are marked as high demand.
const HIGH_DEMAND = 50
const BANDS = [{ max: 1000, label: 'Within 1 km' }, { max: 3000, label: '1 to 3 km' }, { max: 5000, label: '3 to 5 km' }, { max: Infinity, label: '5 to 10 km' }]

function fromParam(v: string | null): Tab {
  if (v === 'requests') return 'top' // links from before the split
  return TABS.includes(v as Tab) ? (v as Tab) : 'top'
}

function distanceLead(m: number | null): ReactNode {
  if (m == null) return null
  return m >= 1000 ? <>{(m / 1000).toFixed(1)}<small>km</small></> : <>{Math.max(10, Math.round(m / 10) * 10)}<small>m</small></>
}

/** One request: lead (rank or distance), name with a quiet detail line, and supporters with a relative bar. */
function ExploreRow({ d, lead, top, max }: { d: Demand; lead: ReactNode; top?: boolean; max: number }) {
  const hot = d.supporters >= HIGH_DEMAND
  const status = d.status === 'fulfilled' ? { text: 'Opened', cls: 'is-ok' } : d.status === 'matched' ? { text: 'Business interested', cls: 'is-blue' } : null
  return (
    <li>
      <Link href={`/demands/${d.id}`} className={`ex-row${hot ? ' is-hot' : ''}`}>
        <span className={`ex-lead${top ? ' is-top' : ''}`} aria-hidden>{lead}</span>
        <span className="ex-main">
          <span className="ex-title">{d.title}{d.verified ? <ShieldCheck size={15} aria-label="Verified local demand" /> : null}</span>
          <span className="ex-sub">
            <span>{d.locality}</span>
            {d.category_name.toLowerCase() !== d.title.toLowerCase() ? <span>{d.category_name}</span> : null}
            {status ? <span className={status.cls}>{status.text}</span> : null}
            {d.my_support === 'verified' ? <span className="is-blue">You support this</span> : null}
          </span>
        </span>
        <span className="ex-demand">
          <span className="ex-count">{hot ? <Flame size={15} aria-hidden /> : null}{num(d.supporters)}
            <span className="sr-only"> verified supporters{hot ? ', high demand' : ''}</span></span>
          <span className="ex-bar" aria-hidden><span style={{ width: `${Math.max(3, (d.supporters / max) * 100)}%` }} /></span>
        </span>
      </Link>
    </li>
  )
}

export default function Explore() {
  const params = useSearchParams()
  const router = useRouter()
  const { user } = useAuth()
  const { loc, categories } = useLocation()
  const visible = TABS.filter((t) => canUse(user, FEATURE[t]))
  const [picked, setTab] = useState<Tab>(fromParam(params.get('tab')))
  const tab = visible.includes(picked) ? picked : visible[0]
  const [q, setQ] = useState(params.get('q') || '')
  const [cat, setCat] = useState(params.get('category') || '')
  const [show, setShow] = useState<'all' | 'hot'>('all')
  const dq = useDebounced(q, 300)
  const center = { lat: loc.lat, lng: loc.lng }
  const isRequests = tab === 'top' || tab === 'near'
  const demands = useApi<Paged<Demand> & { city: string | null }>(isRequests ? '/demands' : null, tab === 'top'
    ? { ...center, scope: 'city', q: dq, category: cat, sort: 'support', limit: 50 }
    : { ...center, radius_km: NEAR_KM, q: dq, category: cat, sort: 'near', limit: 50 })
  const spot = useApi<Paged<Demand> & { city: string | null }>(tab === 'spotlight' ? '/demands' : null,
    { ...center, scope: 'city', q: dq, category: cat, sort: 'support', limit: SPOTLIGHT_COUNT })
  const spaces = useApi<Paged<Space>>(tab === 'spaces' ? '/properties' : null, { ...center, radius_km: NEAR_KM, category: cat, limit: 40 })
  const areas = useApi<AreaRef[]>(tab === 'areas' ? '/geo/areas' : null, { q: dq })
  const [city, setCity] = useState<string | null>(null)
  useEffect(() => { const c = demands.data?.city || spot.data?.city; if (c) setCity(c) }, [demands.data?.city, spot.data?.city])
  const cityName = city || 'your city'
  const orbitItems: OrbitItem[] = useMemo(() => (spot.data?.items || []).map((d, i) => {
    const { icon, tone } = categoryIcon(d.category)
    const hot = d.supporters >= HIGH_DEMAND
    return {
      id: d.id, title: d.title, href: `/demands/${d.id}`, icon, tone, image: CATEGORY_PHOTOS[d.category],
      eyebrow: `#${i + 1} in ${cityName}`, subtitle: d.locality, stat: num(d.supporters), statLabel: d.supporters === 1 ? 'supporter' : 'supporters',
      badge: hot || d.verified ? (
        <span className="orb-tags">
          {hot ? <span className="orb-tag is-hot"><Flame size={12} aria-hidden /> High demand</span> : null}
          {d.verified ? <span className="orb-tag is-ok"><ShieldCheck size={12} aria-hidden /> Verified</span> : null}
        </span>
      ) : undefined,
      cta: 'View request',
    }
  }), [spot.data, cityName])

  useEffect(() => {
    const sp = new URLSearchParams()
    if (tab !== 'top') sp.set('tab', tab)
    if (dq) sp.set('q', dq)
    if (cat) sp.set('category', cat)
    const s = sp.toString()
    router.replace(s ? `/explore?${s}` : '/explore', { scroll: false })
  }, [tab, dq, cat, router])

  const items = demands.data?.items || []
  const max = Math.max(1, ...items.map((d) => d.supporters))
  const hotCount = items.filter((d) => d.supporters >= HIGH_DEMAND).length
  const shown = show === 'hot' ? items.filter((d) => d.supporters >= HIGH_DEMAND) : items
  const bands = tab === 'near'
    ? BANDS.map((b, i) => ({ ...b, items: shown.filter((d) => (d.distance_m ?? 0) < b.max && (d.distance_m ?? 0) >= (i ? BANDS[i - 1].max : 0)) })).filter((b) => b.items.length)
    : [{ label: '', items: shown }]
  const sub = tab === 'top' ? `The most supported requests across ${cityName}.`
    : tab === 'near' ? `Requests within ${NEAR_KM} km of ${loc.label}, nearest first.`
      : tab === 'spotlight' ? `The ${SPOTLIGHT_COUNT} most wanted requests across ${cityName}, in orbit.`
      : tab === 'spaces' ? `Available spaces within ${NEAR_KM} km of ${loc.label}.` : 'Browse areas and their opportunities.'

  return (
    <AppShell>
      <div className="container stack">
        <PageHeader title="Explore" sub={sub} />
        <div className="row">
          <div className="search" style={{ flex: '1 1 320px' }}>
            <Search size={20} aria-hidden />
            <input aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={tab === 'areas' ? 'Search areas' : 'Search requests, e.g. bakery'} />
          </div>
          {tab !== 'areas' ? (
            <>
              <label className="sr-only" htmlFor="cat">Category</label>
              <select id="cat" className="input" style={{ maxWidth: 240, height: 56 }} value={cat} onChange={(e) => setCat(e.target.value)}>
                <option value="">All categories</option>
                {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
            </>
          ) : null}
        </div>
        <Tabs label="Explore" value={tab} onChange={setTab} tabs={([
          { key: 'top', label: `Top in ${city || 'city'}` },
          { key: 'near', label: 'Near you' },
          { key: 'spotlight', label: 'Spotlight' },
          { key: 'spaces', label: 'Spaces', count: spaces.data?.total },
          { key: 'areas', label: 'Areas' }] as { key: Tab; label: string; count?: number }[]).filter((t) => visible.includes(t.key))} />

        {isRequests ? (demands.loading ? <Skeleton rows={6} height={64} /> : items.length ? (
          <>
            <div className="ex-toolbar">
              <p className="meta">{num(demands.data?.total || 0)} {demands.data?.total === 1 ? 'request' : 'requests'} · {tab === 'top' ? 'ranked by verified supporters' : 'nearest first'}</p>
              {hotCount ? <Segmented label="Show" value={show} onChange={setShow}
                options={[{ key: 'all', label: 'All' }, { key: 'hot', label: `High demand (${hotCount})` }]} /> : null}
            </div>
            <div className="ex-card">
              <div className="ex-head" aria-hidden><span>{tab === 'top' ? 'Rank' : 'Away'}</span><span>Request</span><span>Supporters</span></div>
              {bands.map((b) => (
                <section key={b.label || 'all'} aria-label={b.label || undefined}>
                  {b.label ? <h3 className="ex-band">{b.label}<span>{b.items.length}</span></h3> : null}
                  <ol className="ex-list">
                    {b.items.map((d) => (
                      <ExploreRow key={d.id} d={d} max={max}
                        top={tab === 'top' && items.indexOf(d) < 3}
                        lead={tab === 'top' ? items.indexOf(d) + 1 : distanceLead(d.distance_m)} />
                    ))}
                  </ol>
                </section>
              ))}
            </div>
            <p className="meta ex-legend"><Flame size={13} aria-hidden /> High demand: {num(HIGH_DEMAND)}+ verified supporters
              {demands.data && demands.data.total > items.length ? ` · Showing the top ${num(items.length)} of ${num(demands.data.total)}` : ''}</p>
          </>
        ) : (
          <Empty title="Nothing matches yet" body={tab === 'near' ? `No requests within ${NEAR_KM} km match. Try Top in ${cityName}, or be the first to ask.` : 'Try another word, or be the first to ask for it.'}
            action={canUse(user, 'demand.create') ? <LinkButton href="/demands/new">Request a business</LinkButton> : undefined} />
        )) : null}

        {tab === 'spotlight' ? (spot.loading ? <Skeleton rows={1} height={460} /> : orbitItems.length ? (
          <div className="stack-sm">
            <OrbitCarousel items={orbitItems} label={`Top requests in ${cityName}`} />
            <p className="meta" style={{ textAlign: 'center' }}>Tap a circle, or focus the carousel and use the arrow keys. It turns every 5 seconds and pauses while you look.{' '}
              <button type="button" className="link" onClick={() => setTab('top')}>See the full ranking</button></p>
          </div>
        ) : (
          <Empty title="Nothing to spotlight yet" body="No live requests match. Try another word or category."
            action={canUse(user, 'demand.create') ? <LinkButton href="/demands/new">Request a business</LinkButton> : undefined} />
        )) : null}

        {tab === 'spaces' ? (spaces.loading ? <Skeleton rows={3} height={220} /> : spaces.data?.items.length
          ? <div className="grid-cards">{spaces.data.items.map((s) => <SpaceCard key={s.id} s={s} />)}</div>
          : <Empty title="No spaces listed here yet" body="Owners nearby can list a space in a few minutes." action={canUse(user, 'property.create') ? <LinkButton href="/properties/new" variant="secondary">List a space</LinkButton> : undefined} />) : null}
        {tab === 'areas' ? (areas.loading ? <Skeleton rows={5} /> : (
          <ul className="rows">
            {(areas.data || []).map((a) => (
              <li key={a.id}><Link href={`/opportunities/${a.id}${cat ? `?category=${cat}` : ''}`} className="row-link">
                <span className="row-icon ci-blue"><MapPin size={18} aria-hidden /></span>
                <span><span className="row-title">{a.name}</span><span className="row-meta"><span>{a.city}</span></span></span>
                <ChevronRight size={20} aria-hidden />
              </Link></li>
            ))}
          </ul>
        )) : null}
      </div>
    </AppShell>
  )
}

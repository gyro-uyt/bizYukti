'use client'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'
import { ArrowRight, Gift, MapPin, PartyPopper, Search } from 'lucide-react'
import { DemandRow, StatusBadge } from '@/components/cards'
import { LocationPicker } from '@/components/location-picker'
import { MapView } from '@/components/map'
import { Badge, LinkButton, Notice, Progress, Skeleton } from '@/components/ui'
import { date, firstName, greeting, num, plural } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { AppConfig, Demand, Me, Paged } from '@/lib/types'

type Cat = { category: string; name: string; supporters: number; demands: number }
type Week = { week: string; supporters: number }
type Feed = {
  center: { lat: number; lng: number; locality: string; radius_km: number }
  stats: { live_requests: number; supporters: number; new_supporters_14d: number; opened: number }
  categories: Cat[]; trend: Week[]; opened: Demand[]
  me: { created: number; supported: number }
}
type Rewards = { balance: number; pending: number; lifetime: number; tier: { name: string; next_name: string | null; next_at: number | null; progress: number } }
type Mine = { created: (Demand & { matched_spaces: number })[] }

export default function ResidentHome({ user }: { user: Me }) {
  const router = useRouter()
  const { loc, config } = useLocation()
  const [q, setQ] = useState('')
  const [picking, setPicking] = useState(false)
  const feed = useApi<Feed>('/demands/for-you', { lat: loc.lat, lng: loc.lng })
  const rewards = useApi<Rewards>('/rewards')
  const mine = useApi<Mine>('/demands/mine')
  const nearby = useApi<Paged<Demand>>('/demands', { lat: loc.lat, lng: loc.lng, sort: 'support', limit: 5 })
  const f = feed.data

  return (
    <div className="stack-lg">
      {user.roles.includes('admin') ? <Notice tone="info">You have admin access. <Link href="/admin">Open the review queue</Link>.</Notice> : null}

      {/* 1. Hero + neighbourhood pulse */}
      <section className="rh-hero">
        <div className="home-hero">
          <p className="meta">{greeting()}, {firstName(user.name)}</p>
          <h1 className="display-sm">What&apos;s missing near {loc.label}?</h1>
          <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); router.push(`/explore?q=${encodeURIComponent(q)}`) }}>
            <Search size={20} aria-hidden />
            <input aria-label="Search local requests" placeholder="Pharmacy, café, gym…" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <div className="row">
            <LinkButton href="/demands/new" variant="pink" size="lg">Request a business</LinkButton>
            <button type="button" className="reward-link loc-link" onClick={() => setPicking(true)} aria-label={`Location: ${loc.label}. Change location`}>
              <MapPin size={20} aria-hidden /><span>{loc.label}</span>
            </button>
          </div>
          <LocationPicker open={picking} onClose={() => setPicking(false)} />
        </div>
        <aside className="rh-pulse" aria-labelledby="pulse-h">
          <p className="rh-eyebrow" id="pulse-h">Your neighbourhood today</p>
          {f ? (
            <div className="rh-pulse-grid">
              <PulseStat value={f.stats.live_requests} label="open requests" />
              <PulseStat value={f.stats.supporters} label="verified supporters" />
              <PulseStat value={f.stats.new_supporters_14d} label="joined in 2 weeks" accent />
              <PulseStat value={f.stats.opened} label="businesses opened" />
            </div>
          ) : <Skeleton rows={2} height={56} />}
          <p className="meta">Within {f?.center.radius_km ?? 5} km of {loc.label}</p>
        </aside>
      </section>

      {/* 2. Personal impact */}
      <section className="rh-impact" aria-label="Your impact">
        <Link href="/rewards" className="rh-tile">
          <span className="rh-tile-label"><Gift size={16} aria-hidden /> Points</span>
          <span className="rh-tile-value">{rewards.data ? num(rewards.data.balance) : '–'}</span>
          <span className="meta">{rewards.data?.pending ? `${num(rewards.data.pending)} pending verification` : 'Ready to redeem'}</span>
        </Link>
        <Link href="/rewards" className="rh-tile">
          <span className="rh-tile-label">Level</span>
          <span className="rh-tile-value rh-tile-text">{rewards.data?.tier.name || '–'}</span>
          {rewards.data?.tier.next_name ? (
            <span className="stack-sm" style={{ gap: 6 }}>
              <Progress value={rewards.data.tier.progress} light />
              <span className="meta">{num(Math.max(0, (rewards.data.tier.next_at || 0) - rewards.data.lifetime))} points to {rewards.data.tier.next_name}</span>
            </span>
          ) : <span className="meta">Top level reached</span>}
        </Link>
        <Link href="/demands/mine" className="rh-tile">
          <span className="rh-tile-label">Requests you made</span>
          <span className="rh-tile-value">{f ? num(f.me.created) : '–'}</span>
          <span className="meta">Track them in My activity</span>
        </Link>
        <Link href="/demands/mine" className="rh-tile">
          <span className="rh-tile-label">Requests you back</span>
          <span className="rh-tile-value">{f ? num(f.me.supported) : '–'}</span>
          <span className="meta">Each one makes local demand stronger</span>
        </Link>
      </section>

      {/* 3. Charts (recommendations and the insight live in the floating AI assistant) */}
      <section className="stack">
        <h2 className="h2">What your neighbours want</h2>
        <div className="grid-2">
          <div className="blockbox accent-pink">
            <div><h3 className="h3">Most wanted near {loc.label}</h3><p className="meta">Verified supporters by business type, within {f?.center.radius_km ?? 5} km</p></div>
            {f ? <CategoryBars cats={f.categories} /> : <Skeleton rows={4} height={28} />}
          </div>
          <div className="blockbox accent-pink">
            <div><h3 className="h3">Support momentum</h3>
              <p className="meta">{f ? <>New verified supporters each week. <strong>{num(f.stats.new_supporters_14d)}</strong> in the last two weeks.</> : 'Loading…'}</p></div>
            {f ? <TrendChart series={f.trend} /> : <Skeleton rows={1} height={180} />}
          </div>
        </div>
      </section>

      {/* 5. Feature cards */}
      <section className="stack">
        <h2 className="h2">Make your neighbourhood better</h2>
        <div className="rh-features">
          <FeatureCard href="/explore" img="/landing/verified-demand.webp" tone="green" title="Back local demand"
            body={`Your support counts when you live within ${config?.trust.local_radius_km ?? 5} km. One tap adds your voice.`} cta="Explore requests" />
          <FeatureCard href="/demands/mine" img="/landing/fresh-spaces.webp" tone="orange" title="Watch it open"
            body="Follow each request from posted to verified, growing and opened." cta="My activity" />
          <FeatureCard href="/rewards" img="/landing/rewards.webp" tone="blue" title="Earn rewards"
            body={rewards.data ? `You have ${num(rewards.data.balance)} points. Redeem them for local vouchers.` : 'Earn points as your requests grow and open.'} cta="See rewards" />
          <Link href="/neighbourhood" className="rh-feature rh-feature-map">
            <div className="rh-feature-media rh-mini-map" aria-hidden>
              <MapView center={loc} zoom={13} height={150} ariaLabel="Preview of your neighbourhood map"
                points={[{ id: 'me', lat: loc.lat, lng: loc.lng, kind: 'me', label: loc.label },
                  ...(nearby.data?.items || []).map((d) => ({ id: d.id, lat: d.lat, lng: d.lng, kind: 'demand' as const, label: d.title }))]} />
            </div>
            <div className="rh-feature-body"><h3 className="h3">See it on the map</h3>
              <p className="meta">Every request around you, ranked by neighbours.</p>
              <span className="link-quiet row">Open the map <ArrowRight size={16} aria-hidden /></span></div>
          </Link>
        </div>
      </section>

      {/* 6. Your requests with progress */}
      <section className="stack">
        <div className="section-head"><h2 className="h2">Your requests</h2><Link href="/demands/mine" className="link-quiet">Manage</Link></div>
        {mine.loading ? <Skeleton rows={2} /> : mine.data?.created.length ? (
          <ul className="rows">{mine.data.created.slice(0, 3).map((d) => <MyRequest key={d.id} d={d} config={config} />)}</ul>
        ) : (
          <div className="rh-empty-cta">
            <div><h3 className="h3">You haven&apos;t asked for anything yet</h3><p className="meta">Tell neighbours what&apos;s missing. It takes under a minute, and you earn up to {config?.rewards.demand_max_points ?? 150} points.</p></div>
            <LinkButton href="/demands/new" variant="pink">Request a business</LinkButton>
          </div>
        )}
      </section>

      {/* 7. Opened nearby */}
      {f?.opened.length ? (
        <section className="stack">
          <h2 className="h2 row"><PartyPopper size={22} className="rh-party" aria-hidden /> Opened thanks to neighbours</h2>
          <div className="rh-opened">{f.opened.map((d) => (
            <Link key={d.id} href={`/demands/${d.id}`} className="rh-opened-card">
              <Badge tone="verified">Opened</Badge>
              <span className="row-title">{d.display_title}</span>
              <span className="meta">{plural(d.supporters, 'neighbour')} asked for it{d.fulfilled_at ? `. Opened ${date(d.fulfilled_at)}` : ''}</span>
            </Link>))}</div>
        </section>
      ) : null}

      {/* 8. Ranked nearby demand */}
      <section>
        <div className="section-head"><h2 className="h2">Top requests nearby</h2><Link href="/explore" className="link-quiet">See all</Link></div>
        <p className="meta" style={{ marginBottom: 12 }}>Ranked by verified supporters within 5 km of {loc.label}</p>
        {nearby.loading ? <Skeleton rows={4} /> : nearby.data?.items.length
          ? <ol className="rows">{nearby.data.items.map((d, i) => <DemandRow key={d.id} d={d} rank={i + 1} />)}</ol>
          : <p className="meta">No requests nearby yet. Be the first to ask for something your area needs.</p>}
      </section>
    </div>
  )
}

function PulseStat({ value, label, accent }: { value: number; label: string; accent?: boolean }) {
  return <div className={`rh-pulse-stat${accent ? ' is-accent' : ''}`}><span className="num">{accent && value ? '+' : ''}{num(value)}</span><span>{label}</span></div>
}

function FeatureCard({ href, img, tone, title, body, cta }: { href: string; img: string; tone: 'green' | 'orange' | 'blue'; title: string; body: string; cta: string }) {
  return (
    <Link href={href} className="rh-feature">
      <div className={`rh-feature-media ci-${tone}`}><img src={img} alt="" aria-hidden /></div>
      <div className="rh-feature-body"><h3 className="h3">{title}</h3><p className="meta">{body}</p>
        <span className="link-quiet row">{cta} <ArrowRight size={16} aria-hidden /></span></div>
    </Link>
  )
}

function MyRequest({ d, config }: { d: Demand & { matched_spaces: number }; config: AppConfig | null }) {
  const need = (config?.trust.verify_min_supporters ?? 3) + 1
  const grow = config?.trust.growing_threshold ?? 10
  const step = d.status === 'fulfilled' ? { v: 1, text: 'Opened. Thanks for asking!' }
    : d.status === 'matched' ? { v: 0.85, text: 'A business is interested' }
      : !d.verified ? { v: Math.min(1, d.supporters / need) * 0.33, text: `${num(d.supporters)} of ${need} supporters to verify` }
        : d.status === 'growing' ? { v: 0.66, text: 'Growing. Waiting for a business to show interest' }
          : { v: 0.33 + Math.min(1, d.supporters / grow) * 0.33, text: `${num(d.supporters)} of ${grow} supporters to reach Growing` }
  return (
    <li><Link href={`/demands/${d.id}`} className="row-link">
      <span aria-hidden />
      <span className="stack-sm" style={{ gap: 6 }}>
        <span className="row-title">{d.display_title}</span>
        <span className="row-meta"><StatusBadge status={d.status} /><span>{plural(d.matched_spaces, 'matched space')}</span></span>
        <span className="rh-progress"><Progress value={step.v} light /><span className="meta">{step.text}</span></span>
      </span>
      <span className="row-count"><strong>{num(d.supporters)}</strong><span>supporters</span></span>
    </Link></li>
  )
}

/** Horizontal bars, one hue (magnitude). Each row links to Explore filtered by that category. */
function CategoryBars({ cats }: { cats: Cat[] }) {
  const [hover, setHover] = useState<string | null>(null)
  if (!cats.length) return <p className="meta">No requests near this location yet.</p>
  const max = Math.max(...cats.map((c) => c.supporters), 1)
  return (
    <ul className="rh-bars">
      {cats.map((c) => (
        <li key={c.category}>
          <Link href={`/explore?category=${c.category}`} className="rh-bar-row" onMouseEnter={() => setHover(c.category)} onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(c.category)} onBlur={() => setHover(null)}
            aria-label={`${c.name}: ${num(c.supporters)} verified supporters across ${plural(c.demands, 'request')}`}>
            <span className="rh-bar-name">{c.name}</span>
            <span className="rh-bar-track"><span className="rh-bar" style={{ width: `${Math.max(2, (c.supporters / max) * 100)}%` }} /></span>
            <span className="rh-bar-value">{num(c.supporters)}</span>
            {hover === c.category ? <span className="rh-tip" role="tooltip">{num(c.supporters)} verified supporters · {plural(c.demands, 'request')}</span> : null}
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Weekly columns, one hue. Hover or focus a week for its exact value. */
function TrendChart({ series }: { series: Week[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 560, H = 200, padL = 34, padB = 26, padT = 12
  const max = Math.max(...series.map((s) => s.supporters), 1)
  const nice = useMemo(() => { const p = Math.pow(10, Math.floor(Math.log10(max))); return Math.ceil(max / p) * p }, [max])
  const slot = (W - padL) / series.length
  const bw = Math.min(40, slot - 10)
  const y = (v: number) => H - padB - (v / nice) * (H - padB - padT)
  const label = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  const h = hover != null ? series[hover] : null
  return (
    <div className="rh-trend">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Weekly new verified supporters for the last ${series.length} weeks: ${series.map((s) => s.supporters).join(', ')}`}>
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={padL} x2={W} y1={y(nice * t)} y2={y(nice * t)} className={t === 0 ? 'rh-axis' : 'rh-grid'} />
            <text x={padL - 6} y={y(nice * t) + 4} textAnchor="end" className="rh-tick">{num(Math.round(nice * t))}</text>
          </g>
        ))}
        {series.map((s, i) => {
          const x = padL + i * slot + (slot - bw) / 2
          const top = y(s.supporters)
          const hgt = Math.max(0, H - padB - top)
          return (
            <g key={s.week} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} tabIndex={0} onFocus={() => setHover(i)} onBlur={() => setHover(null)}
              aria-label={`Week of ${label(s.week)}: ${s.supporters} new supporters`}>
              <rect x={padL + i * slot} y={padT} width={slot} height={H - padB - padT} fill="transparent" />
              {hgt > 0 ? <path className={`rh-col${hover === i ? ' is-hover' : ''}`}
                d={`M${x},${H - padB} V${top + Math.min(4, hgt)} q0,-4 4,-4 H${x + bw - 4} q4,0 4,4 V${H - padB} Z`} /> : null}
              {i % 2 === series.length % 2 || i === series.length - 1
                ? <text x={x + bw / 2} y={H - 8} textAnchor="middle" className="rh-tick">{i === series.length - 1 ? 'This week' : label(s.week)}</text> : null}
            </g>
          )
        })}
      </svg>
      {h && hover != null ? (
        <div className="rh-tip rh-tip-chart" role="tooltip" style={{ left: `${((padL + hover * slot + slot / 2) / W) * 100}%` }}>
          <strong>{num(h.supporters)}</strong> new supporters<br /><span className="meta">Week of {label(h.week)}</span>
        </div>
      ) : null}
    </div>
  )
}

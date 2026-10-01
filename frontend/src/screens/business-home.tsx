'use client'
// B1 business home: where to open next, with the competitor-gap and feasibility verdicts for the best area up front.
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, Bookmark, Briefcase, CheckCircle2, MapPin, MessageSquare, ShieldCheck } from 'lucide-react'
import { AreaRow, SpaceCard } from '@/components/cards'
import { LocationPicker } from '@/components/location-picker'
import { MapView } from '@/components/map'
import { Badge, LinkButton, Notice, Segmented, Skeleton } from '@/components/ui'
import { http } from '@/lib/api'
import { greeting, inrShort, num } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { AreaOpp, Inquiry, Me, Paged, Space } from '@/lib/types'

type OppData = { areas: AreaOpp[]; strong_demand_areas: number; category_name: string; city: string; budget: number | null
  near?: { radius_km: number; all: boolean } | null }
type GapPreview = { verdict: { label: string; tone: string; score: number; summary: string }; metrics: { per_outlet: number; city_avg_per_outlet: number; competitors: number } }
type FeasPreview = { status: { label: string; tone: string; score: number }; expected: { profit: number; revenue: number }; payback_month: number | null; space: { title: string } }

export default function BusinessHome({ user }: { user: Me }) {
  const { categories, config, category, loc } = useLocation()
  const profile = user.business
  const [cat, setCat] = useState(profile?.categories?.[0] || 'pharmacy')
  const [view, setView] = useState<'list' | 'map'>('list')
  const [picking, setPicking] = useState(false)
  // 'near' ranks areas around the target location; 'city' ranks the whole city.
  const [scope, setScope] = useState<'near' | 'city'>('near')
  const [autoWide, setAutoWide] = useState(false)
  const city = profile?.preferred_cities?.[0] || config?.default_city
  const { data, loading } = useApi<OppData>('/opportunities', scope === 'near'
    ? { category: cat, city, lat: loc.lat, lng: loc.lng } : { category: cat, city })
  useEffect(() => { setScope('near'); setAutoWide(false) }, [cat, loc.lat, loc.lng])
  // Nothing verified nearby but the city may have demand: widen once, and say so.
  useEffect(() => {
    if (scope === 'near' && data?.near && !data.near.all && data.areas.every((a) => a.supporters === 0)) { setScope('city'); setAutoWide(true) }
  }, [data, scope])
  const best = data?.areas[0] && data.areas[0].supporters > 0 ? data.areas[0] : undefined
  const gap = useApi<GapPreview>(best ? '/reports/competitor-gap' : null, { area_id: best?.area.id, category: cat })
  const [feas, setFeas] = useState<FeasPreview | null>(null)
  useEffect(() => {
    setFeas(null)
    if (!best) return
    let live = true
    http.post<FeasPreview>('/reports/feasibility', { area_id: best.area.id, category: cat }).then((r) => { if (live) setFeas(r) }).catch(() => {})
    return () => { live = false }
  }, [best?.area.id, cat]) // eslint-disable-line react-hooks/exhaustive-deps
  const spaces = useApi<Paged<Space>>('/properties', { lat: loc.lat, lng: loc.lng, radius_km: 10, category: cat, budget: data?.budget || undefined, limit: 4 })
  const saved = useApi<{ areas: unknown[]; properties: unknown[] }>('/saved')
  const sent = useApi<{ items: Inquiry[] }>('/inquiries', { box: 'sent' })

  const noun = category(cat)?.noun || 'your business'
  const name = category(cat)?.name || 'business'
  const totals = useMemo(() => (data?.areas || []).reduce((t, a) => ({
    supporters: t.supporters + a.supporters, spaces: t.spaces + a.spaces, competitors: t.competitors + a.competitors,
  }), { supporters: 0, spaces: 0, competitors: 0 }), [data])
  const zones = useMemo(() => (data?.areas || []).map((a) => ({
    id: a.area.id, lat: a.area.lat, lng: a.area.lng, radius_m: a.area.radius_m, label: `${a.area.name}: ${a.label}, ${a.supporters} supporters`,
    intensity: a.tone === 'strong' ? 0.7 : a.tone === 'promising' ? 0.4 : 0.1, tone: (a.tone === 'strong' ? 'green' : a.tone === 'promising' ? 'demand' : 'blue') as 'green' | 'demand' | 'blue',
  })), [data])
  const briefs = (sent.data?.items || []).filter((i) => i.kind === 'market_brief').length
  const talks = (sent.data?.items || []).filter((i) => i.kind !== 'market_brief').length
  const areaHref = (id: string) => `/opportunities/${id}?category=${cat}`

  return (
    <div className="stack-lg">
      {!profile ? <Notice tone="info">Add your business details to tailor these results. <Link href="/profile">Set up your business</Link></Notice> : null}

      {/* 1. Hero + market snapshot */}
      <section className="rh-hero">
        <div className="home-hero">
          <p className="meta row" style={{ gap: 8 }}>{greeting()}{profile ? `, ${profile.name}` : ''}
            {profile?.verified ? <Badge tone="verified">Verified business</Badge> : null}</p>
          <h1 className="display-sm">{data ? <><span className="num">{data.strong_demand_areas}</span> {data.strong_demand_areas === 1 ? 'area' : 'areas'} with strong demand for {noun}</> : 'Finding where demand is strongest…'}</h1>
          <div className="row">
            <label className="sr-only" htmlFor="biz-cat">Business category</label>
            <select id="biz-cat" className="input" style={{ maxWidth: 260 }} value={cat} onChange={(e) => setCat(e.target.value)}>
              {categories.filter((c) => c.slug !== 'other').map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </select>
            <button type="button" className="reward-link loc-link" onClick={() => setPicking(true)} aria-label={`Target location: ${loc.label}. Change`}>
              <MapPin size={20} aria-hidden /><span>{loc.label}</span>
            </button>
            <LinkButton href={`/map?category=${cat}`} variant="ghost">Opportunity map <ArrowRight size={16} aria-hidden /></LinkButton>
          </div>
          <Segmented label="Areas to rank" value={scope} onChange={(v) => { setScope(v); setAutoWide(false) }}
            options={[{ key: 'near', label: `Near ${loc.label}` }, { key: 'city', label: `All of ${city || 'the city'}` }]} />
          {autoWide ? <p className="meta">No verified demand for {noun} within 3 km of {loc.label} yet, so these are the best areas across {data?.city || city}.</p>
            : data?.near ? <p className="meta">{data.near.all ? `No areas within ${data.near.radius_km} km of ${loc.label} yet, so all areas in ${data.city} are shown.` : `Areas within ${data.near.radius_km} km of ${loc.label}, ranked by opportunity.`}</p>
              : data ? <p className="meta">Every area in {data.city}, ranked by opportunity.</p> : null}
          {data?.budget ? <p className="meta">Spaces filtered to rent up to ₹{num(data.budget)} a month. Change this in your profile.</p> : null}
          <LocationPicker open={picking} onClose={() => setPicking(false)} title="Where do you want to open?" />
        </div>
        <aside className="rh-pulse" aria-labelledby="snap-h">
          <p className="rh-eyebrow" id="snap-h">Market snapshot · {name}</p>
          {data ? (
            <div className="rh-pulse-grid">
              <div className="rh-pulse-stat"><span className="num">{num(totals.supporters)}</span><span>verified residents asking</span></div>
              <div className="rh-pulse-stat is-accent"><span className="num">{num(data.strong_demand_areas)}</span><span>strong-demand areas</span></div>
              <div className="rh-pulse-stat"><span className="num">{num(totals.spaces)}</span><span>spaces that fit</span></div>
              <div className="rh-pulse-stat"><span className="num">{num(totals.competitors)}</span><span>existing outlets</span></div>
            </div>
          ) : <Skeleton rows={2} height={56} />}
          <p className="meta">{data ? `${data.areas.length} ${data.areas.length === 1 ? 'area' : 'areas'} ${scope === 'near' ? `near ${loc.label}, ${data.city}` : `across ${data.city}`}` : ' '}</p>
        </aside>
      </section>

      {/* 2. Best place to open, with both report verdicts */}
      {loading && !data ? <Skeleton rows={1} height={240} /> : best ? (
        <section className="blockbox accent-green bh-pick" aria-labelledby="pick-h">
          <div className="bh-pick-head">
            <span className="bh-rank" aria-hidden>#1</span>
            <div className="stack-sm" style={{ gap: 4 }}>
              <p className="br-eyebrow">Best place to open {noun}</p>
              <h2 className="h1" id="pick-h">{best.area.name}</h2>
              <span className="row" style={{ gap: 8 }}><Badge tone={best.tone}>{best.label}</Badge>
                <span className="meta">{num(best.supporters)} verified supporters · {best.spaces} {best.spaces === 1 ? 'space fits' : 'spaces fit'} · {best.competitors === 0 ? 'no competitors recorded' : `${best.competitors} ${best.competitors === 1 ? 'competitor' : 'competitors'}`}</span></span>
            </div>
          </div>
          <div className="bh-pick-grid">
            <ul className="br-reasons">{best.reasons.slice(0, 4).map((r) => <li key={r}><CheckCircle2 size={16} aria-hidden /> {r}</li>)}</ul>
            <div className="bh-minis">
              <Link href={areaHref(best.area.id)} className={`bh-mini is-${gap.data?.verdict.tone || 'early'}`}>
                <span className="bh-mini-label">Competitor gap</span>
                {gap.data ? <>
                  <span className="bh-mini-verdict">{gap.data.verdict.label}<span className="bh-mini-score">{gap.data.verdict.score}/100</span></span>
                  <span className="meta">{gap.data.metrics.competitors ? `${num(Math.round(gap.data.metrics.per_outlet))} supporters per outlet vs ${num(Math.round(gap.data.metrics.city_avg_per_outlet))} city average` : 'No outlets yet: demand is unserved'}</span>
                </> : <Skeleton rows={1} height={44} />}
              </Link>
              <Link href={areaHref(best.area.id)} className={`bh-mini is-${feas?.status.tone || 'early'}`}>
                <span className="bh-mini-label">Financial feasibility</span>
                {feas ? <>
                  <span className="bh-mini-verdict">{feas.status.label}<span className="bh-mini-score">{feas.status.score}/100</span></span>
                  <span className="meta">{feas.expected.profit >= 0 ? `${inrShort(feas.expected.profit)} a month profit` : `Loses ${inrShort(-feas.expected.profit)} a month`} · {feas.payback_month ? `pays back in ${feas.payback_month} months` : 'no payback within 10 years'}</span>
                </> : <Skeleton rows={1} height={44} />}
              </Link>
            </div>
          </div>
          <div className="row">
            <LinkButton href={areaHref(best.area.id)}>Open full reports <ArrowRight size={16} aria-hidden /></LinkButton>
            <span className="meta">{feas ? `Feasibility for a ${feas.space.title.replace(/^Typical /, 'typical ')}` : ''}</span>
          </div>
        </section>
      ) : data ? (
        <section className="empty" aria-live="polite">
          <h2 className="h3">No verified demand for {noun} {scope === 'near' ? `near ${loc.label}` : `in ${data.city}`} yet</h2>
          <p>Residents haven&apos;t asked for this business here. Try another business type{scope === 'near' ? ', look across the whole city,' : ''} or open the map to compare.</p>
          <div className="row" style={{ justifyContent: 'center' }}>
            {scope === 'near' ? <button type="button" className="btn btn-secondary btn-md" onClick={() => setScope('city')}>Show all of {data.city}</button> : null}
            <LinkButton href={`/map?category=${cat}`} variant="secondary">Open the map</LinkButton>
          </div>
        </section>
      ) : null}

      {/* 3. All areas ranked */}
      <section className="stack">
        <div className="section-head" style={{ marginBottom: 0 }}>
          <div className="stack-sm"><h2 className="h2">All areas, ranked</h2><p className="meta">Verified demand, matching spaces and competition for {noun}</p></div>
          <Segmented label="View" value={view} onChange={setView} options={[{ key: 'list', label: 'List' }, { key: 'map', label: 'Map' }]} />
        </div>
        {view === 'map' && data ? <MapView center={{ lat: best?.area.lat || 26.2183, lng: best?.area.lng || 78.1828 }} zoom={12} zones={zones} height={420} fitKey={cat} ariaLabel={`Areas ranked for ${noun}`} /> : null}
        {loading ? <Skeleton rows={5} /> : (
          <ol className="rows">{(data?.areas || []).map((a, i) => <AreaRow key={a.area.id} a={a} rank={i + 1} href={areaHref(a.area.id)} />)}</ol>
        )}
      </section>

      {/* 4. Spaces that fit */}
      <section className="stack">
        <div className="section-head" style={{ marginBottom: 0 }}>
          <div className="stack-sm"><h2 className="h2">Spaces that fit your plan</h2><p className="meta">Vacant spaces near {loc.label} sized for {noun}{data?.budget ? `, within ₹${num(data.budget)} a month` : ''}</p></div>
          <Link href={`/explore?tab=spaces&category=${cat}`} className="link-quiet">See all spaces</Link>
        </div>
        {spaces.loading ? <Skeleton rows={1} height={260} /> : spaces.data?.items.length
          ? <div className="grid-cards">{spaces.data.items.map((s) => <SpaceCard key={s.id} s={s} />)}</div>
          : <p className="meta panel">No vacant spaces fit {noun} near {loc.label} yet. Save an area to hear when one is listed.</p>}
      </section>

      {/* 5. Pipeline */}
      <section className="stack">
        <h2 className="h2">Your pipeline</h2>
        <div className="bh-pipeline">
          <Link href="/saved" className="rh-tile"><span className="rh-tile-label"><Bookmark size={16} aria-hidden /> Saved</span>
            <span className="rh-tile-value">{saved.data ? num(saved.data.areas.length + saved.data.properties.length) : '–'}</span>
            <span className="meta">{saved.data ? `${saved.data.areas.length} areas, ${saved.data.properties.length} spaces` : 'Areas and spaces you saved'}</span></Link>
          <Link href="/inquiries" className="rh-tile"><span className="rh-tile-label"><MessageSquare size={16} aria-hidden /> Owner conversations</span>
            <span className="rh-tile-value">{sent.data ? num(talks) : '–'}</span><span className="meta">Spaces you asked about</span></Link>
          <Link href="/inquiries" className="rh-tile"><span className="rh-tile-label"><Briefcase size={16} aria-hidden /> Market briefs</span>
            <span className="rh-tile-value">{sent.data ? num(briefs) : '–'}</span><span className="meta">Requested from the BizYukti team</span></Link>
        </div>
        {profile && !profile.verified ? (
          <Notice tone="info"><span className="row" style={{ gap: 6 }}><ShieldCheck size={16} aria-hidden />
            {profile.verification_status === 'pending' ? 'Your business verification is in review.' : <>Verified businesses get faster replies from owners. <Link href="/profile">Get the Verified business badge</Link></>}</span></Notice>
        ) : null}
      </section>
    </div>
  )
}

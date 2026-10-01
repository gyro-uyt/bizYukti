'use client'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useMemo, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Store as StoreIcon } from 'lucide-react'
import { MapView } from '@/components/map'
import { DEMAND_GROUPS, categoryIcon, demandGroup } from '@/lib/category-media'
import { AppShell } from '@/components/shell'
import { Badge, Chip, Field, LinkButton } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { budgetLabel, num, price, sqft } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'

type ZoneRow = { category: string; category_name: string; demands: number; supporters: number; lat: number; lng: number; radius_m: number; intensity: number; top_demand_id: string }
type SpacePt = { id: string; lat: number; lng: number; title: string; type: string; size_sqft: number | null; price_type: string; price_amount: number | null; price_negotiable: boolean; locality: string | null; verified: boolean; distance_m: number; cover_url: string | null }
type Layers = { zones: ZoneRow[]; spaces: SpacePt[]; areas: { id: string; name: string }[] }

const BUDGETS = [0, 15000, 25000, 40000, 60000, 100000]
const SIZES = [{ k: '', label: 'Any size' }, { k: '0-300', label: 'Under 300 sq ft' }, { k: '300-800', label: '300 to 800 sq ft' }, { k: '800-2000', label: '800 to 2,000 sq ft' }, { k: '2000-1000000', label: '2,000 sq ft and up' }]
const RADII = [2, 5, 8, 12]

export default function MapScreen() {
  const params = useSearchParams()
  const { user } = useAuth()
  const { loc, categories } = useLocation()
  const [cat, setCat] = useState(params.get('category') || user?.business?.categories?.[0] || '')
  const [budget, setBudget] = useState(0)
  const [size, setSize] = useState('')
  const [radius, setRadius] = useState(8)
  const [sel, setSel] = useState<{ kind: 'zone' | 'space'; id: string } | null>(null)
  const [open, setOpen] = useState(false)
  const [focus, setFocus] = useState<{ lat: number; lng: number } | null>(null)
  const [smin, smax] = size ? size.split('-').map(Number) : [undefined, undefined]
  const { data } = useApi<Layers>('/map/layers', { lat: loc.lat, lng: loc.lng, radius_km: radius, category: cat, budget: budget || undefined, size_min: smin, size_max: smax })

  // Each zone is coloured by its category family and carries a badge with the category icon and supporter count.
  const zones = useMemo(() => (data?.zones || []).map((z, i) => {
    const group = demandGroup(z.category)
    const Icon = categoryIcon(z.category).icon
    return {
      ...z, id: `z${i}`, group, color: group.color, selected: sel?.kind === 'zone' && sel.id === `z${i}`,
      label: `${z.category_name} (${group.label}): ${num(z.supporters)} verified supporters`,
      badgeHtml: `<i>${renderToStaticMarkup(<Icon size={13} strokeWidth={2.4} aria-hidden />)}</i><b>${num(z.supporters)}</b>`,
      onClick: () => { setSel({ kind: 'zone', id: `z${i}` }); setOpen(true) },
    }
  }), [data, sel])
  // Zones of different categories often share a centre; fan their badges out in a row (strongest in the middle).
  const placed = useMemo(() => {
    const buckets = new Map<string, typeof zones>()
    zones.forEach((z) => {
      const k = `${Math.round(z.lat / 0.004)}:${Math.round(z.lng / 0.004)}`
      buckets.set(k, [...(buckets.get(k) || []), z])
    })
    const offset = new Map<string, [number, number]>()
    buckets.forEach((list) => {
      const sorted = [...list].sort((a, b) => b.supporters - a.supporters)
      const order = sorted.map((_, i) => (i % 2 ? -1 : 1) * Math.ceil(i / 2)) // 0, +1, -1, +2, -2 …
      sorted.forEach((z, i) => offset.set(z.id, [order[i] * 62, 0]))
    })
    return zones.map((z) => ({ ...z, badgeOffset: offset.get(z.id) }))
  }, [zones])
  const groups = useMemo(() => DEMAND_GROUPS.map((g) => ({ ...g, count: zones.filter((z) => z.group.key === g.key).length }))
    .filter((g) => g.count), [zones])
  const points = useMemo(() => (data?.spaces || []).map((s) => ({
    id: s.id, lat: s.lat, lng: s.lng, kind: 'space' as const, selected: sel?.kind === 'space' && sel.id === s.id,
    label: `${s.title}, ${price(s)}`, onClick: () => { setSel({ kind: 'space', id: s.id }); setOpen(true) },
  })), [data, sel])
  const zone = sel?.kind === 'zone' ? zones.find((z) => z.id === sel.id) : null
  const space = sel?.kind === 'space' ? data?.spaces.find((s) => s.id === sel.id) : null
  const choose = (id: string, lat: number, lng: number) => { setSel({ kind: 'zone', id }); setFocus({ lat, lng }) }

  return (
    <AppShell wide>
      <div className="split">
        <MapView center={focus || loc} zoom={13} zones={placed} points={points} height="100%" fitKey={`${cat}-${radius}`}
          ariaLabel="Opportunity map. Circles are demand zones, coloured by category family and labelled with the category icon and supporter count. Orange shop markers are vacant spaces. The list beside the map has the same information." />
        <aside className={`rail${open ? ' is-open' : ''}`} aria-label="Filters and results">
          <button type="button" className="sheet-handle" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Show more map' : 'Show list and filters'}</button>
          <div className="stack-sm">
            <h1 className="h2">Opportunity map</h1>
            <p className="meta">{data ? `${data.zones.length} demand zones and ${data.spaces.length} available spaces within ${radius} km of ${loc.label}` : 'Loading map data…'}</p>
          </div>
          <div className="filters">
            <Field label="Category" htmlFor="m-cat">
              <select id="m-cat" className="input" value={cat} onChange={(e) => { setCat(e.target.value); setSel(null) }}>
                <option value="">All categories</option>
                {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Monthly rent" htmlFor="m-budget">
              <select id="m-budget" className="input" value={budget} onChange={(e) => setBudget(Number(e.target.value))}>
                {BUDGETS.map((b) => <option key={b} value={b}>{b ? `Up to ${budgetLabel(b)}` : 'Any budget'}</option>)}
              </select>
            </Field>
            <Field label="Size" htmlFor="m-size">
              <select id="m-size" className="input" value={size} onChange={(e) => setSize(e.target.value)}>
                {SIZES.map((s) => <option key={s.k} value={s.k}>{s.label}</option>)}
              </select>
            </Field>
          </div>
          <div className="stack-sm"><span className="field-label">Radius</span><div className="chips">{RADII.map((r) => <Chip key={r} selected={radius === r} onClick={() => setRadius(r)}>{r} km</Chip>)}</div></div>
          <div className="map-legend" aria-label="Legend">
            {groups.map((g) => <span key={g.key}><i className="legend-dot" style={{ background: g.color }} />{g.label}<span className="meta">{g.count}</span></span>)}
            <span><i className="pin-store is-legend" dangerouslySetInnerHTML={{ __html: renderToStaticMarkup(<StoreIcon size={11} strokeWidth={2.6} aria-hidden />) }} />Vacant space<span className="meta">{data?.spaces.length ?? 0}</span></span>
            <p className="meta">Circle size and shade grow with verified supporters.</p>
          </div>
          {zone ? (
            <div className="panel panel-tight stack-sm">
              <span className="row" style={{ gap: 8 }}>
                <span className="zone-chip" style={{ background: zone.color }}>{(() => { const I = categoryIcon(zone.category).icon; return <I size={16} aria-hidden /> })()}</span>
                <Badge tone="neutral">{zone.group.label}</Badge>
              </span>
              <p className="h3">{zone.category_name}</p>
              <p>{num(zone.supporters)} verified supporters across {zone.demands === 1 ? '1 request' : `${zone.demands} requests`}</p>
              <LinkButton href={`/demands/${zone.top_demand_id}`} variant="secondary" size="sm">View top request</LinkButton>
            </div>
          ) : null}
          {space ? (
            <div className="panel panel-tight stack-sm">
              {space.cover_url ? <img src={space.cover_url} alt="" style={{ borderRadius: 4, aspectRatio: '3 / 2', objectFit: 'cover' }} /> : null}
              <p className="h3">{space.title}</p>
              <p>{price(space)}{space.size_sqft ? `, ${sqft(space.size_sqft)}` : ''}</p>
              <p className="meta">{space.locality}{space.verified ? ', ownership verified' : ''}</p>
              <LinkButton href={`/properties/${space.id}`} size="sm">View space</LinkButton>
            </div>
          ) : null}
          <div className="stack-sm">
            <h2 className="h3">Strongest demand</h2>
            <ol className="rows">
              {zones.slice(0, 12).map((z) => (
                <li key={z.id}><button type="button" className="row-link" style={{ minHeight: 60, padding: '12px 14px' }} onClick={() => choose(z.id, z.lat, z.lng)} aria-pressed={sel?.id === z.id}>
                  <span className="zone-chip" style={{ background: z.color }} aria-hidden>{(() => { const I = categoryIcon(z.category).icon; return <I size={15} /> })()}</span>
                  <span><span className="row-title" style={{ fontSize: 15 }}>{z.category_name}</span><span className="row-meta"><span>{z.demands === 1 ? '1 request' : `${z.demands} requests`}</span></span></span>
                  <span className="row-count"><strong style={{ fontSize: 18 }}>{num(z.supporters)}</strong></span>
                </button></li>
              ))}
            </ol>
            {data && !zones.length ? <p className="meta">No live demand in this radius. Try a wider radius or another category.</p> : null}
            <p className="meta">Looking for a specific area? <Link href="/explore?tab=areas">Browse areas</Link></p>
          </div>
        </aside>
      </div>
    </AppShell>
  )
}

'use client'
import { useMemo, useState } from 'react'
import { Check, MapPin, PersonStanding } from 'lucide-react'
import { StatusBadge, TrustBadge } from '@/components/cards'
import { LocationPicker } from '@/components/location-picker'
import { MapView } from '@/components/map'
import { AppShell } from '@/components/shell'
import { Button, Chip, Field, LinkButton } from '@/components/ui'
import { useRequireAuth } from '@/lib/auth'
import { distance, num } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { Demand, Paged } from '@/lib/types'

const RADII = [1, 2, 5]

/** Resident map: every live request around the chosen location, ranked by verified supporters. */
export default function Neighbourhood() {
  const user = useRequireAuth()
  const { loc, categories } = useLocation()
  const [cat, setCat] = useState('')
  const [radius, setRadius] = useState(2)
  const [sel, setSel] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [focus, setFocus] = useState<{ lat: number; lng: number } | null>(null)
  const [picking, setPicking] = useState(false)
  const { data } = useApi<Paged<Demand>>(user ? '/demands' : null,
    { lat: loc.lat, lng: loc.lng, radius_km: radius, category: cat, sort: 'support', limit: 50 })

  const items = useMemo(() => data?.items || [], [data])
  const points = useMemo(() => [
    { id: 'me', lat: loc.lat, lng: loc.lng, kind: 'me' as const, label: `You: ${loc.label}` },
    ...items.map((d) => ({
      id: d.id, lat: d.lat, lng: d.lng, kind: 'demand' as const, selected: sel === d.id,
      label: `${d.display_title}, ${num(d.supporters)} supporters`, onClick: () => { setSel(d.id); setOpen(true) },
    })),
  ], [items, sel, loc])
  const zones = useMemo(() => [{ lat: loc.lat, lng: loc.lng, radius_m: radius * 1000, intensity: 0, tone: 'blue' as const,
    label: `Within ${radius} km of ${loc.label}` }], [loc, radius])
  const selected = items.find((d) => d.id === sel)
  const choose = (d: Demand) => { setSel(d.id); setFocus({ lat: d.lat, lng: d.lng }) }

  if (!user) return null
  return (
    <AppShell wide>
      <div className="split">
        <MapView center={focus || loc} zoom={14} zones={zones} points={points} height="100%" fitKey={`${cat}-${radius}-${loc.lat}-${loc.lng}`}
          ariaLabel="Neighbourhood map. Pink circles are requests from residents, the blue person marker is your location. The list beside the map has the same information." />
        <aside className={`rail${open ? ' is-open' : ''}`} aria-label="Filters and requests">
          <button type="button" className="sheet-handle" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Show more map' : 'Show list and filters'}</button>
          <div className="stack-sm">
            <h1 className="h2">Your neighbourhood</h1>
            <p className="meta">{data ? `${data.total} ${data.total === 1 ? 'request' : 'requests'} within ${radius} km of ${loc.label}` : 'Loading requests…'}</p>
            <Button variant="secondary" size="sm" onClick={() => setPicking(true)}><MapPin size={16} aria-hidden /> Change location</Button>
          </div>
          <div className="filters">
            <Field label="Category" htmlFor="n-cat">
              <select id="n-cat" className="input" value={cat} onChange={(e) => { setCat(e.target.value); setSel(null) }}>
                <option value="">All categories</option>
                {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
            </Field>
          </div>
          <div className="stack-sm"><span className="field-label">Distance</span><div className="chips">{RADII.map((r) => <Chip key={r} selected={radius === r} onClick={() => { setRadius(r); setSel(null) }}>{r} km</Chip>)}</div></div>
          <div className="legend"><span><i className="pin pin-demand" /> Request</span><span><i className="pin-me"><PersonStanding aria-hidden /></i> Your location</span></div>
          {selected ? (
            <div className="panel panel-tight stack-sm">
              <div className="row"><TrustBadge verified={selected.verified} /><StatusBadge status={selected.status} /></div>
              <p className="h3">{selected.display_title}</p>
              <p><strong>{num(selected.supporters)}</strong> {selected.supporters === 1 ? 'resident supports' : 'residents support'} this{selected.distance_m != null ? `, ${distance(selected.distance_m)} away` : ''}</p>
              {selected.my_support === 'verified' ? <p className="meta row"><Check size={14} aria-hidden /> You support this</p> : null}
              <LinkButton href={`/demands/${selected.id}`} size="sm">{selected.my_support ? 'View request' : 'View and support'}</LinkButton>
            </div>
          ) : null}
          <div className="stack-sm">
            <h2 className="h3">Most wanted nearby</h2>
            <ol className="rows">
              {items.slice(0, 20).map((d, i) => (
                <li key={d.id}><button type="button" className="row-link" style={{ minHeight: 60, padding: '12px 14px' }} onClick={() => choose(d)} aria-pressed={sel === d.id}>
                  <span className={`rank${i < 3 ? ' rank-top' : ''}`} aria-hidden>{i + 1}</span>
                  <span><span className="row-title" style={{ fontSize: 15 }}>{d.display_title}</span>
                    <span className="row-meta"><span>{d.category_name}</span>{d.distance_m != null ? <span>{distance(d.distance_m)}</span> : null}</span></span>
                  <span className="row-count"><strong style={{ fontSize: 18 }}>{num(d.supporters)}</strong></span>
                </button></li>
              ))}
            </ol>
            {data && !items.length ? (
              <div className="stack-sm">
                <p className="meta">No requests within {radius} km yet. Try a wider distance, or be the first to ask.</p>
                <LinkButton href="/demands/new" variant="pink" size="sm">Request a business</LinkButton>
              </div>
            ) : null}
          </div>
        </aside>
      </div>
      <LocationPicker open={picking} onClose={() => setPicking(false)} />
    </AppShell>
  )
}

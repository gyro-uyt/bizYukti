'use client'
// Decision reports for businesses: Competitor Gap Analysis and Financial Feasibility, for an area or a space.
// All numbers are computed by the API (/reports/*); this file only presents them.
import Link from 'next/link'
import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { AlertTriangle, CheckCircle2, Info, MapPin, Printer, RotateCcw, Users, XCircle } from 'lucide-react'
import { ApiError, errorMessage, http } from '@/lib/api'
import { inrShort, num } from '@/lib/format'
import { useApi, useDebounced } from '@/lib/hooks'
import type { Space } from '@/lib/types'
import { Badge, Button, Notice, Skeleton, Tabs, type Tone } from './ui'

type GapRow = { area: { id: string; name: string }; distance_km: number; supporters: number; competitors: number; per_outlet: number; score: number; label: string; tone: string; current: boolean }
type Gap = {
  category: string; category_name: string; scope: 'area' | 'property'; area: { id: string; name: string; city: string }
  verdict: { label: string; tone: string; score: number; summary: string }
  metrics: { supporters: number; requests: number; competitors: number; intensity: string; per_outlet: number; city_avg_per_outlet: number; footfall_index: number; rank_nearby: number | null; areas_nearby: number }
  service_gaps: { label: string; supporters: number; share: number }[]
  audience: { reason: string; label: string; supporters: number; share: number }[]
  complements: { category: string; name: string; count: number; text: string }[]
  neighbours: GapRow[]; reasons: string[]; top_requests: { id: string; title: string; locality: string; supporters: number }[]; sources: string
}
type Month = { units: number; revenue: number; profit: number; margin_pct: number | null; costs: Record<'cogs' | 'occupancy' | 'staff' | 'utilities' | 'other', number> }
type Check = { key: string; label: string; status: 'good' | 'warn' | 'bad'; detail: string }
type Assumption = { key: string; label: string; value: number; base: number; unit: string }
type Feas = {
  category: string; category_name: string; model: string; unit_label: string; per_day: boolean
  area: { id: string; name: string; city: string }; occupancy_label: string
  space: { source: 'listing' | 'typical'; property_id: string | null; title: string; locality: string; size_sqft: number; price_type: string; price_amount: number | null; negotiable: boolean; note?: string }
  status: { label: string; tone: 'good' | 'warn' | 'bad'; score: number; summary: string }
  demand: { supporters: number; reach: number; potential_customers: number; competitors: number; share_pct: number; walkin_share_pct: number; footfall_index: number; capacity: number | null; capped: boolean }
  expected: Month; scenarios: (Month & { key: string; label: string; factor: number })[]
  breakeven: { revenue: number | null; units: number | null; per_day: number | null; cushion: number }
  rent_ratio: number | null; setup: { total: number; items: Record<string, number> }; payback_month: number | null
  cash_curve: { month: number; cash: number }[]; checks: Check[]; assumptions: Assumption[]; customised: boolean; notes: string[]
}

const GAP_TONE: Record<string, Tone> = { strong: 'strong', promising: 'promising', early: 'early', warn: 'warn' }
const STATUS_TONE: Record<string, Tone> = { good: 'strong', warn: 'promising', bad: 'bad' }
const CHECK_ICON = { good: CheckCircle2, warn: AlertTriangle, bad: XCircle }

export type ReportsProps = {
  areaId?: string
  propertyId?: string
  /** Controlled category (area page). Leave out to let the report pick and show its own selector. */
  category?: string
  categoryChoices?: { slug: string; name: string }[]
  /** Spaces in the area the feasibility report can evaluate instead of a typical space. */
  spaces?: Space[]
}

export function BusinessReports({ areaId, propertyId, category, categoryChoices, spaces }: ReportsProps) {
  const [tab, setTab] = useState<'gap' | 'feasibility'>('gap')
  const [ownCat, setOwnCat] = useState<string | null>(null)
  const cat = category ?? ownCat ?? undefined
  const gap = useApi<Gap>('/reports/competitor-gap', { area_id: areaId, property_id: propertyId, category: cat })
  useEffect(() => { if (!category && !ownCat && gap.data?.category) setOwnCat(gap.data.category) }, [category, ownCat, gap.data?.category])
  const name = gap.data?.category_name
  const where = propertyId ? 'this space' : gap.data?.area.name || 'this area'

  const print = () => {
    document.body.classList.add('br-printing')
    const done = () => { document.body.classList.remove('br-printing'); window.removeEventListener('afterprint', done) }
    window.addEventListener('afterprint', done)
    window.print()
    setTimeout(done, 1500)
  }

  return (
    <section className="br-root" aria-labelledby="br-title">
      <div className="br-head">
        <div className="stack-sm">
          <p className="br-eyebrow">Decision reports</p>
          <h2 className="h2" id="br-title">{name ? `Should you open a ${name.toLowerCase()} at ${where}?` : 'Decision reports'}</h2>
          <p className="meta">Competitor gap and financial feasibility from verified local demand, live listings and typical costs.</p>
        </div>
        <div className="row br-no-print">
          {!category && categoryChoices?.length ? (
            <>
              <label className="sr-only" htmlFor="br-cat">Business type</label>
              <select id="br-cat" className="input" style={{ maxWidth: 240 }} value={cat || ''} onChange={(e) => setOwnCat(e.target.value)}>
                {categoryChoices.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
            </>
          ) : null}
          <Button variant="secondary" size="sm" onClick={print}><Printer size={16} aria-hidden /> Print or save PDF</Button>
        </div>
      </div>
      <div className="br-no-print">
        <Tabs label="Reports" value={tab} onChange={setTab} tabs={[{ key: 'gap', label: 'Competitor gap analysis' }, { key: 'feasibility', label: 'Financial feasibility' }]} />
      </div>
      {tab === 'gap'
        ? (gap.error ? <Notice tone="error">{gap.error.message}</Notice> : !gap.data ? <Skeleton rows={3} height={140} /> : <GapReport g={gap.data} />)
        : <FeasibilityReport areaId={areaId} propertyId={propertyId} category={cat} spaces={spaces} />}
    </section>
  )
}

/* ------------------------------------------------------------------ Competitor gap */
function GapReport({ g }: { g: Gap }) {
  const m = g.metrics
  const maxPer = Math.max(m.per_outlet, m.city_avg_per_outlet, 1)
  return (
    <div className="stack-lg">
      <div className={`br-verdict is-${g.verdict.tone}`}>
        <Score value={g.verdict.score} label="Gap score" />
        <div className="stack-sm" style={{ flex: 1, minWidth: 220 }}>
          <div className="row" style={{ gap: 8 }}><Badge tone={GAP_TONE[g.verdict.tone] || 'neutral'}>{g.verdict.label}</Badge>
            <span className="meta">{g.category_name} · {g.scope === 'property' ? `within 2 km of this space, ${g.area.name}` : `${g.area.name}, ${g.area.city}`}</span></div>
          <p className="br-summary">{g.verdict.summary}</p>
        </div>
      </div>

      <div className="stats">
        <div className="stat stat-pink"><span className="stat-value">{num(m.supporters)}</span><span className="stat-label">verified residents want it ({m.requests} {m.requests === 1 ? 'request' : 'requests'})</span></div>
        <div className="stat"><span className="stat-value">{m.competitors}</span><span className="stat-label">existing outlets · {m.intensity.toLowerCase()} competition</span></div>
        <div className="stat stat-blue"><span className="stat-value">{m.competitors ? num(Math.round(m.per_outlet)) : '∞'}</span><span className="stat-label">supporters per outlet ({g.area.city} avg {num(Math.round(m.city_avg_per_outlet))})</span></div>
        <div className="stat"><span className="stat-value">{Math.round(m.footfall_index * 100)}</span><span className="stat-label">footfall index out of 100</span></div>
      </div>

      <div className="grid-2">
        <div className="blockbox accent-pink">
          <div><h3 className="h3">Demand vs supply</h3><p className="meta">Verified supporters for each existing {g.category_name.toLowerCase()}</p></div>
          {m.competitors ? (
            <ul className="br-hbars">
              <HBar label={g.scope === 'property' ? 'Around this space' : g.area.name} value={m.per_outlet} max={maxPer} text={`${num(Math.round(m.per_outlet))} per outlet`} strong />
              <HBar label={`${g.area.city} average`} value={m.city_avg_per_outlet} max={maxPer} text={`${num(Math.round(m.city_avg_per_outlet))} per outlet`} />
            </ul>
          ) : (
            <p className="br-callout">{m.supporters ? <>No {g.category_name.toLowerCase()} here yet, so all <strong>{num(m.supporters)}</strong> supporters are unserved locally.</> : 'No outlets and no requests yet: an untested market.'}</p>
          )}
          {m.city_avg_per_outlet > 0 && m.competitors > 0 ? <p className="meta">{(m.per_outlet / m.city_avg_per_outlet).toFixed(1)}× the city average demand per outlet.</p> : null}
        </div>
        <div className="blockbox accent-orange">
          <div><h3 className="h3">What residents say is missing</h3><p className="meta">From the wording of their requests, weighted by supporters</p></div>
          {g.service_gaps.length ? (
            <ul className="br-hbars">{g.service_gaps.map((s) => <HBar key={s.label} label={s.label} value={s.share} max={1} text={`${Math.round(s.share * 100)}% · ${num(s.supporters)}`} />)}</ul>
          ) : <p className="meta">Requests ask for the business itself, without a specific service angle.</p>}
          {g.audience.length ? (
            <div className="stack-sm"><span className="field-label row" style={{ gap: 6 }}><Users size={15} aria-hidden /> Who&apos;s asking</span>
              <div className="br-chips">{g.audience.map((a) => <span key={a.reason} className="br-chip"><strong>{Math.round(a.share * 100)}%</strong> {a.label.toLowerCase()}</span>)}</div></div>
          ) : null}
        </div>
      </div>

      <div className="blockbox accent-blue">
        <div className="row-between"><div><h3 className="h3">Nearby areas compared</h3><p className="meta">Same business type, areas within 5 km{m.rank_nearby ? `. This one ranks ${m.rank_nearby} of ${m.areas_nearby}.` : ''}</p></div></div>
        <div className="table-wrap">
          <table className="br-table">
            <thead><tr><th>Area</th><th className="n">Distance</th><th className="n">Verified demand</th><th className="n">Outlets</th><th className="n">Per outlet</th><th>Gap</th></tr></thead>
            <tbody>{g.neighbours.map((r) => (
              <tr key={r.area.id} className={r.current ? 'is-current' : undefined}>
                <td>{r.current ? <strong>{r.area.name} <span className="meta">(this area)</span></strong>
                  : <Link href={`/opportunities/${r.area.id}?category=${g.category}`}>{r.area.name}</Link>}</td>
                <td className="n">{r.current ? '–' : `${r.distance_km} km`}</td>
                <td className="n">{num(r.supporters)}</td><td className="n">{r.competitors}</td>
                <td className="n">{r.competitors ? num(Math.round(r.per_outlet)) : r.supporters ? 'Unserved' : '–'}</td>
                <td><Badge tone={GAP_TONE[r.tone] || 'neutral'}>{r.label}</Badge></td>
              </tr>))}</tbody>
          </table>
        </div>
      </div>

      <div className="grid-2">
        <div className="blockbox">
          <h3 className="h3">Why this verdict</h3>
          <ul className="br-reasons">{g.reasons.map((r) => <li key={r}><CheckCircle2 size={16} aria-hidden /> {r}</li>)}</ul>
        </div>
        <div className="blockbox">
          <h3 className="h3">Helpful neighbours</h3>
          {g.complements.length ? <ul className="br-reasons is-plain">{g.complements.map((c) => <li key={c.category}><MapPin size={16} aria-hidden /> {c.text}</li>)}</ul>
            : <p className="meta">No complementary businesses recorded nearby.</p>}
          {g.top_requests.length ? (
            <div className="stack-sm"><span className="field-label">Requests behind this demand</span>
              <ul className="br-links">{g.top_requests.map((t) => <li key={t.id}><Link href={`/demands/${t.id}`}>{t.title} near {t.locality}</Link> <span className="meta">{num(t.supporters)} supporters</span></li>)}</ul></div>
          ) : null}
        </div>
      </div>
      <p className="meta br-source"><Info size={13} aria-hidden /> {g.sources}</p>
    </div>
  )
}

/* ------------------------------------------------------------------ Financial feasibility */
function FeasibilityReport({ areaId, propertyId, category, spaces }: { areaId?: string; propertyId?: string; category?: string; spaces?: Space[] }) {
  const [spaceId, setSpaceId] = useState<string>(propertyId || '')
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [data, setData] = useState<Feas | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const seq = useRef(0)
  const overrides = useMemo(() => {
    const o: Record<string, number> = {}
    Object.entries(draft).forEach(([k, v]) => { const n = Number(v); if (v.trim() !== '' && Number.isFinite(n) && n >= 0) o[k] = n })
    return o
  }, [draft])
  const dOverrides = useDebounced(overrides, 450)
  const target = propertyId || spaceId

  useEffect(() => { setDraft({}) }, [category, target])
  useEffect(() => {
    const n = ++seq.current
    setLoading(true)
    http.post<Feas>('/reports/feasibility', {
      category, ...(target ? { property_id: target } : { area_id: areaId }),
      assumptions: Object.keys(dOverrides).length ? dOverrides : undefined,
    }).then((r) => { if (n === seq.current) { setData(r); setError(null) } })
      .catch((e) => { if (n === seq.current) setError(e instanceof ApiError ? e.message : errorMessage(e)) })
      .finally(() => { if (n === seq.current) setLoading(false) })
  }, [category, target, areaId, dOverrides])

  if (error && !data) return <Notice tone="error">{error}</Notice>
  if (!data) return <Skeleton rows={3} height={140} />
  const f = data
  const e = f.expected
  const unitsNow = f.per_day ? e.units / 30 : e.units
  const beNow = f.per_day ? f.breakeven.per_day : f.breakeven.units
  const price = f.space.price_amount ? (f.space.price_type === 'sale' ? `${inrShort(f.space.price_amount)} to buy` : `${inrShort(f.space.price_amount)}/month`) : 'Price on request'

  return (
    <div className={`stack-lg${loading ? ' br-updating' : ''}`}>
      {!propertyId && spaces?.length ? (
        <div className="row br-no-print">
          <label className="field-label" htmlFor="br-space">Evaluate</label>
          <select id="br-space" className="input" style={{ maxWidth: 420 }} value={spaceId} onChange={(ev) => setSpaceId(ev.target.value)}>
            <option value="">A typical space in {f.area.name}</option>
            {spaces.map((s) => <option key={s.id} value={s.id}>{s.display_title}, {s.locality}{s.price_amount ? ` · ${inrShort(s.price_amount)}${s.price_type === 'rent' ? '/month' : ''}` : ''}</option>)}
          </select>
        </div>
      ) : null}

      <div className={`br-verdict is-${f.status.tone}`}>
        <Score value={f.status.score} label="Feasibility" />
        <div className="stack-sm" style={{ flex: 1, minWidth: 220 }}>
          <div className="row" style={{ gap: 8 }}><Badge tone={STATUS_TONE[f.status.tone]}>{f.status.label}</Badge>
            {f.customised ? <Badge tone="blue">Your assumptions</Badge> : null}
            <span className="meta">{f.category_name} · {f.space.title} · {price} · {f.space.locality}</span></div>
          <p className="br-summary">{f.status.summary}</p>
          {f.space.note ? <p className="meta">{f.space.note}</p> : null}
        </div>
      </div>

      <div className="stats">
        <div className="stat stat-blue"><span className="stat-value">{inrShort(e.revenue)}</span><span className="stat-label">monthly revenue once settled</span></div>
        <div className={`stat ${e.profit >= 0 ? 'stat-green' : 'br-stat-bad'}`}><span className="stat-value">{inrShort(e.profit)}</span><span className="stat-label">monthly profit{e.margin_pct != null ? ` (${e.margin_pct}%)` : ''}</span></div>
        <div className="stat"><span className="stat-value">{beNow != null ? num(Math.ceil(beNow)) : '–'}</span><span className="stat-label">{f.unit_label.toLowerCase()} to break even (expect {num(Math.round(unitsNow))})</span></div>
        <div className="stat"><span className="stat-value">{f.payback_month ? `${f.payback_month} mo` : '10+ yr'}</span><span className="stat-label">to earn back {inrShort(f.setup.total)} setup</span></div>
      </div>

      <div className="blockbox">
        <h3 className="h3">Feasibility checks</h3>
        <ul className="br-checks">{f.checks.map((c) => { const Icon = CHECK_ICON[c.status]; return (
          <li key={c.key} className={`is-${c.status}`}><Icon size={18} aria-hidden /><span><strong>{c.label}</strong><span className="meta block">{c.detail}</span></span>
            <span className="sr-only">{c.status === 'good' ? 'passes' : c.status === 'warn' ? 'needs attention' : 'fails'}</span></li>) })}</ul>
      </div>

      <div className="grid-2">
        <div className="blockbox accent-blue">
          <div><h3 className="h3">Monthly profit and loss</h3><p className="meta">At expected demand, once sales settle</p></div>
          <PnL m={e} occupancyLabel={f.occupancy_label} />
        </div>
        <div className="blockbox accent-blue">
          <div><h3 className="h3">Cash over 36 months</h3><p className="meta">After {inrShort(f.setup.total)} setup, with a 6-month launch ramp</p></div>
          <CashChart curve={f.cash_curve} setup={f.setup.total} payback={f.payback_month} />
        </div>
      </div>

      <div className="grid-2">
        <div className="blockbox">
          <h3 className="h3">Scenarios</h3>
          <div className="table-wrap"><table className="br-table">
            <thead><tr><th /><th className="n">Demand −30%</th><th className="n">Expected</th><th className="n">Demand +30%</th></tr></thead>
            <tbody>
              <tr><td>{f.unit_label}</td>{f.scenarios.map((s) => <td key={s.key} className="n">{num(Math.round(f.per_day ? s.units / 30 : s.units))}</td>)}</tr>
              <tr><td>Monthly revenue</td>{f.scenarios.map((s) => <td key={s.key} className="n">{inrShort(s.revenue)}</td>)}</tr>
              <tr><td>Monthly profit</td>{f.scenarios.map((s) => <td key={s.key} className={`n ${s.profit >= 0 ? 'br-pos' : 'br-neg'}`}>{inrShort(s.profit)}</td>)}</tr>
            </tbody></table></div>
          <p className="meta">Demand: {num(f.demand.supporters)} verified supporters × {f.demand.reach} customers each, {f.demand.share_pct}% won against {f.demand.competitors} competitor{f.demand.competitors === 1 ? '' : 's'}{f.demand.capped ? `, capped at ${num(f.demand.capacity || 0)} by space` : ''}.</p>
        </div>
        <div className="blockbox">
          <h3 className="h3">Setup cost</h3>
          <ul className="br-setup">{Object.entries(f.setup.items).filter(([, v]) => v > 0).map(([k, v]) => (
            <li key={k}><span>{SETUP_LABEL[k] || k}</span><strong>{inrShort(v)}</strong></li>))}
            <li className="is-total"><span>Total to open</span><strong>{inrShort(f.setup.total)}</strong></li></ul>
        </div>
      </div>

      <Assumptions items={f.assumptions} draft={draft} setDraft={setDraft} customised={f.customised} />
      <ul className="br-notes">{f.notes.map((n) => <li key={n}>{n}</li>)}</ul>
    </div>
  )
}

const SETUP_LABEL: Record<string, string> = { fitout: 'Fit-out and interiors', deposit: 'Security deposit', down_payment: 'Down payment', stock: 'Opening stock and equipment', licences: 'Licences and launch' }

function Assumptions({ items, draft, setDraft, customised }: { items: Assumption[]; draft: Record<string, string>; setDraft: (d: Record<string, string>) => void; customised: boolean }) {
  return (
    <details className="blockbox br-assume br-no-print" open={customised || undefined}>
      <summary><span className="h3">Adjust the assumptions</span><span className="meta">Change any number to match your plan. The report updates as you type.</span></summary>
      <div className="br-assume-grid">
        {items.map((a) => (
          <div key={a.key} className="field">
            <label className="field-label" htmlFor={`as-${a.key}`}>{a.label}</label>
            <div className="input-prefix">{a.unit === '₹' || a.unit === '₹/month' ? <span>₹</span> : null}
              <input id={`as-${a.key}`} className="input" inputMode="decimal" style={a.unit.startsWith('₹') ? undefined : { paddingLeft: 14 }}
                value={draft[a.key] ?? String(a.value)} onChange={(e) => setDraft({ ...draft, [a.key]: e.target.value.replace(/[^\d.]/g, '') })} /></div>
            <span className="field-hint">{a.unit === '%' ? '%' : a.unit === '×' ? 'customers' : a.unit === 'people' ? 'people' : a.unit === '₹/month' ? 'per month' : ''}{Number(draft[a.key] ?? a.value) !== a.base ? ` · typical ${a.unit.startsWith('₹') ? inrShort(a.base) : num(a.base)}` : ''}</span>
          </div>
        ))}
      </div>
      {customised || Object.keys(draft).length ? <div><Button variant="secondary" size="sm" onClick={() => setDraft({})}><RotateCcw size={15} aria-hidden /> Reset to typical values</Button></div> : null}
    </details>
  )
}

/* ------------------------------------------------------------------ small visuals */
function Score({ value, label }: { value: number; label: string }) {
  return (
    <div className="br-score" role="img" aria-label={`${label}: ${value} out of 100`}>
      <span className="br-score-n">{value}</span><span className="br-score-of">/100</span>
      <span className="br-score-bar"><span style={{ width: `${Math.max(2, value)}%` }} /></span>
      <span className="br-score-label">{label}</span>
    </div>
  )
}

function HBar({ label, value, max, text, strong }: { label: string; value: number; max: number; text: string; strong?: boolean }) {
  return (
    <li className={`br-hbar${strong ? ' is-strong' : ''}`} title={`${label}: ${text}`}>
      <span className="br-hbar-label">{label}</span>
      <span className="br-hbar-track"><span style={{ width: `${Math.max(2, (value / max) * 100)}%` }} /></span>
      <span className="br-hbar-value">{text}</span>
    </li>
  )
}

function PnL({ m, occupancyLabel }: { m: Month; occupancyLabel: string }) {
  const rows: [string, number][] = [['Cost of goods', m.costs.cogs], [occupancyLabel, m.costs.occupancy], ['Staff', m.costs.staff], ['Utilities', m.costs.utilities], ['Other running costs', m.costs.other]]
  const max = Math.max(m.revenue, Math.abs(m.profit), 1)
  return (
    <ul className="br-pnl">
      <li className="is-revenue" title={`Revenue: ${inrShort(m.revenue)}`}><span>Revenue</span><span className="br-pnl-track"><span style={{ width: `${(m.revenue / max) * 100}%` }} /></span><strong>{inrShort(m.revenue)}</strong></li>
      {rows.map(([k, v]) => <li key={k} title={`${k}: ${inrShort(v)}`}><span>{k}</span><span className="br-pnl-track"><span style={{ width: `${Math.max(1, (v / max) * 100)}%` }} /></span><strong>−{inrShort(v)}</strong></li>)}
      <li className={m.profit >= 0 ? 'is-profit' : 'is-loss'} title={`${m.profit >= 0 ? 'Profit' : 'Loss'}: ${inrShort(m.profit)}`}><span>{m.profit >= 0 ? 'Profit' : 'Loss'}</span><span className="br-pnl-track"><span style={{ width: `${Math.max(1, (Math.abs(m.profit) / max) * 100)}%` }} /></span><strong>{inrShort(m.profit)}</strong></li>
    </ul>
  )
}

/** Cumulative cash, one series. Hover or focus for the month's value; the dashed line marks break-even. */
function CashChart({ curve, setup, payback }: { curve: { month: number; cash: number }[]; setup: number; payback: number | null }) {
  const [hover, setHover] = useState<number | null>(null)
  const pts = [{ month: 0, cash: -setup }, ...curve]
  const W = 560, H = 220, L = 64, R = 12, T = 14, B = 28
  const minV = Math.min(0, ...pts.map((p) => p.cash)), maxV = Math.max(0, ...pts.map((p) => p.cash))
  const span = maxV - minV || 1
  const x = (mo: number) => L + (mo / 36) * (W - L - R)
  const y = (v: number) => T + (1 - (v - minV) / span) * (H - T - B)
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.month).toFixed(1)},${y(p.cash).toFixed(1)}`).join(' ')
  const area = `${line} L${x(36)},${y(0)} L${x(0)},${y(0)} Z`
  const h = hover != null ? pts[hover] : null
  const onMove = (ev: MouseEvent<SVGSVGElement>) => {
    const r = ev.currentTarget.getBoundingClientRect()
    const mo = Math.round((((ev.clientX - r.left) / r.width) * W - L) / (W - L - R) * 36)
    setHover(Math.max(0, Math.min(36, mo)))
  }
  return (
    <div className="br-cash">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
        onKeyDown={(ev) => { if (ev.key === 'ArrowRight') setHover((v) => Math.min(36, (v ?? -1) + 1)); if (ev.key === 'ArrowLeft') setHover((v) => Math.max(0, (v ?? 37) - 1)) }}
        aria-label={`Cumulative cash: starts at ${inrShort(-setup)}, ${payback ? `turns positive in month ${payback}` : 'stays negative'}, reaches ${inrShort(pts[pts.length - 1].cash)} by month 36.`}>
        {[maxV, 0, minV].filter((v, i, a) => a.indexOf(v) === i).map((v) => (
          <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className={v === 0 ? 'br-axis' : 'br-grid'} />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" className="br-tick">{inrShort(v)}</text></g>
        ))}
        {[0, 12, 24, 36].map((mo) => <text key={mo} x={x(mo)} y={H - 8} textAnchor="middle" className="br-tick">{mo ? `Month ${mo}` : 'Open'}</text>)}
        <path d={area} className="br-cash-area" />
        <path d={line} className="br-cash-line" />
        {payback && payback <= 36 ? (
          <g><line x1={x(payback)} x2={x(payback)} y1={T} y2={H - B} className="br-be" />
            <text x={Math.min(x(payback) + 6, W - 120)} y={T + 12} className="br-be-label">Break-even · month {payback}</text></g>
        ) : null}
        {h ? <><line x1={x(h.month)} x2={x(h.month)} y1={T} y2={H - B} className="br-cross" /><circle cx={x(h.month)} cy={y(h.cash)} r={5} className="br-dot" /></> : null}
      </svg>
      {h ? <div className="br-tip" role="status" style={{ left: `${(x(h.month) / W) * 100}%` }}><strong>{inrShort(h.cash)}</strong><br /><span className="meta">{h.month ? `End of month ${h.month}` : 'Opening day'}</span></div> : null}
    </div>
  )
}

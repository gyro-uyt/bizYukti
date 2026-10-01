'use client'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { Bookmark, BookmarkCheck, Bus, Footprints, Route, TrendingDown, TrendingUp } from 'lucide-react'
import { BusinessReports } from '@/components/business-reports'
import { DemandRow, MessageModal, SpaceRow } from '@/components/cards'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Empty, LinkButton, Notice, PageHeader, Skeleton, StickyCTA } from '@/components/ui'
import { canUse } from '@/lib/access'
import { errorMessage, http } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { num, plural } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import type { AreaOpp, Demand, Inquiry, Space } from '@/lib/types'

type Detail = AreaOpp & { rank: number; of: number; series: { week: string; supporters: number }[]; demands: Demand[]
  spaces: Space[]; saved: boolean; brief_requested: boolean; budget: number | null; categories: { slug: string; name: string }[] }

export default function Opportunity() {
  const { areaId } = useParams<{ areaId: string }>()
  const params = useSearchParams()
  const router = useRouter()
  const toast = useToast()
  const { user, ready } = useAuth()
  const [cat, setCat] = useState(params.get('category') || '')
  const { data: a, loading, error, setData } = useApi<Detail>(ready ? `/opportunities/areas/${areaId}` : null, { category: cat || undefined, u: user?.id })
  const [composer, setComposer] = useState<'owner' | 'brief' | null>(null)

  if (error) return <AppShell><div className="container"><Empty title="Area not found" body={error.message} /></div></AppShell>
  if (loading || !a) return <AppShell><div className="container"><Skeleton rows={4} height={140} /></div></AppShell>

  const login = () => router.push(`/login?next=${encodeURIComponent(`/opportunities/${areaId}?category=${a.category}`)}`)
  const toggleSave = async () => {
    if (!user) return login()
    try {
      if (a.saved) await http.del('/saved', { kind: 'area', ref_id: areaId, category: a.category })
      else await http.post('/saved', { kind: 'area', ref_id: areaId, category: a.category })
      setData({ ...a, saved: !a.saved })
      toast(a.saved ? 'Removed from saved areas.' : 'Area saved. You will see it under Saved.')
    } catch (e) { toast(errorMessage(e)) }
  }
  const best = a.spaces[0]
  const send = async (message: string) => {
    if (composer === 'brief') {
      await http.post('/inquiries', { kind: 'market_brief', area_id: areaId, category: a.category, message })
      setData({ ...a, brief_requested: true })
      setComposer(null)
      toast('Brief requested. The BizYukti team will reply in your inbox.')
      return
    }
    const r = await http.post<Inquiry>('/inquiries', { kind: 'space', property_id: best.id, demand_id: a.demands[0]?.id, message })
    router.push(`/inquiries/${r.id}`)
  }
  const max = Math.max(1, ...a.series.map((s) => s.supporters))
  const Trend = a.trend.direction === 'cooling' ? TrendingDown : TrendingUp
  const level = a.competitors === 0 ? 'None recorded' : a.competitors <= 2 ? 'Light' : a.competitors <= 5 ? 'Moderate' : 'Heavy'
  const cta = best ? <Button block size="lg" onClick={() => (user ? setComposer('owner') : login())}>Contact owner of best-fit space</Button>
    : <Button block size="lg" onClick={() => (user ? setComposer('brief') : login())} disabled={a.brief_requested}>{a.brief_requested ? 'Market brief requested' : 'Request a market brief'}</Button>

  return (
    <AppShell>
      <div className="container stack-lg">
        <PageHeader back="/home" title={`${a.category_name} in ${a.area.name}`}
          sub={<span className="row"><Badge tone={a.tone}>{a.label}</Badge><span className="meta">Ranked {a.rank} of {a.of} areas in {a.area.city}</span></span>}
          action={<div className="row">
            <label className="sr-only" htmlFor="opp-cat">Category</label>
            <select id="opp-cat" className="input" style={{ maxWidth: 240 }} value={a.category} onChange={(e) => { setCat(e.target.value); router.replace(`/opportunities/${areaId}?category=${e.target.value}`, { scroll: false }) }}>
              {a.categories.filter((c) => c.slug !== 'other').map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </select>
            <Button variant="secondary" onClick={toggleSave}>{a.saved ? <BookmarkCheck size={18} aria-hidden /> : <Bookmark size={18} aria-hidden />}{a.saved ? 'Saved' : 'Save area'}</Button>
          </div>} />
        <section className="panel stack-sm accent-green">
          <h2 className="h3">Why this area</h2>
          <ul style={{ margin: 0, paddingLeft: 20, display: 'grid', gap: 6 }}>{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </section>
        {canUse(user, 'reports') ? <BusinessReports areaId={areaId} category={a.category} spaces={a.spaces} /> : null}
        <div className="grid-2">
          <section className="blockbox accent-pink">
            <h2 className="h2">Demand</h2>
            <p className="big-count"><span className="num">{num(a.supporters)}</span><span>verified supporters</span></p>
            <p className="row strong"><Trend size={18} aria-hidden /> {a.trend.text}</p>
            <div className="bars" role="img" aria-label={`Weekly new supporters for the last 8 weeks: ${a.series.map((s) => s.supporters).join(', ')}`}>
              {a.series.map((s) => (
                <div key={s.week}><span className="bar" style={{ height: `${(s.supporters / max) * 100}%` }} /><small>{new Date(s.week).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</small></div>
              ))}
            </div>
            {a.demands.length ? <ul className="rows">{a.demands.slice(0, 3).map((d) => <DemandRow key={d.id} d={d} />)}</ul> : <p className="meta">No requests yet. Demand often appears once someone asks first.</p>}
          </section>
          <section className="blockbox accent-orange">
            <h2 className="h2">Supply</h2>
            <p className="big-count supply"><span className="num">{a.spaces.length}</span><span>{a.spaces.length === 1 ? 'space fits' : 'spaces fit'} {a.category_name.toLowerCase()}</span></p>
            {a.budget ? <p className="meta">Within rent of ₹{num(a.budget)} a month.</p> : null}
            {a.spaces.length ? <ul className="rows">{a.spaces.slice(0, 4).map((s) => <li key={s.id}><SpaceRow s={s} extra={<span className="meta">{Math.round((s.fit || 0) * 100)}% size fit. {s.availability_text}</span>} /></li>)}</ul>
              : <p className="meta">No matching spaces are listed yet. Save the area to hear when one is.</p>}
          </section>
          <section className="blockbox accent-blue">
            <h2 className="h2">Competition</h2>
            <p className="big-count"><span className="num" style={{ color: 'var(--blue)' }}>{a.competitors}</span><span>{plural(a.competitors, 'existing outlet').replace(/^\d+ /, '')} nearby</span></p>
            <p><strong>{level}</strong> competition for {a.category_name.toLowerCase()} in {a.area.name}.</p>
          </section>
          <section className="blockbox">
            <h2 className="h2">Access</h2>
            <p className="row"><Bus size={18} aria-hidden /> Public transport: <strong>{a.access.transit}</strong></p>
            {a.access.road ? <p className="row"><Route size={18} aria-hidden /> {a.access.road}</p> : null}
            <div className="stack-sm"><p className="row"><Footprints size={18} aria-hidden /> Footfall index <strong>{Math.round(a.access.footfall_index * 100)}/100</strong></p>
              <div className="meter"><span style={{ width: `${a.access.footfall_index * 100}%` }} /></div></div>
            {a.access.notes ? <p className="meta">{a.access.notes}</p> : null}
          </section>
        </div>
        <section className="panel stack">
          <h2 className="h2">Next step</h2>
          <div className="desktop-only cta-row">{cta}{best ? <Button variant="secondary" size="lg" onClick={() => (user ? setComposer('brief') : login())} disabled={a.brief_requested}>{a.brief_requested ? 'Brief requested' : 'Request a market brief'}</Button> : null}</div>
          <p className="meta">A market brief from the BizYukti team covers rent ranges, footfall by hour and nearby outlets. Area statistics in this demo are illustrative.</p>
        </section>
        {a.brief_requested ? <Notice tone="success">You requested a market brief for this area. Replies arrive in your inbox.</Notice> : null}
        <div className="mobile-only"><StickyCTA>{cta}</StickyCTA></div>
      </div>
      <MessageModal open={!!composer} onClose={() => setComposer(null)} onSend={send}
        title={composer === 'brief' ? 'Request a market brief' : 'Contact the owner'} cta={composer === 'brief' ? 'Request brief' : 'Send message'}
        intro={composer === 'brief' ? `For ${a.category_name.toLowerCase()} in ${a.area.name}.` : best ? `About the ${best.type_label} in ${best.locality}.` : undefined}
        placeholder={composer === 'brief' ? 'What would help you decide? For example, rents for 400 to 800 sq ft and footfall after 6 pm.' : "We're planning to open here. Is the space available, and when could we visit?"} />
    </AppShell>
  )
}

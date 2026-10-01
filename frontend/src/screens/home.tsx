'use client'
import Link from 'next/link'
import { useState } from 'react'
import { Plus, TrendingUp } from 'lucide-react'
import { cap, demandLine } from '@/components/cards'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Empty, LinkButton, Notice, Skeleton } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import { firstName, greeting, num, plural, price, sqft, STATUS_LABEL } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { Me, Space } from '@/lib/types'
import BusinessHome from './business-home'
import ResidentHome from './resident-home'

export default function Home() {
  const user = useRequireAuth()
  return (
    <AppShell>
      <div className="container">
        {!user ? <Skeleton rows={4} /> : user.active_role === 'owner' ? <OwnerHome user={user} />
          : user.active_role === 'business' ? <BusinessHome user={user} /> : <ResidentHome user={user} />}
      </div>
    </AppShell>
  )
}

type OwnerData = { spaces: (Space & { matches: number })[]; new_matches_week: number; open_inquiries: number; needs_confirmation: string[] }

type DemandContext = { density: string; supporters: number; radius_m: number; locality: string
  top: { category: string; category_name: string; supporters: number; top_demand_id: string }[] }

function OwnerHome({ user }: { user: Me }) {
  const toast = useToast()
  const { loc } = useLocation()
  const { data, loading, reload } = useApi<OwnerData>('/properties/mine')
  const nearby = useApi<DemandContext>('/geo/demand-context', { lat: loc.lat, lng: loc.lng })
  const [confirming, setConfirming] = useState(false)
  const firstMatched = data?.spaces.find((s) => s.matches > 0)
  const confirmAll = async () => {
    if (!data) return
    setConfirming(true)
    try {
      await Promise.all(data.needs_confirmation.map((id) => http.post(`/properties/${id}/confirm`)))
      toast('Thanks. Your listings are marked as available.')
      reload()
    } catch (e) { toast(errorMessage(e)) } finally { setConfirming(false) }
  }
  return (
    <div className="stack-lg">
      <section className="home-hero">
        <p className="meta">{greeting()}, {firstName(user.name)}</p>
        <h1 className="display-sm">Your spaces, matched to what neighbours want</h1>
        <div className="row"><LinkButton href="/properties/new" size="lg"><Plus size={20} aria-hidden /> Add property</LinkButton></div>
      </section>
      {data?.needs_confirmation.length ? (
        <Notice tone="warn">
          <span><strong>Is your space still available?</strong> {plural(data.needs_confirmation.length, 'listing')} haven&apos;t been confirmed in 30 days. Confirm to keep showing them to businesses.</span>
          <span><Button size="sm" variant="secondary" onClick={confirmAll} loading={confirming}>Yes, still available</Button></span>
        </Notice>
      ) : null}
      {loading ? <Skeleton rows={3} /> : (
        <div className="owner-grid">
          <section className="blockbox accent-orange" aria-labelledby="spaces-h">
            <div className="row-between"><h2 className="h2" id="spaces-h">Your spaces</h2><span className="meta">{plural(data?.spaces.length || 0, 'listing')}</span></div>
            {data?.spaces.length ? (
              <ul className="rows">
                {data.spaces.map((s) => (
                  <li key={s.id}>
                    <Link href={s.status === 'draft' ? `/properties/${s.id}/edit` : `/properties/${s.id}`} className="row-link">
                      {s.cover_url ? <img src={s.cover_url} alt="" className="thumb-sm" /> : <span className="thumb-sm" aria-hidden />}
                      <span>
                        <span className="row-title">{cap(s.type_label)}, {sqft(s.size_sqft) || 'size missing'}</span>
                        <span className="row-meta">
                          <Badge tone={s.status === 'published' ? 'verified' : s.status === 'draft' ? 'pending' : 'warn'} icon={null}>{s.status === 'published' ? 'Live' : STATUS_LABEL[s.status]}</Badge>
                          <span>{price(s)}</span>
                        </span>
                        {s.top_demand ? <span className="space-demand" style={{ marginTop: 6 }}><TrendingUp size={15} aria-hidden /> {demandLine(s.top_demand)}</span>
                          : s.status === 'draft' ? <span className="row-reason">Finish the listing to see matching demand</span> : null}
                      </span>
                      <span className="row-count supply"><strong>{s.matches}</strong><span>matches</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <Empty title="No spaces yet" body="List your first space to see which local demand it fits." action={<LinkButton href="/properties/new">Add property</LinkButton>} />}
          </section>
          <div className="owner-side">
            <section className="blockbox accent-green" aria-labelledby="near-h">
              <h2 className="h2" id="near-h">Demand near {loc.label}</h2>
              {nearby.loading || !nearby.data ? <Skeleton rows={2} height={40} /> : (
                <>
                  <p className="meta">Within 2 km: <strong>{nearby.data.density}</strong> demand, {plural(nearby.data.supporters, 'verified supporter')}</p>
                  {nearby.data.top.length ? (
                    <ul className="rows">{nearby.data.top.slice(0, 3).map((t) => (
                      <li key={t.category}><Link href={`/demands/${t.top_demand_id}`} className="row-link" style={{ minHeight: 56, padding: '10px 14px' }}>
                        <span aria-hidden /><span className="row-title" style={{ fontSize: 15 }}>{t.category_name}</span>
                        <span className="row-count"><strong style={{ fontSize: 18 }}>{num(t.supporters)}</strong></span>
                      </Link></li>))}</ul>
                  ) : <p className="meta">No requests near this location yet.</p>}
                </>
              )}
            </section>
            <section className="blockbox accent-pink">
              <h2 className="h2">Demand matches</h2>
              <p className="big-count"><span className="num">{data?.new_matches_week || 0}</span><span>new this week</span></p>
              {firstMatched ? <LinkButton href={`/properties/${firstMatched.id}/matches`} variant="secondary">See why they match</LinkButton>
                : <p className="meta">Matches appear when a live listing sits near local demand it can host.</p>}
            </section>
            <section className="blockbox accent-blue">
              <h2 className="h2">Inquiries</h2>
              <p className="big-count"><span className="num" style={{ color: 'var(--blue)' }}>{data?.open_inquiries || 0}</span><span>waiting for a reply</span></p>
              <LinkButton href="/inquiries" variant="secondary">Open inbox</LinkButton>
            </section>
          </div>
        </div>
      )}
    </div>
  )
}

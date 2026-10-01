'use client'
import Link from 'next/link'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { Users } from 'lucide-react'
import { cap, MessageModal } from '@/components/cards'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Empty, LinkButton, Modal, Notice, PageHeader, Skeleton } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import { distance, num, sqft } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import type { Inquiry, MatchItem, Space } from '@/lib/types'

type Biz = { interest_id: string; name: string; verified: boolean; note: string | null }

export default function PropertyMatches() {
  const user = useRequireAuth()
  const { id } = useParams<{ id: string }>()
  const params = useSearchParams()
  const router = useRouter()
  const toast = useToast()
  const { data, loading, error } = useApi<{ property: Space; items: MatchItem[] }>(user ? `/properties/${id}/matches` : null)
  const [active, setActive] = useState<MatchItem | null>(null)
  const [businesses, setBusinesses] = useState<Biz[] | null>(null)
  const [chosen, setChosen] = useState<Biz | null>(null)
  const [offering, setOffering] = useState(false)

  const contact = async (m: MatchItem) => {
    setActive(m)
    setBusinesses(null)
    try {
      const d = await http.get<{ businesses: Biz[] }>(`/demands/${m.demand?.id}`)
      setBusinesses(d.businesses)
    } catch (e) { toast(errorMessage(e)); setActive(null) }
  }
  const offer = async () => {
    if (!active) return
    setOffering(true)
    try {
      const r = await http.post<{ notified: number }>(`/properties/${id}/matches/${active.id}/offer`)
      toast(r.notified ? `We told ${r.notified} businesses looking for ${active.demand?.category_name.toLowerCase()} about your space.` : 'No matching businesses yet. We will tell new ones as they join.')
      setActive(null)
    } catch (e) { toast(errorMessage(e)) } finally { setOffering(false) }
  }
  const send = async (message: string) => {
    if (!chosen) return
    const r = await http.post<Inquiry>('/inquiries', { kind: 'business', interest_id: chosen.interest_id, property_id: id, message })
    router.push(`/inquiries/${r.id}`)
  }

  if (error) return <AppShell><div className="container"><Empty title="Matches aren't available" body={error.message} /></div></AppShell>
  const p = data?.property
  return (
    <AppShell>
      <div className="container stack-lg">
        <PageHeader back={`/properties/${id}`} title="Demand matches" sub={p ? `${cap(p.type_label)}, ${sqft(p.size_sqft)} in ${p.locality}` : undefined} />
        {params.get('new') ? <Notice tone="success"><strong>Your space is live.</strong> Here is the local demand it fits. Your listing reward unlocks after 3 days if it passes checks.</Notice> : null}
        {loading || !data ? <Skeleton rows={3} height={160} /> : data.items.length ? (
          <ol className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {data.items.map((m) => (
              <li key={m.id} className="panel stack">
                <div className="row-between">
                  <Badge tone={m.score >= 80 ? 'strong' : m.score >= 70 ? 'promising' : 'early'}>{m.fit_label}: {m.score}% match</Badge>
                  {m.status === 'contacted' ? <Badge tone="blue">Contacted</Badge> : null}
                </div>
                <div className="row-between" style={{ alignItems: 'flex-start' }}>
                  <div className="stack-sm">
                    <h2 className="h2">{m.demand?.display_title}</h2>
                    <p className="row meta"><Users size={14} aria-hidden /> {num(m.cluster_supporters || m.demand?.supporters || 0)} residents asking nearby, {distance(m.distance_m)}</p>
                  </div>
                  <div className="stat stat-pink" style={{ textAlign: 'right' }}><span className="stat-value" style={{ fontSize: 28, lineHeight: '32px' }}>{m.density?.label}</span><span className="stat-label">2 km demand density</span></div>
                </div>
                <p className="why"><span>{m.summary}</span></p>
                {m.reasons.length ? <ul className="meta" style={{ margin: 0, paddingLeft: 18 }}>{m.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : null}
                <div className="cta-row">
                  <LinkButton href={`/demands/${m.demand?.id}`} variant="secondary">View demand</LinkButton>
                  <Button onClick={() => contact(m)}>{m.interested_businesses ? `Contact business (${m.interested_businesses})` : 'Contact business'}</Button>
                </div>
              </li>
            ))}
          </ol>
        ) : <Empty title="No matches yet" body="Matches appear when residents nearby ask for a business your space can host. We'll notify you." action={<LinkButton href="/home" variant="secondary">Back to your spaces</LinkButton>} />}
      </div>
      <Modal open={!!active && !chosen} onClose={() => setActive(null)} title="Contact a business">
        {!businesses ? <Skeleton rows={2} /> : businesses.length ? (
          <>
            <p>These businesses said they want to open {active?.demand?.category_name.toLowerCase()} here. Pick one to message.</p>
            <ul className="pick-list">{businesses.map((b) => (
              <li key={b.interest_id}><button type="button" onClick={() => setChosen(b)}><span>{b.name}</span>{b.verified ? <Badge tone="verified">Verified</Badge> : null}<span className="meta">{b.note}</span></button></li>
            ))}</ul>
          </>
        ) : (
          <>
            <p>No business has spoken up for this request yet. We can tell businesses looking for {active?.demand?.category_name.toLowerCase()} in your city about your space.</p>
            <Button onClick={offer} loading={offering}>Offer my space to them</Button>
          </>
        )}
        <p className="meta">Prefer to wait? <Link href={`/demands/${active?.demand?.id}`}>See the request</Link> and share it to grow demand.</p>
      </Modal>
      <MessageModal open={!!chosen} onClose={() => { setChosen(null); setActive(null) }} title={`Message ${chosen?.name || ''}`} onSend={send}
        intro={active?.summary} placeholder="My space is close to where the requests are. Would you like to visit?" />
    </AppShell>
  )
}

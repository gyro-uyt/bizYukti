'use client'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Bookmark, BookmarkCheck, CalendarDays, Ruler, ShieldCheck, TrendingUp } from 'lucide-react'
import { BusinessReports } from '@/components/business-reports'
import { cap, MessageModal } from '@/components/cards'
import { MapView } from '@/components/map'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Empty, LinkButton, Notice, PageHeader, Skeleton, StickyCTA } from '@/components/ui'
import { canUse } from '@/lib/access'
import { errorMessage, http } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useLocation } from '@/lib/location'
import { ago, num, price, sqft, STATUS_LABEL } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import type { Inquiry, Space, TopDemand } from '@/lib/types'

type Detail = Space & { matches: number; top_demand: TopDemand | null; is_owner: boolean; blockers: string[]; availability_text: string
  demand_density?: { label: string; supporters: number }; my_inquiry_id?: string | null }

export default function PropertyDetail() {
  const { id } = useParams<{ id: string }>()
  const params = useSearchParams()
  const router = useRouter()
  const toast = useToast()
  const { user, ready } = useAuth()
  const { categories } = useLocation()
  const { data: p, error, loading, reload } = useApi<Detail>(ready ? `/properties/${id}` : null, { u: user?.id })
  const [contact, setContact] = useState(false)
  const [saved, setSaved] = useState(false)
  const [img, setImg] = useState(0)
  useEffect(() => { http.post(`/properties/${id}/view`).catch(() => {}) }, [id])
  useEffect(() => {
    if (user) http.get<{ properties: { property: { id: string } }[] }>('/saved').then((s) => setSaved(s.properties.some((x) => x.property.id === id))).catch(() => {})
  }, [user, id])

  if (error) return <AppShell><div className="container"><Empty title="This space isn't available" body={error.message} action={<LinkButton href="/explore?tab=spaces">Browse spaces</LinkButton>} /></div></AppShell>
  if (loading || !p) return <AppShell><div className="container"><Skeleton rows={3} height={160} /></div></AppShell>

  const toggleSave = async () => {
    if (!user) return router.push(`/login?next=/properties/${id}`)
    try {
      if (saved) await http.del('/saved', { kind: 'property', ref_id: id })
      else await http.post('/saved', { kind: 'property', ref_id: id })
      setSaved(!saved)
      toast(saved ? 'Removed from saved.' : 'Saved. Find it under Saved.')
    } catch (e) { toast(errorMessage(e)) }
  }
  const send = async (message: string) => {
    const r = await http.post<Inquiry>('/inquiries', { kind: 'space', property_id: id, demand_id: params.get('demand') || p.top_demand?.demand_id || undefined, message })
    setContact(false)
    router.push(`/inquiries/${r.id}`)
  }
  const confirm = async () => { try { await http.post(`/properties/${id}/confirm`); await reload(); toast('Marked as still available.') } catch (e) { toast(errorMessage(e)) } }
  const photos = p.media.filter((m) => !m.is_duplicate)
  const cta = p.is_owner
    ? <LinkButton href={`/properties/${id}/matches`} block size="lg">See demand matches ({p.matches})</LinkButton>
    : p.my_inquiry_id ? <LinkButton href={`/inquiries/${p.my_inquiry_id}`} block size="lg" variant="secondary">Open your conversation</LinkButton>
      : <Button block size="lg" onClick={() => (user ? setContact(true) : router.push(`/login?next=/properties/${id}`))}>Contact owner</Button>

  return (
    <AppShell>
      <div className="container stack-lg">
        <PageHeader back={p.is_owner ? '/home' : '/explore?tab=spaces'} title={`${cap(p.type_label)}, ${sqft(p.size_sqft) || 'size not given'}`}
          sub={<span className="row">{p.verified ? <Badge tone="verified">Ownership verified</Badge> : <Badge tone="pending">Not yet verified</Badge>}
            {p.recently_updated ? <Badge tone="blue">Recently updated</Badge> : null}{p.status !== 'published' ? <Badge tone="warn">{STATUS_LABEL[p.status]}</Badge> : null}
            <span className="meta">{p.locality}</span></span>} />
        {p.is_owner && p.status === 'draft' ? <Notice tone="warn">This listing is a draft. Add {p.blockers.join(', ') || 'the last details'} and publish it. <LinkButton href={`/properties/${id}/edit`} size="sm" variant="secondary">Finish listing</LinkButton></Notice> : null}
        {photos.length ? (
          <div className="gallery">
            <img className="gallery-main" src={photos[img]?.url || photos[0].url} alt={`Photo ${img + 1} of ${photos.length}`} />
            <div className="gallery-side">{photos.slice(0, 3).map((m, i) => (
              <button key={m.id} type="button" className={`gallery-thumb${i === img ? ' is-active' : ''}`} onClick={() => setImg(i)}
                aria-label={`Show photo ${i + 1}`} aria-pressed={i === img}>
                <img src={m.thumb_url} alt="" /></button>))}</div>
          </div>
        ) : null}
        <div className="detail-grid">
          <div className="stack-lg">
            <section className="stats prop-facts">
              <div className="stat"><span className="stat-value">{price(p).split('/').map((part, i) => (i ? <span key={i}><wbr />/{part}</span> : part))}</span><span className="stat-label">{p.price_type === 'rent' ? 'Rent' : 'Sale price'}</span></div>
              <div className="stat"><span className="stat-value"><Ruler size={20} aria-hidden /> {sqft(p.size_sqft) || 'Not given'}</span><span className="stat-label">Size</span></div>
              <div className="stat"><span className="stat-value"><CalendarDays size={20} aria-hidden /> {p.availability_text}</span><span className="stat-label">Availability</span></div>
            </section>
            {p.top_demand ? (
              <section className="why">
                <h2 className="h3 row"><TrendingUp size={18} aria-hidden /> Local demand</h2>
                <p><strong>{num(p.top_demand.supporters)} residents nearby</strong> asked for {p.top_demand.category_name.toLowerCase()}. Demand density within 2 km: <strong>{p.demand_density?.label}</strong>.</p>
                <p className="meta">{p.matches} demand matches in total.</p>
              </section>
            ) : null}
            {p.description ? <section className="stack-sm"><h2 className="h3">About this space</h2><p>{p.description}</p></section> : null}
            {p.amenity_labels.length ? <section className="stack-sm"><h2 className="h3">Features</h2><div className="chips">{p.amenity_labels.map((a) => <Badge key={a} tone="neutral">{a}</Badge>)}</div></section> : null}
            <p className="meta row"><ShieldCheck size={14} aria-hidden /> Listed by {p.owner?.name || 'the owner'}. Confirmed available {ago(p.last_confirmed_at)}.</p>
          </div>
          <aside className="stack">
            {p.lat != null && p.lng != null ? <MapView center={{ lat: p.lat, lng: p.lng }} zoom={15} height={240} points={[{ id: p.id, lat: p.lat, lng: p.lng, kind: 'space', label: p.display_title }]} ariaLabel={`Map showing the area of this ${p.type_label}`} /> : null}
            <div className="desktop-only stack-sm">{cta}</div>
            {!p.is_owner ? <Button variant="secondary" block onClick={toggleSave}>{saved ? <BookmarkCheck size={18} aria-hidden /> : <Bookmark size={18} aria-hidden />} {saved ? 'Saved' : 'Save space'}</Button> : (
              <div className="stack-sm">
                <LinkButton href={`/properties/${id}/edit`} variant="secondary" block>Edit listing</LinkButton>
                {!p.recently_updated && p.status !== 'draft' ? <Button variant="secondary" block onClick={confirm}>Still available</Button> : null}
                <p className="meta">{num(p.views || 0)} views. Quality {p.quality_score ?? 0}/100.</p>
              </div>
            )}
          </aside>
        </div>
        {canUse(user, 'reports') && !p.is_owner && p.status === 'published' ? (
          <BusinessReports propertyId={p.id}
            categoryChoices={categories.filter((c) => c.slug !== 'other' && c.types.includes(p.type)).map((c) => ({ slug: c.slug, name: c.name }))} />
        ) : null}
        <div className="mobile-only"><StickyCTA>{cta}</StickyCTA></div>
      </div>
      <MessageModal open={contact} onClose={() => setContact(false)} title="Contact the owner" onSend={send}
        intro={`About the ${p.type_label} in ${p.locality}.`} placeholder="Hi, I'm planning to open here. Is it available, and when could I visit?" />
    </AppShell>
  )
}

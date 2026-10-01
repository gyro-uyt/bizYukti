'use client'
import Link from 'next/link'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Check, Eye, Share2, ShieldCheck } from 'lucide-react'
import { MessageModal, SpaceRow, StatusBadge, Timeline, TrustBadge } from '@/components/cards'
import { MapView } from '@/components/map'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Empty, LinkButton, Modal, Notice, PageHeader, Skeleton, Stat, StickyCTA } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { date, num, plural } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import type { Demand, MatchItem } from '@/lib/types'

type Detail = Demand & {
  matched_spaces: number; interested_businesses: number; spaces: MatchItem[]
  businesses: { interest_id: string; name: string; verified: boolean; note: string | null }[]
  my_support_reason: string | null; timeline: { state: string; reached: boolean }[]
  reward_hint: { points: number }; private?: { risk_score: number; risk_reasons: string[]; pending_supporters: number }
}

export default function DemandDetail() {
  const { id } = useParams<{ id: string }>()
  const params = useSearchParams()
  const router = useRouter()
  const toast = useToast()
  const { user, ready } = useAuth()
  const { data: d, error, loading, setData, reload } = useApi<Detail>(ready ? `/demands/${id}` : null, { u: user?.id })
  const [busy, setBusy] = useState(false)
  const [interestOpen, setInterestOpen] = useState(false)
  const [confirmClose, setConfirmClose] = useState<'close' | 'fulfil' | null>(null)

  useEffect(() => { http.post(`/demands/${id}/view`).catch(() => {}) }, [id])

  const needLogin = () => router.push(`/login?next=${encodeURIComponent(`/demands/${id}`)}`)
  const share = async () => {
    if (!d) return
    try {
      const r = await http.post<{ url: string; text: string }>(`/demands/${id}/share`)
      if (navigator.share) await navigator.share({ title: d.display_title, text: r.text, url: r.url })
      else { await navigator.clipboard.writeText(`${r.text} ${r.url}`); toast('Link copied. Share it with neighbours.') }
    } catch { /* share sheet dismissed */ }
  }
  const support = async () => {
    if (!user) return needLogin()
    setBusy(true)
    try {
      const r = await http.post<{ support: { status: string; reason: string | null }; demand: Demand }>(`/demands/${id}/support`)
      setData((prev) => (prev ? { ...prev, ...r.demand, my_support: r.support.status, my_support_reason: r.support.reason } : prev))
      toast(r.support.status === 'verified' ? `Thanks! Your support counts. +${d?.reward_hint.points ?? 2} points pending.` : r.support.reason || 'Support recorded.')
    } catch (e) { toast(errorMessage(e)) } finally { setBusy(false) }
  }
  const withdraw = async () => {
    setBusy(true)
    try { await http.del(`/demands/${id}/support`); await reload(); toast('Your support was withdrawn.') } catch (e) { toast(errorMessage(e)) } finally { setBusy(false) }
  }
  const expressInterest = async (note: string) => {
    await http.post(`/demands/${id}/interest`, { note })
    setInterestOpen(false)
    await reload()
    toast('The requester was told a business is interested.')
  }
  const closeOrFulfil = async () => {
    if (!confirmClose) return
    try {
      await http.post(`/demands/${id}/${confirmClose === 'close' ? 'close' : 'fulfil'}`)
      setConfirmClose(null)
      await reload()
      toast(confirmClose === 'fulfil' ? 'Marked as opened. Supporters will be thanked with points.' : 'Request closed.')
    } catch (e) { toast(errorMessage(e)) }
  }

  if (error) return <AppShell><div className="container"><Empty title="This request isn't available" body={error.message} action={<LinkButton href="/explore">Explore requests</LinkButton>} /></div></AppShell>
  if (loading || !d) return <AppShell><div className="container"><Skeleton rows={4} height={120} /></div></AppShell>

  const live = ['published', 'growing', 'matched'].includes(d.status)
  const role = user?.active_role
  const isBusiness = !!user && role === 'business' && user.roles.includes('business')
  const isOwner = !!user && role === 'owner'
  const supported = !!d.my_support && d.my_support !== 'rejected'

  let cta = null
  if (live && !d.mine) {
    if (isBusiness) {
      cta = d.interested ? <Button variant="secondary" block onClick={async () => { await http.del(`/demands/${id}/interest`); reload() }}><Check size={18} aria-hidden /> You&apos;re interested</Button>
        : <Button block size="lg" onClick={() => setInterestOpen(true)}>Express interest</Button>
    } else if (isOwner) {
      cta = <LinkButton href="/properties/new" block size="lg">Offer my space</LinkButton>
    } else {
      cta = supported ? <Button variant="success" block size="lg" onClick={withdraw} loading={busy} aria-label="You support this. Withdraw support"><Check size={18} aria-hidden /> You support this</Button>
        : <Button variant="pink" block size="lg" onClick={support} loading={busy}>Support</Button>
    }
  }

  return (
    <AppShell>
      <div className="container stack-lg">
        {params.get('new') ? (
          <Notice tone="success">
            <strong>Your request is live.</strong> It becomes verified local demand once {3} neighbours support it. Share it to get there faster.
            <span><Button size="sm" onClick={share}><Share2 size={16} aria-hidden /> Share with neighbours</Button></span>
          </Notice>
        ) : null}
        <div className="detail-grid">
          <div className="stack-lg">
            <PageHeader back="/explore" title={d.display_title} sub={<span className="row"><TrustBadge verified={d.verified} /><StatusBadge status={d.status} /><span className="meta">{d.category_name}</span></span>} />
            <section className="stack">
              <p className="big-count"><span className="num">{num(d.supporters)}</span><span>{d.supporters === 1 ? 'resident supports this' : 'residents support this'}</span></p>
              <p className="meta row"><ShieldCheck size={14} aria-hidden /> Counted only from verified residents within 5 km.
                {d.pending_supporters ? ` ${plural(d.pending_supporters, 'more person', 'more people')} waiting for verification.` : ''}
                <span className="row" style={{ gap: 4 }}><Eye size={14} aria-hidden /> {plural(d.views, 'view')}</span></p>
              {d.my_support === 'pending' && d.my_support_reason ? <Notice tone="warn">Your support isn&apos;t counted yet: {d.my_support_reason}. <Link href="/profile">Update your profile</Link></Notice> : null}
              {d.my_support === 'rejected' && d.my_support_reason ? <Notice tone="warn">Your support wasn&apos;t counted: {d.my_support_reason}.</Notice> : null}
            </section>
            <section className="why">
              <h2 className="h3">Why it matters</h2>
              <p><strong>{d.reason_label}:</strong> {d.why}</p>
              {d.author ? <p className="meta">Requested by {d.author.name} on {date(d.published_at)}</p> : null}
            </section>
            <section className="stack-sm">
              <h2 className="h3">Progress</h2>
              <Timeline items={d.timeline} current={d.status} />
            </section>
            <section className="stack">
              <div className="section-head"><h2 className="h2">Matched spaces</h2>{d.matched_spaces > 3 ? <span className="meta">Top 3 of {d.matched_spaces}</span> : null}</div>
              {d.spaces.length ? (
                <ul className="rows">{d.spaces.map((m) => m.property ? (
                  <li key={m.id}><SpaceRow s={m.property} extra={<span className="meta">{m.score}% fit. {m.summary}</span>} /></li>) : null)}</ul>
              ) : <p className="meta">No listed space fits this yet. Owners nearby are notified as demand grows.</p>}
            </section>
          </div>
          <aside className="stack">
            <div className="stats">
              <Stat value={d.matched_spaces} label="Matched spaces" tone="orange" />
              <Stat value={d.interested_businesses} label="Interested businesses" tone="blue" />
            </div>
            {d.businesses.length ? (
              <div className="panel panel-tight stack-sm">
                <h2 className="h3">Businesses interested</h2>
                {d.businesses.map((b) => <p key={b.interest_id} className="row">{b.name}{b.verified ? <Badge tone="verified">Verified business</Badge> : null}</p>)}
              </div>
            ) : null}
            <MapView center={{ lat: d.lat, lng: d.lng }} zoom={14} height={220} points={[{ id: d.id, lat: d.lat, lng: d.lng, kind: 'demand', label: d.display_title }]} ariaLabel={`Map showing ${d.display_title}`} />
            <div className="stack-sm">
              {cta ? <div className="desktop-only">{cta}</div> : null}
              <Button variant="secondary" block onClick={share}><Share2 size={18} aria-hidden /> Share</Button>
              {d.mine && live ? (
                <div className="row">
                  <Button variant="secondary" size="sm" onClick={() => setConfirmClose('fulfil')}>It opened</Button>
                  <Button variant="danger" size="sm" onClick={() => setConfirmClose('close')}>Close request</Button>
                </div>
              ) : null}
            </div>
            {d.private?.risk_reasons.length ? <Notice tone="warn">Held for a quick review: {d.private.risk_reasons.join(', ')}.</Notice> : null}
          </aside>
        </div>
        {cta ? <div className="mobile-only"><StickyCTA>{cta}</StickyCTA></div> : null}
      </div>
      <MessageModal open={interestOpen} onClose={() => setInterestOpen(false)} title="Express interest" cta="Send interest"
        intro={`The requester and ${num(d.supporters)} supporters will see that a business is considering ${d.display_title.toLowerCase()}.`}
        placeholder="We're planning an outlet here and are looking at spaces." onSend={expressInterest} />
      <Modal open={!!confirmClose} onClose={() => setConfirmClose(null)} title={confirmClose === 'fulfil' ? 'Did it open?' : 'Close this request?'}
        footer={<><Button variant="secondary" onClick={() => setConfirmClose(null)}>Cancel</Button><Button onClick={closeOrFulfil} variant={confirmClose === 'close' ? 'danger' : 'primary'}>{confirmClose === 'fulfil' ? 'Yes, it opened' : 'Close request'}</Button></>}>
        <p>{confirmClose === 'fulfil' ? 'Supporters are thanked and everyone who helped earns points.' : 'It stops collecting support. You can post it again later.'}</p>
      </Modal>
    </AppShell>
  )
}

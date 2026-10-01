'use client'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Briefcase, Check, Flame, Heart, MapPin, RefreshCw, ShieldCheck, Star, TrendingUp, X } from 'lucide-react'
import { errorMessage, http } from '@/lib/api'
// Real photos for the business types we have imagery for; other categories fall back to the tag's 3D image.
import { CATEGORY_PHOTOS } from '@/lib/category-media'
import { distance, firstName, num } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { Demand, Me } from '@/lib/types'
import { useToast } from './toast'
import { Badge, Button, Skeleton, type Tone } from './ui'

type Pick = { demand: Demand; reasons: string[]; tag: string; score: number }
type Feed = { center: { locality: string; radius_km: number }; insight: string; recommendations: Pick[] }

const LOGO = '/brand/bizyukti-assistant.png'
// Each pick type reuses the existing badge tones, tint colours and the 3D images from the home feature cards.
const TAGS: Record<string, { badge: Tone; tint: 'green' | 'pink' | 'orange' | 'blue'; icon: typeof Flame; img: string }> = {
  'Help verify': { badge: 'verified', tint: 'green', icon: ShieldCheck, img: '/landing/verified-demand.webp' },
  Trending: { badge: 'demand', tint: 'pink', icon: Flame, img: '/landing/fresh-spaces.webp' },
  'Almost growing': { badge: 'promising', tint: 'orange', icon: TrendingUp, img: '/landing/rewards.webp' },
  'Business interested': { badge: 'blue', tint: 'blue', icon: Briefcase, img: '/landing/fresh-spaces.webp' },
  'For you': { badge: 'blue', tint: 'blue', icon: Heart, img: '/landing/verified-demand.webp' },
  'Popular nearby': { badge: 'demand', tint: 'pink', icon: Star, img: '/landing/fresh-spaces.webp' },
}

/** Floating assistant for residents: one tap opens a few explained picks for the chosen location. */
export function AiAssistant({ user }: { user: Me }) {
  const { loc } = useLocation()
  const [open, setOpen] = useState(false)
  const [seen, setSeen] = useState(false)
  const panel = useRef<HTMLDivElement>(null)
  const fab = useRef<HTMLButtonElement>(null)
  // Loaded on first open, then kept in step with the chosen location.
  const feed = useApi<Feed>(seen ? '/demands/for-you' : null, { lat: loc.lat, lng: loc.lng })

  const close = () => { setOpen(false); fab.current?.focus() }
  useEffect(() => {
    if (!open) return
    panel.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const picks = feed.data?.recommendations || []
  return (
    <>
      <button ref={fab} type="button" className={`ai-fab${open ? ' is-open' : ''}`} onClick={() => { setSeen(true); setOpen((o) => !o) }}
        aria-expanded={open} aria-controls="ai-panel" aria-label={open ? 'Close smart picks' : 'Open smart picks for your neighbourhood'}>
        {open ? <X size={26} aria-hidden /> : <img src={LOGO} alt="" aria-hidden />}
        {!open ? <span className="ai-fab-dot" aria-hidden /> : null}
      </button>
      {open ? <div className="ai-backdrop" onClick={close} aria-hidden /> : null}
      {open ? (
        <section id="ai-panel" ref={panel} tabIndex={-1} className="ai-panel" role="dialog" aria-labelledby="ai-title">
          <header className="ai-head">
            <img src={LOGO} alt="" aria-hidden className="ai-avatar" />
            <div className="ai-head-text">
              <h2 id="ai-title" className="h3">Smart picks for {firstName(user.name)}</h2>
              <p className="meta row" style={{ gap: 4 }}><MapPin size={13} aria-hidden /> Near {loc.label}</p>
            </div>
            <button type="button" className="icon-btn" onClick={() => feed.reload()} aria-label="Refresh picks" disabled={feed.loading}>
              <RefreshCw size={18} className={feed.loading ? 'spin' : undefined} />
            </button>
            <button type="button" className="icon-btn" onClick={close} aria-label="Close"><X size={20} /></button>
          </header>

          <div className="ai-body">
            {feed.loading && !feed.data ? <div className="ai-grid"><Skeleton rows={1} height={230} /><Skeleton rows={1} height={230} /></div> : feed.error ? (
              <div className="notice notice-error"><div>Picks aren&apos;t available right now. {feed.error.message}</div></div>
            ) : picks.length ? (
              <>
                <p className="ai-lead">Back these to make the biggest difference near you.</p>
                <ul className="ai-grid">{picks.map((p) => <PickCard key={p.demand.id} p={p} />)}</ul>
              </>
            ) : feed.data ? (
              <div className="empty" style={{ padding: '28px 18px' }}>
                <h3 className="h3">You back everything nearby</h3>
                <p>New requests near {loc.label} will appear here.</p>
              </div>
            ) : null}
          </div>

          <footer className="ai-foot">
            <Link href="/neighbourhood" className="link-quiet row" style={{ gap: 6 }} onClick={() => setOpen(false)}>See all on the map <ArrowRight size={16} aria-hidden /></Link>
          </footer>
        </section>
      ) : null}
    </>
  )
}

function PickCard({ p }: { p: Pick }) {
  const toast = useToast()
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const t = TAGS[p.tag] || TAGS['Popular nearby']
  const d = p.demand
  const photo = CATEGORY_PHOTOS[d.category]
  const count = d.supporters + (status === 'verified' ? 1 : 0)
  const support = async () => {
    setBusy(true)
    try {
      const r = await http.post<{ support: { status: string; reason: string | null } }>(`/demands/${d.id}/support`)
      setStatus(r.support.status)
      toast(r.support.status === 'verified' ? 'Thanks! Your support counts. Points are on the way.' : r.support.reason || 'Support recorded.')
    } catch (e) { toast(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <li className="ai-card">
      <Link href={`/demands/${d.id}`} className={`ai-card-media ci-${t.tint}${photo ? ' has-photo' : ''}`} title={p.reasons[0]} tabIndex={-1} aria-hidden>
        <img src={photo || t.img} alt="" loading="lazy" />
      </Link>
      <div className="ai-card-body">
        <Badge tone={t.badge} icon={<t.icon size={13} aria-hidden />}>{p.tag}</Badge>
        <Link href={`/demands/${d.id}`} className="ai-card-title">{d.title}</Link>
        <p className="ai-card-count"><strong>{num(count)}</strong> neighbours</p>
        <p className="meta ai-card-where"><MapPin size={12} aria-hidden /> {d.locality}{d.distance_m != null ? `, ${distance(d.distance_m).replace(' away', '')}` : ''}</p>
        {status ? <span className="btn btn-success btn-sm btn-block ai-done" role="status"><Check size={16} aria-hidden /> {status === 'verified' ? 'Supported' : 'Recorded'}</span>
          : <Button variant="pink" size="sm" block loading={busy} onClick={support} aria-label={`Support ${d.display_title}`}>Support</Button>}
      </div>
    </li>
  )
}

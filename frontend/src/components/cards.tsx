'use client'
import Link from 'next/link'
import { useState, type ReactNode } from 'react'
import { Clock, Lock, MapPin, ShieldCheck, Store, TrendingUp } from 'lucide-react'
import { errorMessage } from '@/lib/api'
import { distance, num, plural, price, sqft, STATUS_LABEL } from '@/lib/format'
import type { AreaOpp, Demand, Space } from '@/lib/types'
import { Badge, Button, Field, Modal, Notice } from './ui'

export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

export function TrustBadge({ verified }: { verified: boolean }) {
  return verified ? <Badge tone="verified">Verified local demand</Badge> : <Badge tone="pending">Pending verification</Badge>
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === 'matched' ? 'blue' : status === 'growing' ? 'demand' : status === 'fulfilled' ? 'verified' : 'neutral'
  return <Badge tone={tone}>{STATUS_LABEL[status] || status}</Badge>
}

export function DemandRow({ d, rank }: { d: Demand; rank?: number }) {
  return (
    <li>
      <Link href={`/demands/${d.id}`} className="row-link">
        {rank ? <span className={`rank${rank <= 3 ? ' rank-top' : ''}`} aria-hidden>{rank}</span> : <span aria-hidden />}
        <span>
          <span className="row-title">{d.display_title}</span>
          <span className="row-meta">
            {d.distance_m != null ? <span><MapPin size={13} aria-hidden /> {distance(d.distance_m)}</span> : null}
            <span>{d.category_name}</span>
            {d.verified ? <span className="ok"><ShieldCheck size={13} aria-hidden /> Verified</span> : <span><Clock size={13} aria-hidden /> Pending verification</span>}
            {d.status === 'matched' ? <span>Businesses interested</span> : null}
            {d.status === 'fulfilled' ? <span className="ok">Opened</span> : null}
            {d.my_support === 'verified' ? <span className="mine">You support this</span> : null}
          </span>
        </span>
        <span className="row-count"><strong>{num(d.supporters)}</strong><span>{d.supporters === 1 ? 'supporter' : 'supporters'}</span></span>
      </Link>
    </li>
  )
}

export function demandLine(top: { category_name: string; supporters: number } | null | undefined) {
  if (!top) return null
  return `${top.supporters >= 40 ? 'High demand nearby' : 'Demand nearby'}: ${top.category_name.toLowerCase()}`
}

export function SpaceCard({ s, href, note }: { s: Space; href?: string; note?: ReactNode }) {
  const top = s.top_demand || s.demand?.top
  return (
    <Link href={href || `/properties/${s.id}`} className="space-card">
      {s.cover_url ? <img className="space-thumb" src={s.cover_url} alt="" loading="lazy" /> : <div className="space-thumb space-thumb-empty"><Store size={28} aria-hidden /></div>}
      <div className="space-body">
        <div className="row-between"><span className="space-price">{price(s)}</span>{s.verified ? <Badge tone="verified">Verified</Badge> : null}</div>
        <span className="row-title">{cap(s.type_label)}, {sqft(s.size_sqft) || 'size not given'}</span>
        <span className="meta">{s.locality}{s.distance_m != null ? `, ${distance(s.distance_m)}` : ''}</span>
        {top ? <span className="space-demand"><TrendingUp size={15} aria-hidden /> {demandLine(top)}</span> : null}
        {s.recently_updated ? <span className="meta">Recently updated</span> : null}
        {note}
      </div>
    </Link>
  )
}

export function SpaceRow({ s, href, extra }: { s: Space; href?: string; extra?: ReactNode }) {
  return (
    <Link href={href || `/properties/${s.id}`} className="space-row">
      {s.cover_url ? <img src={s.cover_url} alt="" loading="lazy" /> : <span className="space-thumb space-thumb-empty"><Store size={22} aria-hidden /></span>}
      <span className="stack-sm">
        <span className="row-title">{cap(s.type_label)}, {sqft(s.size_sqft)}</span>
        <span className="meta">{price(s)}{s.locality ? `, ${s.locality}` : ''}</span>
        {extra}
      </span>
    </Link>
  )
}

export function AreaRow({ a, rank, href }: { a: AreaOpp; rank?: number; href: string }) {
  const rising = a.trend.direction === 'rising' || a.trend.direction === 'new'
  return (
    <li>
      <Link href={href} className="row-link">
        <span className={`rank${rank && rank <= 3 ? ' rank-top' : ''}`} aria-hidden>{rank}</span>
        <span>
          <span className="row-title">{a.area.name}</span>
          <span className="row-meta">
            <Badge tone={a.tone}>{a.label}</Badge>
            <span>{plural(a.spaces, 'matching space')}</span>
            <span>{a.competitors === 0 ? 'No competitors recorded' : plural(a.competitors, 'competitor')}</span>
            {rising ? <span className="up"><TrendingUp size={13} aria-hidden /> {a.trend.text}</span> : null}
          </span>
          <span className="row-reason">{a.reasons[0]}</span>
        </span>
        <span className="row-count"><strong>{num(a.supporters)}</strong><span>supporters</span></span>
      </Link>
    </li>
  )
}

export function Timeline({ items, current }: { items: { state: string; reached: boolean }[]; current: string }) {
  return (
    <ol className="timeline" aria-label="Request progress">
      {items.map((t) => (
        <li key={t.state} className={`${t.reached ? 'is-reached' : ''}${t.state === current ? ' is-current' : ''}`} aria-current={t.state === current ? 'step' : undefined}>
          {STATUS_LABEL[t.state] || t.state}
        </li>
      ))}
    </ol>
  )
}

export function MessageModal({ open, onClose, title, intro, placeholder, onSend, cta = 'Send message', initial = '' }:
  { open: boolean; onClose: () => void; title: string; intro?: ReactNode; placeholder?: string; onSend: (text: string) => Promise<void>; cta?: string; initial?: string }) {
  const [text, setText] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSend(text.trim())
      setText('')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={title}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={busy} disabled={text.trim().length < 2}>{cta}</Button></>}>
      {intro ? <div className="meta">{intro}</div> : null}
      <Field label="Message" htmlFor="msg-body">
        <textarea id="msg-body" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} maxLength={2000} />
      </Field>
      <p className="meta row"><Lock size={14} aria-hidden /> Your phone and email stay private. Share them in the chat only if you want to.</p>
      {error ? <Notice tone="error">{error}</Notice> : null}
    </Modal>
  )
}

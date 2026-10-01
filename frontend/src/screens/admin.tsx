'use client'
import Link from 'next/link'
import { useState } from 'react'
import { FileText } from 'lucide-react'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Chip, Empty, Field, Modal, PageHeader, Skeleton, Stat, Tabs } from '@/components/ui'
import { apiBlob, errorMessage, http } from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import { ago, num, pct } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import type { Demand, Inquiry, Space } from '@/lib/types'

type Item = { id: string; subject_type: string; subject_id: string; kind: string; status: string; reason: string | null; created_at: string
  evidence: Record<string, unknown>; has_document: boolean
  subject: { demand?: Demand & { risk_score: number; risk_reasons: string[] }; property?: Space; business?: { name: string; registration_id: string | null; website: string | null }
    support?: { status: string; reason: string | null; distance_m: number | null } } | null }
type Stats = { north_star: { label: string; value: number; definition: string }; kpis: { key: string; label: string; value: number | null; unit?: string }[]
  retention_30d: { role: string; cohort: number; rate: number | null }[]; totals: Record<string, number>; events_7d: { name: string; count: number }[] }

const KIND: Record<string, string> = { risk_review: 'Risk review', ownership_document: 'Ownership documents', kyb: 'Business verification', manual: 'Manual review' }
const TYPES = ['', 'demand', 'property', 'business', 'support']

export default function Admin() {
  const user = useRequireAuth({ role: 'admin' })
  const toast = useToast()
  const [tab, setTab] = useState<'queue' | 'kpis' | 'team'>('queue')
  const [type, setType] = useState('')
  const queue = useApi<{ counts: Record<string, number>; items: Item[] }>(user && tab === 'queue' ? '/admin/queue' : null, { subject_type: type })
  const stats = useApi<Stats>(user && tab === 'kpis' ? '/admin/stats' : null)
  const team = useApi<{ items: Inquiry[] }>(user && tab === 'team' ? '/inquiries' : null, { box: 'team' })
  const [rejecting, setRejecting] = useState<Item | null>(null)
  const [reason, setReason] = useState('')
  const decide = async (item: Item, decision: 'approve' | 'reject', why?: string) => {
    try { await http.post(`/admin/verifications/${item.id}/decide`, { decision, reason: why || null }); toast(decision === 'approve' ? 'Approved.' : 'Rejected.'); setRejecting(null); setReason(''); queue.reload() }
    catch (e) { toast(errorMessage(e)) }
  }
  const openDoc = async (item: Item) => {
    try { const blob = await apiBlob(`/admin/verifications/${item.id}/document`); window.open(URL.createObjectURL(blob), '_blank', 'noopener') } catch (e) { toast(errorMessage(e)) }
  }
  if (!user) return null
  const total = Object.values(queue.data?.counts || {}).reduce((a, b) => a + b, 0)
  return (
    <AppShell>
      <div className="container stack">
        <PageHeader title="Admin review" sub="Verification queue, moderation and the launch KPIs." />
        <Tabs label="Admin" value={tab} onChange={setTab} tabs={[{ key: 'queue', label: 'Review queue', count: queue.data ? total : undefined }, { key: 'kpis', label: 'KPIs' }, { key: 'team', label: 'Team inbox' }]} />
        {tab === 'queue' ? (
          <>
            <div className="chips">{TYPES.map((t) => <Chip key={t || 'all'} selected={type === t} onClick={() => setType(t)}>{t ? `${t[0].toUpperCase()}${t.slice(1)} (${queue.data?.counts[t] || 0})` : 'All'}</Chip>)}</div>
            {queue.loading || !queue.data ? <Skeleton rows={3} height={120} /> : queue.data.items.length ? (
              <ul className="stack" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {queue.data.items.map((it) => (
                  <li key={it.id} className="panel stack-sm">
                    <div className="row-between"><span className="row"><Badge tone="warn">{KIND[it.kind] || it.kind}</Badge><span className="meta">{it.subject_type}, submitted {ago(it.created_at)}</span></span></div>
                    {it.subject?.demand ? (<>
                      <Link href={`/demands/${it.subject.demand.id}`} className="h3">{it.subject.demand.display_title}</Link>
                      <p className="meta">Risk {Math.round(it.subject.demand.risk_score * 100)}/100: {it.subject.demand.risk_reasons.join(', ') || 'no automatic flags'}</p>
                      {it.subject.support ? <p className="meta">Support status {it.subject.support.status}: {it.subject.support.reason}</p> : null}
                    </>) : null}
                    {it.subject?.property ? (<>
                      <Link href={`/properties/${it.subject.property.id}`} className="h3">{it.subject.property.display_title} in {it.subject.property.locality}</Link>
                      <p className="meta">Document: {String(it.evidence.document_type || 'not given')}{it.evidence.note ? `. Note: ${String(it.evidence.note)}` : ''}</p>
                      {it.has_document ? <Button size="sm" variant="secondary" onClick={() => openDoc(it)}><FileText size={16} aria-hidden /> Open document</Button> : <p className="meta">No file attached.</p>}
                    </>) : null}
                    {it.subject?.business ? (<>
                      <p className="h3">{it.subject.business.name}</p>
                      <p className="meta">GSTIN or registration: {it.subject.business.registration_id || 'not given'}. Website: {it.subject.business.website || 'not given'}</p>
                    </>) : null}
                    <div className="row"><Button size="sm" onClick={() => decide(it, 'approve')}>Approve</Button><Button size="sm" variant="danger" onClick={() => setRejecting(it)}>Reject</Button></div>
                  </li>
                ))}
              </ul>
            ) : <Empty title="Nothing to review" body="New risk flags and verification requests appear here." />}
          </>
        ) : null}
        {tab === 'kpis' ? (stats.loading || !stats.data ? <Skeleton rows={3} height={120} /> : (
          <div className="stack-lg">
            <section className="balance"><p className="meta">North star: {stats.data.north_star.label}</p><p className="num">{num(stats.data.north_star.value)}</p><p className="meta">{stats.data.north_star.definition}</p></section>
            <div className="stats">
              <Stat value={num(stats.data.totals.live_demands)} label="Live requests" tone="pink" />
              <Stat value={num(stats.data.totals.supports)} label="Supports" tone="pink" />
              <Stat value={num(stats.data.totals.published_properties)} label="Live spaces" tone="orange" />
              <Stat value={num(stats.data.totals.matches)} label="Matches" tone="blue" />
              <Stat value={num(stats.data.totals.users)} label="People" />
            </div>
            <div className="table-wrap"><table className="kpi-table"><thead><tr><th>KPI (PRD section 14)</th><th style={{ textAlign: 'right' }}>Value</th></tr></thead>
              <tbody>{stats.data.kpis.map((k) => <tr key={k.key}><td>{k.label}</td><td className="n">{k.unit === 'hours' ? (k.value == null ? 'No data yet' : `${k.value} h`) : pct(k.value)}</td></tr>)}
                {stats.data.retention_30d.map((r) => <tr key={r.role}><td>30-day retention, {r.role} ({num(r.cohort)} people)</td><td className="n">{pct(r.rate)}</td></tr>)}</tbody></table></div>
            <section className="stack-sm"><h2 className="h3">Events in the last 7 days</h2>
              <div className="chips">{stats.data.events_7d.map((e) => <Badge key={e.name} tone="neutral">{e.name}: {num(e.count)}</Badge>)}</div></section>
          </div>
        )) : null}
        {tab === 'team' ? (team.loading || !team.data ? <Skeleton rows={3} /> : team.data.items.length ? (
          <ul className="rows">{team.data.items.map((i) => (
            <li key={i.id}><Link href={`/inquiries/${i.id}`} className="row-link"><span aria-hidden /><span><span className="row-title">{i.subject}</span><span className="row-meta"><span>From {i.with.name}</span><span>{i.status}</span></span></span><span className="meta">{ago(i.last_message_at)}</span></Link></li>
          ))}</ul>) : <Empty title="No market brief requests" />) : null}
      </div>
      <Modal open={!!rejecting} onClose={() => setRejecting(null)} title="Reject this item"
        footer={<><Button variant="secondary" onClick={() => setRejecting(null)}>Cancel</Button><Button variant="danger" onClick={() => rejecting && decide(rejecting, 'reject', reason)}>Reject</Button></>}>
        <Field label="Reason shown to the person" htmlFor="why"><textarea id="why" className="input" value={reason} maxLength={240} onChange={(e) => setReason(e.target.value)} placeholder="For example: the document doesn't show this address." /></Field>
      </Modal>
    </AppShell>
  )
}

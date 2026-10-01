'use client'
import { useState } from 'react'
import { Clock, Gift, Ticket } from 'lucide-react'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Modal, PageHeader, Progress, Skeleton } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import { date, num } from '@/lib/format'
import { useApi } from '@/lib/hooks'

type Entry = { id: string; action: string; label: string; points: number; status: string; note: string | null; voucher_code: string | null; expected_unlock_at: string | null; created_at: string }
type Offer = { id: string; title: string; points: number; kind: string; detail: string; affordable: boolean }
type Summary = { balance: number; pending: number; lifetime: number; tier: { name: string; next_name: string | null; next_at: number | null; progress: number }
  entries: Entry[]; offers: Offer[]; rules: Record<string, { points: number; label: string }> }

const EARN = [
  ['demand_published', 'Publish a request (unlocks once verified)'], ['demand_supported', 'Support a nearby request (up to 5 a day)'],
  ['demand_growing', 'Your request reaches 10 verified supporters'], ['demand_fulfilled', 'The business you asked for opens'],
  ['supported_fulfilled', 'A request you supported opens'], ['property_listed', 'List a space that passes checks'], ['property_verified', 'Verify ownership of a space'],
]

export default function Rewards() {
  const user = useRequireAuth()
  const toast = useToast()
  const { data, loading, setData } = useApi<Summary>(user ? '/rewards' : null)
  const [voucher, setVoucher] = useState<{ code: string; title: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const redeem = async (o: Offer) => {
    setBusy(o.id)
    try {
      const r = await http.post<{ voucher_code: string; title: string; summary: Summary }>('/rewards/redeem', { offer_id: o.id })
      setData(r.summary)
      setVoucher({ code: r.voucher_code, title: r.title })
    } catch (e) { toast(errorMessage(e)) } finally { setBusy(null) }
  }
  const pending = (data?.entries || []).filter((e) => e.status === 'pending')
  const history = (data?.entries || []).filter((e) => e.status !== 'pending')
  return (
    <AppShell>
      <div className="container stack-lg">
        <PageHeader title="Rewards" sub="Points for helping your area get what it needs. They unlock once the action is verified." />
        {loading || !data ? <Skeleton rows={3} height={120} /> : (
          <>
            <section className="balance" aria-label="Your points">
              <p className="meta">Available to use</p>
              <p className="row" style={{ alignItems: 'baseline' }}><span className="num">{num(data.balance)}</span><span>points</span></p>
              <p className="meta">{data.pending ? `${num(data.pending)} more pending verification. ` : ''}Level: <strong style={{ color: '#fff' }}>{data.tier.name}</strong></p>
              {data.tier.next_name ? <><Progress value={data.tier.progress} /><p className="meta">{num(Math.max(0, (data.tier.next_at || 0) - data.lifetime))} points to {data.tier.next_name}</p></> : null}
            </section>
            {pending.length ? (
              <section className="stack">
                <h2 className="h2">Pending verification</h2>
                <ul className="rows">{pending.map((e) => (
                  <li key={e.id} className="row-link" style={{ cursor: 'default' }}>
                    <span className="row-icon ci-blue"><Clock size={18} aria-hidden /></span>
                    <span><span className="row-title">{e.label}</span><span className="row-meta"><span>{e.note}</span>{e.expected_unlock_at ? <span>Earliest unlock {date(e.expected_unlock_at)}</span> : null}</span></span>
                    <span className="row-count"><strong style={{ color: 'var(--muted)' }}>+{e.points}</strong><span>pending</span></span>
                  </li>))}</ul>
              </section>
            ) : null}
            <section className="stack">
              <h2 className="h2">Use your points</h2>
              <div className="grid-cards">{data.offers.map((o) => (
                <div key={o.id} className="panel offer">
                  <div className="stack-sm"><span className="choice-icon ci-green"><Gift size={22} aria-hidden /></span><h3 className="h3">{o.title}</h3><p className="meta">{o.detail}</p></div>
                  <div className="row-between"><strong>{num(o.points)} points</strong>
                    <Button size="sm" variant={o.affordable ? 'primary' : 'secondary'} disabled={!o.affordable} loading={busy === o.id} onClick={() => redeem(o)}>
                      {o.affordable ? 'Redeem' : `Need ${num(o.points - data.balance)} more`}</Button></div>
                </div>))}</div>
            </section>
            <section className="grid-2">
              <div className="stack">
                <h2 className="h2">How to earn</h2>
                <ul className="rows">{EARN.map(([k, label]) => (
                  <li key={k} className="row-link" style={{ cursor: 'default', minHeight: 56 }}><span aria-hidden /><span>{label}</span><span className="row-count"><strong style={{ color: 'var(--green-ink)' }}>+{data.rules[k]?.points}</strong></span></li>))}</ul>
              </div>
              <div className="stack">
                <h2 className="h2">History</h2>
                {history.length ? <ul className="rows">{history.map((e) => (
                  <li key={e.id} className="row-link" style={{ cursor: 'default', minHeight: 56 }}>
                    <span aria-hidden />
                    <span><span className="row-title" style={{ fontSize: 15 }}>{e.action === 'redeem' ? e.note : e.label}</span>
                      <span className="row-meta"><span>{date(e.created_at)}</span>{e.status === 'reversed' ? <Badge tone="warn">Reversed</Badge> : null}{e.voucher_code ? <span><Ticket size={13} aria-hidden /> {e.voucher_code}</span> : null}</span></span>
                    <span className="row-count"><strong style={{ color: e.points < 0 ? 'var(--ink)' : e.status === 'reversed' ? 'var(--muted)' : 'var(--green-ink)' }}>{e.points > 0 ? '+' : ''}{e.points}</strong></span>
                  </li>))}</ul> : <p className="meta">Your earned and used points appear here.</p>}
              </div>
            </section>
          </>
        )}
      </div>
      <Modal open={!!voucher} onClose={() => setVoucher(null)} title="Reward redeemed" footer={<Button onClick={() => setVoucher(null)}>Done</Button>}>
        <p>{voucher?.title}</p>
        <p className="h1 num" style={{ letterSpacing: '.08em' }}>{voucher?.code}</p>
        <p className="meta">Show this code at the partner. It&apos;s also saved in your history.</p>
      </Modal>
    </AppShell>
  )
}

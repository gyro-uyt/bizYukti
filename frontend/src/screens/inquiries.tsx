'use client'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Empty, LinkButton, PageHeader, Skeleton, Tabs } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useAuth, useRequireAuth } from '@/lib/auth'
import { ago } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import type { Inquiry } from '@/lib/types'

const KIND: Record<string, string> = { space: 'About a space', business: 'Space offer', market_brief: 'Market brief' }

export default function Inquiries() {
  const user = useRequireAuth()
  const [box, setBox] = useState<'all' | 'received' | 'sent' | 'team'>('all')
  const { data, loading } = useApi<{ items: Inquiry[] }>(user ? '/inquiries' : null, { box })
  const tabs: { key: typeof box; label: string }[] = [{ key: 'all', label: 'All' }, { key: 'received', label: 'Received' }, { key: 'sent', label: 'Sent' }]
  if (user?.roles.includes('admin')) tabs.push({ key: 'team', label: 'Team inbox' })
  return (
    <AppShell>
      <div className="container stack" style={{ maxWidth: 860 }}>
        <PageHeader title="Messages" sub="Conversations about spaces, requests and market briefs. Contact details stay private unless you share them." />
        <Tabs label="Mailbox" value={box} onChange={setBox} tabs={tabs} />
        {loading || !data ? <Skeleton rows={4} /> : data.items.length ? (
          <ul className="rows">{data.items.map((i) => (
            <li key={i.id}><Link href={`/inquiries/${i.id}`} className="row-link">
              {i.context.property?.cover_url ? <img src={i.context.property.cover_url} alt="" className="thumb-sm" /> : <span className="thumb-sm" aria-hidden />}
              <span>
                <span className="row-title">{i.subject}</span>
                <span className="row-meta"><span>{i.direction === 'sent' ? `To ${i.with.name}` : `From ${i.with.name}`}</span><Badge tone="neutral">{KIND[i.kind] || i.kind}</Badge>{i.status === 'closed' ? <span>Closed</span> : null}</span>
                {i.last_message ? <span className="row-reason" style={{ color: 'var(--muted)' }}>{i.last_message}</span> : null}
              </span>
              <span className="row-count">{i.unread ? <span className="unread" aria-label={`${i.unread} unread`} /> : null}<span>{ago(i.last_message_at)}</span></span>
            </Link></li>))}</ul>
        ) : <Empty title="No conversations yet" body="When you contact an owner or a business, the conversation appears here." action={<LinkButton href="/explore" variant="secondary">Explore</LinkButton>} />}
      </div>
    </AppShell>
  )
}

export function InquiryThread() {
  const user = useRequireAuth()
  const { reload: reloadMe } = useAuth()
  const { id } = useParams<{ id: string }>()
  const toast = useToast()
  const { data, loading, error, setData, reload } = useApi<Inquiry>(user ? `/inquiries/${id}` : null)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [data?.messages?.length])
  useEffect(() => { if (data) reloadMe() }, [data?.id, reloadMe]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setInterval(() => reload(), 20000); return () => clearInterval(t) }, [reload])
  const send = async () => {
    if (body.trim().length < 1) return
    setBusy(true)
    try { setData(await http.post<Inquiry>(`/inquiries/${id}/messages`, { body: body.trim() })); setBody('') } catch (e) { toast(errorMessage(e)) } finally { setBusy(false) }
  }
  const close = async () => { try { setData(await http.post<Inquiry>(`/inquiries/${id}/close`)) } catch (e) { toast(errorMessage(e)) } }
  if (error) return <AppShell><div className="container"><Empty title="Conversation not found" body={error.message} /></div></AppShell>
  return (
    <AppShell>
      <div className="container stack" style={{ maxWidth: 860 }}>
        {loading || !data ? <Skeleton rows={4} /> : (
          <>
            <PageHeader back="/inquiries" title={data.subject} sub={`With ${data.with.name}`}
              action={data.status !== 'closed' ? <Button variant="secondary" size="sm" onClick={close}>Close conversation</Button> : <Badge tone="neutral">Closed</Badge>} />
            <div className="row">
              {data.context.property ? <LinkButton href={`/properties/${data.context.property.id}`} variant="secondary" size="sm">View space</LinkButton> : null}
              {data.context.demand ? <LinkButton href={`/demands/${data.context.demand.id}`} variant="secondary" size="sm">{data.context.demand.title}</LinkButton> : null}
              {data.context.area ? <LinkButton href={`/opportunities/${data.context.area.id}${data.category ? `?category=${data.category}` : ''}`} variant="secondary" size="sm">{data.context.area.name}</LinkButton> : null}
            </div>
            <div className="thread" aria-live="polite">
              {(data.messages || []).map((m) => (
                <div key={m.id} className={`bubble${m.mine ? ' mine' : ''}`}>{m.body}<p className="meta">{m.mine ? 'You' : m.sender}, {ago(m.created_at)}</p></div>
              ))}
              <div ref={end} />
            </div>
            {data.status !== 'closed' ? (
              <div className="composer">
                <label className="sr-only" htmlFor="reply">Reply</label>
                <textarea id="reply" className="input" value={body} maxLength={2000} placeholder="Write a reply" onChange={(e) => setBody(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }} />
                <Button onClick={send} loading={busy} disabled={!body.trim()} aria-label="Send reply"><Send size={18} aria-hidden /> Send</Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </AppShell>
  )
}

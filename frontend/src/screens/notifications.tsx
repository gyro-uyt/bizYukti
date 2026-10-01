'use client'
import Link from 'next/link'
import { useEffect } from 'react'
import { Bell } from 'lucide-react'
import { AppShell } from '@/components/shell'
import { Empty, PageHeader, Skeleton } from '@/components/ui'
import { http } from '@/lib/api'
import { useAuth, useRequireAuth } from '@/lib/auth'
import { ago } from '@/lib/format'
import { useApi } from '@/lib/hooks'

type Note = { id: string; kind: string; title: string; body: string | null; link: string | null; read: boolean; created_at: string }

export default function Notifications() {
  const user = useRequireAuth()
  const { reload: reloadMe } = useAuth()
  const { data, loading } = useApi<{ unread: number; items: Note[] }>(user ? '/notifications' : null)
  useEffect(() => {
    if (data?.unread) http.post('/notifications/read', {}).then(() => reloadMe()).catch(() => {})
  }, [data, reloadMe])
  return (
    <AppShell>
      <div className="container stack" style={{ maxWidth: 860 }}>
        <PageHeader title="Notifications" />
        {loading || !data ? <Skeleton rows={4} /> : data.items.length ? (
          <ul className="rows">{data.items.map((n) => {
            const inner = (<>
              <span className={`row-icon ${n.read ? 'ci-blue' : 'ci-pink'}`}><Bell size={18} aria-hidden /></span>
              <span><span className="row-title" style={{ fontSize: 16 }}>{n.title}</span>{n.body ? <span className="row-reason" style={{ color: 'var(--muted)' }}>{n.body}</span> : null}</span>
              <span className="meta">{ago(n.created_at)}{!n.read ? <span className="sr-only"> unread</span> : null}</span>
            </>)
            return <li key={n.id}>{n.link ? <Link href={n.link} className="row-link">{inner}</Link> : <div className="row-link">{inner}</div>}</li>
          })}</ul>
        ) : <Empty title="You're all caught up" body="Updates about your requests, spaces and messages appear here." />}
      </div>
    </AppShell>
  )
}

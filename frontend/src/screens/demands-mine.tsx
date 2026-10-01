'use client'
import Link from 'next/link'
import { useState } from 'react'
import { DemandRow, StatusBadge } from '@/components/cards'
import { AppShell } from '@/components/shell'
import { Empty, LinkButton, PageHeader, Skeleton, Tabs } from '@/components/ui'
import { useRequireAuth } from '@/lib/auth'
import { num, plural } from '@/lib/format'
import { useApi } from '@/lib/hooks'
import type { Demand } from '@/lib/types'

export default function MyDemands() {
  const user = useRequireAuth()
  const [tab, setTab] = useState<'created' | 'supported'>('created')
  const { data, loading } = useApi<{ created: (Demand & { matched_spaces: number })[]; supported: Demand[] }>(user ? '/demands/mine' : null)
  return (
    <AppShell>
      <div className="container stack">
        <PageHeader title="My activity" sub="Requests you created and the ones you support." action={<LinkButton href="/demands/new" variant="pink">Request a business</LinkButton>} />
        <Tabs label="My requests" value={tab} onChange={setTab} tabs={[{ key: 'created', label: 'Created', count: data?.created.length }, { key: 'supported', label: 'Supported', count: data?.supported.length }]} />
        {loading || !data ? <Skeleton rows={3} /> : tab === 'created' ? (data.created.length ? (
          <ul className="rows">{data.created.map((d) => (
            <li key={d.id}><Link href={`/demands/${d.id}`} className="row-link">
              <span aria-hidden />
              <span><span className="row-title">{d.display_title}</span>
                <span className="row-meta"><StatusBadge status={d.status} /><span>{d.verified ? 'Verified local demand' : 'Pending verification'}</span><span>{plural(d.matched_spaces, 'matched space')}</span></span></span>
              <span className="row-count"><strong>{num(d.supporters)}</strong><span>supporters</span></span>
            </Link></li>))}</ul>
        ) : <Empty title="You haven't asked for anything yet" body="Tell us what your area is missing. It takes under a minute." action={<LinkButton href="/demands/new">Request a business</LinkButton>} />)
          : (data.supported.length ? <ul className="rows">{data.supported.map((d) => <DemandRow key={d.id} d={d} />)}</ul>
            : <Empty title="No supported requests yet" body="Back your neighbours' requests to make them count." action={<LinkButton href="/explore" variant="secondary">Explore requests</LinkButton>} />)}
      </div>
    </AppShell>
  )
}

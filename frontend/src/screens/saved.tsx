'use client'
import Link from 'next/link'
import { useState } from 'react'
import { ChevronRight, MapPin } from 'lucide-react'
import { DemandRow, SpaceCard } from '@/components/cards'
import { AppShell } from '@/components/shell'
import { Empty, LinkButton, PageHeader, Skeleton, Tabs } from '@/components/ui'
import { canUse } from '@/lib/access'
import { useRequireAuth } from '@/lib/auth'
import { useApi } from '@/lib/hooks'
import type { AreaRef, Demand, Space } from '@/lib/types'

type Saved = { areas: { id: string; area: AreaRef; category: string; category_name: string | null }[]; properties: { id: string; property: Space }[]; demands: { id: string; demand: Demand }[] }
type Tab = 'areas' | 'spaces' | 'requests'

export default function SavedScreen() {
  const user = useRequireAuth()
  const { data, loading } = useApi<Saved>(user ? '/saved' : null)
  const [picked, setTab] = useState<Tab>(user?.active_role === 'business' ? 'areas' : 'spaces')
  const visible = (['areas', 'spaces', 'requests'] as Tab[]).filter((t) => canUse(user, `saved.${t}`))
  const tab = visible.includes(picked) ? picked : visible[0]
  return (
    <AppShell>
      <div className="container stack">
        <PageHeader title="Saved" />
        <Tabs label="Saved items" value={tab} onChange={setTab} tabs={([{ key: 'areas', label: 'Areas', count: data?.areas.length }, { key: 'spaces', label: 'Spaces', count: data?.properties.length }, { key: 'requests', label: 'Requests', count: data?.demands.length }] as { key: Tab; label: string; count?: number }[]).filter((t) => visible.includes(t.key))} />
        {loading || !data ? <Skeleton rows={3} /> : null}
        {data && tab === 'areas' ? (data.areas.length ? (
          <ul className="rows">{data.areas.map((s) => (
            <li key={s.id}><Link href={`/opportunities/${s.area.id}${s.category ? `?category=${s.category}` : ''}`} className="row-link">
              <span className="row-icon ci-blue"><MapPin size={18} aria-hidden /></span>
              <span><span className="row-title">{s.category_name ? `${s.category_name} in ${s.area.name}` : s.area.name}</span><span className="row-meta"><span>{s.area.city}</span></span></span>
              <ChevronRight size={20} aria-hidden />
            </Link></li>))}</ul>
        ) : <Empty title="No saved areas" body="Save areas from an opportunity page to compare them later." action={<LinkButton href="/map" variant="secondary">Open the map</LinkButton>} />) : null}
        {data && tab === 'spaces' ? (data.properties.length ? <div className="grid-cards">{data.properties.map((s) => <SpaceCard key={s.id} s={s.property} />)}</div>
          : <Empty title="No saved spaces" body="Tap Save on any space to keep it here." action={<LinkButton href="/explore?tab=spaces" variant="secondary">Browse spaces</LinkButton>} />) : null}
        {data && tab === 'requests' ? (data.demands.length ? <ul className="rows">{data.demands.map((s) => <DemandRow key={s.id} d={s.demand} />)}</ul>
          : <Empty title="No saved requests" body="Requests you save appear here." />) : null}
      </div>
    </AppShell>
  )
}

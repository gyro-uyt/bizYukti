'use client'
import Link from 'next/link'
import { Briefcase, Building2, ChevronRight, Users } from 'lucide-react'
import { AppShell } from '@/components/shell'
import { PageHeader } from '@/components/ui'
import { canUse, type Feature } from '@/lib/access'
import { useAuth } from '@/lib/auth'

export default function Post() {
  const { user } = useAuth()
  const go = (href: string) => (user ? href : `/login?next=${encodeURIComponent(href)}`)
  const items: { href: string; title: string; body: string; icon: typeof Users; tone: string; role: string; feature: Feature }[] = [
    { href: go('/demands/new'), title: 'Request a business', body: 'Ask for a pharmacy, café, gym or anything your area is missing.', icon: Users, tone: 'ci-pink', role: 'resident', feature: 'demand.create' },
    { href: go('/properties/new'), title: 'List a space', body: 'Shop, office, plot or warehouse. See the local demand it fits.', icon: Building2, tone: 'ci-orange', role: 'owner', feature: 'property.create' },
    { href: '/map', title: 'Find a location', body: 'See demand zones and available spaces for the business you plan to open.', icon: Briefcase, tone: 'ci-blue', role: 'business', feature: 'map' },
  ]
  const role = user?.active_role
  const ordered = items.filter((i) => canUse(user, i.feature)).sort((a, b) => Number(b.role === role) - Number(a.role === role))
  return (
    <AppShell>
      <div className="container" style={{ maxWidth: 760 }}>
        <PageHeader title="What would you like to do?" />
        <div className="choices">
          {ordered.map((i) => (
            <Link key={i.title} href={i.href} className="choice">
              <span className={`choice-icon ${i.tone}`}><i.icon size={24} aria-hidden /></span>
              <span><span className="row-title">{i.title}</span><span className="meta block">{i.body}</span></span>
              <ChevronRight size={22} aria-hidden />
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  )
}

'use client'
import Link from 'next/link'
import { Building2, Briefcase, Users } from 'lucide-react'
import { DemandRow } from '@/components/cards'
import { HeroMotif, Logo } from '@/components/brand'
import { LinkButton, Skeleton } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { useApi } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { Demand, Paged } from '@/lib/types'

export default function Landing() {
  const { user } = useAuth()
  const { config } = useLocation()
  const { data, loading } = useApi<Paged<Demand>>('/demands', { sort: 'support', limit: 6, radius_km: 25 })
  const request = user ? '/demands/new' : '/login?next=/demands/new'
  const city = config?.default_city || 'your city'
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="landing-nav">
        <div className="container">
          <Link href="/" aria-label="BizYukti home"><Logo inverted /></Link>
          <nav aria-label="Main">
            <Link href="/explore" className="hide-sm">Explore</Link>
            <Link href="/map" className="hide-sm">Map</Link>
            {user ? <Link href="/home" className="btn btn-inverse btn-sm">Open app</Link> : <>
              <Link href="/login">Sign in</Link>
              <Link href="/login?next=/onboarding" className="btn btn-inverse btn-sm">Get started</Link>
            </>}
          </nav>
        </div>
      </header>
      <main id="main">
        <section className="hero">
          <div className="container hero-grid">
            <div>
              <h1>Demand.<br /><span className="hero-accent">Space.</span><br />Opportunity.</h1>
              <p className="hero-lead">Residents ask for the businesses their street is missing. Owners list spaces that sit empty. Businesses see exactly where to open, and why.</p>
              <div className="hero-actions">
                <LinkButton href={request} variant="inverse" size="lg">Request a business</LinkButton>
                <Link href="/explore" className="hero-link">See what&apos;s needed nearby</Link>
              </div>
            </div>
            <HeroMotif />
          </div>
        </section>

        <section className="section">
          <div className="container stack">
            <div className="section-head">
              <div className="stack-sm"><h2 className="h1">The local pulse</h2><p className="lead">What neighbours in {city} are asking for right now, ranked by verified supporters.</p></div>
              <Link href="/explore" className="link-quiet">See all requests</Link>
            </div>
            {loading ? <Skeleton rows={4} /> : <ol className="rows">{(data?.items || []).map((d, i) => <DemandRow key={d.id} d={d} rank={i + 1} />)}</ol>}
          </div>
        </section>

        <section className="section section-white">
          <div className="container stack-lg">
            <h2 className="h1">Three sides, one loop</h2>
            <div className="triad">
              <div className="t-res">
                <span className="choice-icon ci-pink"><Users size={24} aria-hidden /></span>
                <h3 className="h2">Residents</h3>
                <p>Ask for what&apos;s missing in a few taps. Back your neighbours&apos; requests and earn rewards once they&apos;re verified.</p>
                <Link href={request} className="link-quiet">Request a business</Link>
              </div>
              <div className="t-own">
                <span className="choice-icon ci-orange"><Building2 size={24} aria-hidden /></span>
                <h3 className="h2">Property owners</h3>
                <p>List an empty shop, office, plot or warehouse and see which local demand it fits before you set the rent.</p>
                <Link href={user ? '/properties/new' : '/login?next=/properties/new'} className="link-quiet">List a space</Link>
              </div>
              <div className="t-biz">
                <span className="choice-icon ci-blue"><Briefcase size={24} aria-hidden /></span>
                <h3 className="h2">Businesses</h3>
                <p>Find areas where residents already want what you sell, with available spaces and competition side by side.</p>
                <Link href="/map" className="link-quiet">Find opportunities</Link>
              </div>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="container why-grid">
            <div className="stack">
              <h2 className="h1">Every match explains itself</h2>
              <p className="lead">No black-box scores. Each match and opportunity comes with the plain reasons behind it, so everyone can decide quickly.</p>
              <ul className="trust-list">
                <li><span className="trust-icon ci-green"><img src="/landing/verified-demand.webp" alt="" aria-hidden /></span><div><strong>Verified local demand</strong><p className="meta">Support counts only from verified residents within 5 km, one per device.</p></div></li>
                <li><span className="trust-icon ci-orange"><img src="/landing/fresh-spaces.webp" alt="" aria-hidden /></span><div><strong>Real, fresh spaces</strong><p className="meta">Photo checks catch blurry and repeated images; owners confirm availability every month.</p></div></li>
                <li><span className="trust-icon ci-blue"><img src="/landing/rewards.webp" alt="" aria-hidden /></span><div><strong>Rewards that can&apos;t be farmed</strong><p className="meta">Points unlock only after the action is verified.</p></div></li>
              </ul>
            </div>
            <div className="reason-card" aria-label="Example match">
              <span className="badge badge-strong">High local fit: 92% match</span>
              <p className="h2">Shop, 850 sq ft near Gol Pahadiya</p>
              <p>Matched because 184 nearby residents requested a pharmacy and this shop is within 1.3 km of the demand cluster.</p>
              <p className="meta">Example from the demo data</p>
            </div>
          </div>
        </section>

        <section className="cta-band">
          <div className="container row-between">
            <h2>Your street is missing something.<br />Say it.</h2>
            <LinkButton href={request} variant="inverse" size="lg">Request a business</LinkButton>
          </div>
        </section>
      </main>
      <footer className="footer">
        <div className="container footer-grid">
          <div className="stack-sm"><Logo inverted /><p>Demand. Space. Opportunity.</p></div>
          <nav aria-label="Footer">
            <Link href="/explore">Explore</Link><Link href="/map">Map</Link>
            <Link href={user ? '/properties/new' : '/login?next=/properties/new'}>List a space</Link>
            <Link href="/legal/privacy">Privacy</Link><Link href="/legal/terms">Terms</Link>
          </nav>
          <p className="meta" style={{ color: '#9BA5A9', width: '100%' }}>Demo data shown in this build is illustrative and synthetic. © {new Date().getFullYear()} BizYukti</p>
        </div>
      </footer>
    </>
  )
}

'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Briefcase, Building2, Check, LocateFixed, Users } from 'lucide-react'
import { Logo } from '@/components/brand'
import { locateMe } from '@/components/location-picker'
import { MapView } from '@/components/map'
import { Button, Chip, Field, Notice, Steps } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { safeNext } from '@/lib/format'
import { useDebounced } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { Me } from '@/lib/types'

type RoleKey = 'resident' | 'owner' | 'business'
const ROLES: { key: RoleKey; title: string; body: string; icon: typeof Users; tone: string }[] = [
  { key: 'resident', title: 'I live here', body: 'Ask for businesses your area needs and back your neighbours.', icon: Users, tone: 'ci-pink' },
  { key: 'owner', title: 'I have a space', body: 'List a shop, office, plot or warehouse and see local demand for it.', icon: Building2, tone: 'ci-orange' },
  { key: 'business', title: "I'm opening a business", body: 'Find areas where residents already want what you offer.', icon: Briefcase, tone: 'ci-blue' },
]

export default function Onboarding() {
  const { user, ready, setUser } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const { loc, categories, config } = useLocation()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [role, setRole] = useState<RoleKey>('resident')
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null)
  const [label, setLabel] = useState('')
  const [biz, setBiz] = useState({ name: '', categories: [] as string[], budget_max: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!ready) return
    if (!user) router.replace('/login?next=/onboarding')
    else if (user.onboarded) router.replace(safeNext(params.get('next')))
  }, [ready, user, router, params])
  useEffect(() => { if (user?.name) setName((n) => n || user.name || '') }, [user?.name])
  useEffect(() => { setPin((p) => p || { lat: loc.lat, lng: loc.lng }) }, [loc.lat, loc.lng])
  const dpin = useDebounced(pin, 400)
  useEffect(() => {
    if (!dpin) return
    http.get<{ locality: string }>('/geo/reverse', dpin).then((r) => setLabel(r.locality)).catch(() => {})
  }, [dpin])

  const total = role === 'business' ? 4 : 3
  const labels = ['Your name', 'How you will use BizYukti', 'Your locality', 'Your business']
  const canNext = step === 0 ? name.trim().length > 0 : step === 2 ? !!pin : step === 3 ? biz.name.trim().length >= 2 && biz.categories.length > 0 : true

  const finish = async () => {
    if (!pin) return
    setBusy(true)
    setError(null)
    try {
      const body: Record<string, unknown> = { name: name.trim(), role, home: { lat: pin.lat, lng: pin.lng, label: label || undefined } }
      if (role === 'business') {
        body.business = { name: biz.name.trim(), categories: biz.categories, preferred_cities: [config?.default_city || 'Gwalior'],
          budget_max: biz.budget_max ? Number(biz.budget_max) : null }
      }
      const me = await http.post<Me>('/me/onboarding', body)
      setUser(me)
      router.replace(safeNext(params.get('next'), '/home'))
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }
  const locate = async () => {
    try { setPin(await locateMe()) } catch (e) { setError((e as Error).message) }
  }
  const toggleCat = (slug: string) => setBiz((b) => ({ ...b, categories: b.categories.includes(slug) ? b.categories.filter((c) => c !== slug) : [...b.categories, slug].slice(0, 6) }))

  if (!user) return null
  return (
    <div className="flow">
      <header className="flow-head"><div className="container row-between"><Logo /></div></header>
      <main className="flow-body" id="main">
        <Steps step={step} total={total} label={labels[step]} />
        {step === 0 ? (
          <section className="stack">
            <h1 className="h1">What should we call you?</h1>
            <p className="lead">Neighbours see your first name and initial on requests you post. Your phone number and email stay private.</p>
            <Field label="Your name" htmlFor="name">
              <input id="name" className="input" autoFocus value={name} maxLength={80} autoComplete="name" onChange={(e) => setName(e.target.value)} />
            </Field>
          </section>
        ) : null}
        {step === 1 ? (
          <section className="stack">
            <h1 className="h1">How will you use BizYukti?</h1>
            <p className="lead">Pick the one that fits best. You can switch any time from your profile.</p>
            <div className="choices">
              {ROLES.map((r) => (
                <button key={r.key} type="button" className="choice" aria-pressed={role === r.key} onClick={() => setRole(r.key)}>
                  <span className={`choice-icon ${r.tone}`}><r.icon size={24} aria-hidden /></span>
                  <span><span className="row-title">{r.title}</span><span className="meta block">{r.body}</span></span>
                  {role === r.key ? <Check size={22} aria-hidden /> : <span />}
                </button>
              ))}
            </div>
          </section>
        ) : null}
        {step === 2 ? (
          <section className="stack">
            <h1 className="h1">{role === 'business' ? 'Where are you based?' : 'Where do you live?'}</h1>
            <p className="lead">{role === 'resident'
              ? 'Support is counted only from residents within 5 km of a request. That keeps local demand honest.'
              : 'We show nearby demand first. Your exact location is never shown to anyone.'}</p>
            <MapView center={pin || loc} pin={pin} onPinChange={setPin} height={340} ariaLabel="Map. Tap or drag the pin to set your locality" />
            <div className="row-between">
              <p><strong>{label || 'Finding your locality…'}</strong></p>
              <Button variant="secondary" size="sm" onClick={locate}><LocateFixed size={16} aria-hidden /> Use my location</Button>
            </div>
          </section>
        ) : null}
        {step === 3 ? (
          <section className="stack">
            <h1 className="h1">Tell us about your business</h1>
            <p className="lead">We use this to rank areas for you. Only your business name is visible to others.</p>
            <Field label="Business name" htmlFor="biz-name">
              <input id="biz-name" className="input" value={biz.name} maxLength={120} onChange={(e) => setBiz({ ...biz, name: e.target.value })} />
            </Field>
            <Field label="What do you plan to open?" hint="Pick up to 6.">
              <div className="chips">{categories.filter((c) => c.slug !== 'other').map((c) => <Chip key={c.slug} selected={biz.categories.includes(c.slug)} onClick={() => toggleCat(c.slug)}>{c.name}</Chip>)}</div>
            </Field>
            <Field label="Maximum monthly rent (optional)" htmlFor="budget">
              <div className="input-prefix"><span>₹</span><input id="budget" className="input" inputMode="numeric" value={biz.budget_max}
                onChange={(e) => setBiz({ ...biz, budget_max: e.target.value.replace(/\D/g, '') })} placeholder="40000" /></div>
            </Field>
          </section>
        ) : null}
        {error ? <Notice tone="error">{error}</Notice> : null}
      </main>
      <div className="flow-actions">
        <div>
          {step > 0 ? <Button variant="secondary" onClick={() => setStep(step - 1)}>Back</Button> : <span />}
          <Button onClick={() => (step < total - 1 ? setStep(step + 1) : finish())} disabled={!canNext} loading={busy}>
            {step === total - 1 ? 'Finish' : 'Continue'}
          </Button>
        </div>
      </div>
    </div>
  )
}

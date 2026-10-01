'use client'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Gift, LocateFixed, X } from 'lucide-react'
import { Logo } from '@/components/brand'
import { DemandRow } from '@/components/cards'
import { locateMe } from '@/components/location-picker'
import { MapView } from '@/components/map'
import { useToast } from '@/components/toast'
import { Button, Chip, Field, Modal, Notice, Steps } from '@/components/ui'
import { ApiError, errorMessage, http } from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import { useDebounced } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { Demand } from '@/lib/types'

const SUGGESTIONS = ['Pharmacy', 'Grocery store', 'Café', 'Gym', "Children's clinic", 'Coaching centre', 'Daycare', 'Bakery', 'ATM']
const LABELS = ['What', 'Where', 'Why', 'Publish']
type Assist = { title: string; category: string; category_name: string; confidence: number; why: string; similar: (Demand & { similarity: number })[] }

export default function DemandNew() {
  const user = useRequireAuth()
  const router = useRouter()
  const toast = useToast()
  const { loc, config, categories } = useLocation()
  const [step, setStep] = useState(0)
  const [text, setText] = useState('')
  const [category, setCategory] = useState<string | null>(null)
  const [assist, setAssist] = useState<Assist | null>(null)
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null)
  const [locality, setLocality] = useState('')
  const [reason, setReason] = useState('daily_need')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dupes, setDupes] = useState<Demand[] | null>(null)
  const [changingCat, setChangingCat] = useState(false)

  useEffect(() => {
    if (!pin && user) setPin(user.home ? { lat: user.home.lat, lng: user.home.lng } : { lat: loc.lat, lng: loc.lng })
  }, [user, loc, pin])
  const dtext = useDebounced(text.trim(), 450)
  useEffect(() => {
    if (dtext.length < 3) { setAssist(null); return }
    http.post<Assist>('/demands/assist', { text: dtext, lat: pin?.lat, lng: pin?.lng }).then(setAssist).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dtext])
  const dpin = useDebounced(pin, 400)
  useEffect(() => {
    if (dpin) http.get<{ locality: string }>('/geo/reverse', dpin).then((r) => setLocality(r.locality)).catch(() => {})
  }, [dpin])

  const catSlug = category || assist?.category || null
  const catName = categories.find((c) => c.slug === catSlug)?.name || assist?.category_name
  const title = assist?.title || text.trim()
  const maxPoints = config?.rewards.demand_max_points ?? 150

  const supportInstead = async (d: Demand) => {
    try {
      const r = await http.post<{ support: { status: string; reason: string | null } }>(`/demands/${d.id}/support`, { lat: pin?.lat, lng: pin?.lng })
      toast(r.support.status === 'verified' ? 'Thanks! Your support is counted.' : r.support.reason || 'Support recorded.')
      router.push(`/demands/${d.id}`)
    } catch (e) { setError(errorMessage(e)) }
  }

  const publish = async (skip = false) => {
    if (!pin) return
    setBusy(true)
    setError(null)
    try {
      const r = await http.post<{ demand: Demand }>('/demands', {
        text: text.trim(), category: catSlug || undefined, reason, reason_note: note.trim() || undefined,
        lat: pin.lat, lng: pin.lng, publish: true, skip_duplicate_check: skip, client_lat: pin.lat, client_lng: pin.lng,
      })
      router.push(`/demands/${r.demand.id}?new=1`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.data?.code === 'duplicate') setDupes(e.data.similar as Demand[])
      else setError(errorMessage(e))
      setBusy(false)
    }
  }
  const locate = async () => { try { setPin(await locateMe()) } catch (e) { setError((e as Error).message) } }
  const canNext = step === 0 ? text.trim().length >= 2 : step === 1 ? !!pin : true

  if (!user) return null
  return (
    <div className="flow">
      <header className="flow-head"><div className="container row-between"><Logo /><Link href="/home" className="icon-btn" aria-label="Cancel and go home"><X size={22} /></Link></div></header>
      <main className="flow-body" id="main">
        <Steps step={step} total={4} label={LABELS[step]} />
        {step === 0 ? (
          <section className="stack">
            <h1 className="h1">What would you like nearby?</h1>
            <Field label="Describe the business in your own words" htmlFor="what" hint="For example: a pharmacy open late, a gym for women, a bookstore near the park.">
              <input id="what" className="input" autoFocus value={text} maxLength={200} onChange={(e) => setText(e.target.value)} placeholder="A pharmacy" />
            </Field>
            <div className="chips" aria-label="Suggestions">{SUGGESTIONS.map((s) => <Chip key={s} selected={text === s} onClick={() => setText(s)}>{s}</Chip>)}</div>
            {assist && catName ? (
              <p className="meta">We&apos;ll list this under <strong>{catName}</strong>. <button type="button" className="link" onClick={() => setChangingCat(!changingCat)}>Change</button></p>
            ) : null}
            {changingCat ? (
              <select className="input" aria-label="Category" value={catSlug || ''} onChange={(e) => { setCategory(e.target.value); setChangingCat(false) }}>
                {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </select>
            ) : null}
            {assist?.similar.length ? (
              <div className="stack-sm">
                <h2 className="h3">Already requested nearby</h2>
                <p className="meta">Supporting an existing request makes it stronger than starting a new one.</p>
                <ul className="rows">{assist.similar.map((d) => <DemandRow key={d.id} d={d} />)}</ul>
              </div>
            ) : null}
          </section>
        ) : null}
        {step === 1 ? (
          <section className="stack">
            <h1 className="h1">Where should it open?</h1>
            <p className="lead">Drop the pin where you&apos;d like it. Neighbours within 5 km can support it.</p>
            <MapView center={pin || loc} pin={pin} onPinChange={setPin} height={360} ariaLabel="Map. Tap or drag the pin to choose where it should open" />
            <div className="row-between">
              <p>Near <strong>{locality || '…'}</strong></p>
              <Button variant="secondary" size="sm" onClick={locate}><LocateFixed size={16} aria-hidden /> Use my location</Button>
            </div>
          </section>
        ) : null}
        {step === 2 ? (
          <section className="stack">
            <h1 className="h1">Why does your area need it?</h1>
            <div className="chips" role="radiogroup" aria-label="Reason">
              {(config?.reasons || []).map((r) => <Chip key={r.slug} selected={reason === r.slug} onClick={() => setReason(r.slug)}>{r.label}</Chip>)}
            </div>
            <Field label="Anything else? (optional)" htmlFor="note" hint="Keep it about the need. Contact details and links are removed from public view.">
              <textarea id="note" className="input" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder="The nearest one closes at 8 pm." />
            </Field>
          </section>
        ) : null}
        {step === 3 ? (
          <section className="stack">
            <h1 className="h1">Ready to publish?</h1>
            <div className="panel stack-sm">
              <p className="h2">{title} near {locality}</p>
              <p className="meta">{catName || 'Other business'}, {config?.reasons.find((r) => r.slug === reason)?.label}</p>
              {note.trim() ? <p>{note.trim()}</p> : null}
            </div>
            <div className="reward-strip"><Gift size={22} aria-hidden /><span>Earn up to {maxPoints} points after verification</span></div>
            <p className="meta">Your request counts as verified local demand once {config?.trust.verify_min_supporters ?? 3} neighbours support it. Points unlock as it grows and when the business opens.</p>
          </section>
        ) : null}
        {error ? <Notice tone="error">{error}</Notice> : null}
      </main>
      <div className="flow-actions">
        <div>
          {step > 0 ? <Button variant="secondary" onClick={() => setStep(step - 1)}>Back</Button> : <span />}
          {step < 3 ? <Button onClick={() => setStep(step + 1)} disabled={!canNext}>Continue</Button>
            : <Button variant="pink" onClick={() => publish(false)} loading={busy}>Publish request</Button>}
        </div>
      </div>
      <Modal open={!!dupes} onClose={() => setDupes(null)} title="This may already exist"
        footer={<><Button variant="secondary" onClick={() => { setDupes(null); publish(true) }}>Publish mine anyway</Button></>}>
        <p>Neighbours already asked for something similar close by. Adding your support makes their request stronger.</p>
        <ul className="rows">
          {(dupes || []).map((d) => (
            <li key={d.id} className="row-between" style={{ padding: 14 }}>
              <span><span className="row-title">{d.display_title}</span><span className="meta block">{d.supporters} supporters</span></span>
              <Button size="sm" variant="pink" onClick={() => supportInstead(d)}>Support this instead</Button>
            </li>
          ))}
        </ul>
      </Modal>
    </div>
  )
}

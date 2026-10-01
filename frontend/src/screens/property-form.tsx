'use client'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { Camera, LocateFixed, ShieldCheck, Trash2, TrendingUp, X } from 'lucide-react'
import { Logo } from '@/components/brand'
import { locateMe } from '@/components/location-picker'
import { MapView } from '@/components/map'
import { useToast } from '@/components/toast'
import { Badge, Button, Chip, Field, Modal, Notice, Progress, Segmented, Steps } from '@/components/ui'
import { ApiError, errorMessage, http } from '@/lib/api'
import { useRequireAuth } from '@/lib/auth'
import { num, sqft } from '@/lib/format'
import { useDebounced } from '@/lib/hooks'
import { useLocation } from '@/lib/location'
import type { Space } from '@/lib/types'

const LABELS = ['Photos', 'Location', 'Type and size', 'Price and availability', 'Details']
const TYPES = [
  { key: 'shop', label: 'Shop', hint: 'Retail or showroom' }, { key: 'office', label: 'Office', hint: 'Cabins, halls, floors' },
  { key: 'land', label: 'Land or plot', hint: 'Open plot' }, { key: 'warehouse', label: 'Warehouse', hint: 'Godown or hall' },
  { key: 'other', label: 'Other', hint: 'Anything else' },
]
const UNITS = [{ key: 'sqft', label: 'sq ft' }, { key: 'sqm', label: 'sq m' }, { key: 'sqyd', label: 'sq yd (gaj)' }] as const
const FACTOR: Record<string, number> = { sqft: 1, sqm: 10.7639, sqyd: 9 }
type Ctx = { density: string; supporters: number; top: { category: string; category_name: string; supporters: number; suits: string[] }[]; locality: string }
type Form = { type: string; size_value: string; size_unit: string; price_type: string; price_amount: string; price_negotiable: boolean
  availability: string; available_from: string; address: string; description: string; amenities: string[] }

const toForm = (p: Space): Form => ({
  type: p.type || 'shop', size_value: p.size_value ? String(p.size_value) : '', size_unit: p.size_unit || 'sqft',
  price_type: p.price_type || 'rent', price_amount: p.price_amount ? String(p.price_amount) : '', price_negotiable: p.price_negotiable,
  availability: p.availability || 'now', available_from: p.available_from || '', address: p.address || '', description: p.description || '',
  amenities: p.amenities || [],
})
const EMPTY: Form = { type: 'shop', size_value: '', size_unit: 'sqft', price_type: 'rent', price_amount: '', price_negotiable: false,
  availability: 'now', available_from: '', address: '', description: '', amenities: [] }

export default function PropertyForm() {
  const user = useRequireAuth()
  const params = useParams<{ id?: string }>()
  const router = useRouter()
  const toast = useToast()
  const { loc, config } = useLocation()
  const [id, setId] = useState<string | null>(params.id || null)
  const [p, setP] = useState<Space | null>(null)
  const [form, setForm] = useState<Form>(EMPTY)
  const [pin, setPin] = useState<{ lat: number; lng: number } | null>(null)
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(0)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [locality, setLocality] = useState('')
  const [suggested, setSuggested] = useState<string | null>(null)
  const [typeTouched, setTypeTouched] = useState(false)
  const [ctx, setCtx] = useState<Ctx | null>(null)
  const [verifyOpen, setVerifyOpen] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!params.id || !user) return
    http.get<Space>(`/properties/${params.id}`).then((s) => {
      setP(s); setForm(toForm(s)); setTypeTouched(true)
      if (s.lat != null && s.lng != null) setPin({ lat: s.lat, lng: s.lng })
    }).catch((e) => setError(errorMessage(e)))
  }, [params.id, user])
  // New listings start at the property location chosen after sign-in (falls back to home via the location context).
  useEffect(() => { if (!pin && !params.id && user) setPin({ lat: loc.lat, lng: loc.lng }) }, [user, loc, pin, params.id])
  const dpin = useDebounced(pin, 400)
  useEffect(() => {
    if (!dpin) return
    http.get<Ctx>('/geo/demand-context', dpin).then((c) => { setCtx(c); setLocality(c.locality) }).catch(() => {})
  }, [dpin])
  const sizeSqft = form.size_value ? Number(form.size_value) * FACTOR[form.size_unit] : null
  const dsize = useDebounced(sizeSqft, 500)
  useEffect(() => {
    if (!dsize) return
    http.post<{ type: string }>('/properties/suggest-type', { size_value: dsize, size_unit: 'sqft', description: form.description }).then((r) => {
      setSuggested(r.type)
      if (!typeTouched) setForm((f) => ({ ...f, type: r.type }))
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dsize])

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }))
  const payload = () => ({
    type: form.type, size_value: form.size_value ? Number(form.size_value) : null, size_unit: form.size_unit,
    price_type: form.price_type, price_amount: form.price_amount ? Number(form.price_amount) : null, price_negotiable: form.price_negotiable,
    availability: form.availability, available_from: form.availability === 'future' && form.available_from ? form.available_from : null,
    lat: pin?.lat, lng: pin?.lng, address: form.address || null, description: form.description || null, amenities: form.amenities,
  })
  const ensureDraft = async (): Promise<string> => {
    if (id) return id
    const created = await http.post<Space>('/properties', payload())
    setId(created.id); setP(created)
    window.history.replaceState(null, '', `/properties/${created.id}/edit`)
    return created.id
  }
  const save = async (): Promise<Space | null> => {
    const pid = await ensureDraft()
    const updated = await http.patch<Space>(`/properties/${pid}`, payload())
    setP(updated)
    return updated
  }
  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setError(null)
    const list = Array.from(files).slice(0, Math.max(0, 8 - (p?.media.length || 0)))
    setUploading(list.length)
    const notes: string[] = []
    try {
      const pid = await ensureDraft()
      for (const file of list) {
        const fd = new FormData()
        fd.append('file', file)
        try {
          const r = await http.upload<{ warning: string | null }>(`/properties/${pid}/media`, fd)
          if (r.warning) notes.push(`${file.name}: ${r.warning}`)
        } catch (e) { notes.push(`${file.name}: ${errorMessage(e)}`) }
        setUploading((n) => n - 1)
      }
      setP(await http.get<Space>(`/properties/${pid}`))
    } catch (e) { setError(errorMessage(e)) } finally {
      setUploading(0); setWarnings(notes)
      if (fileRef.current) fileRef.current.value = ''
    }
  }
  const removePhoto = async (mid: string) => {
    if (!id) return
    try { setP(await http.del<Space>(`/properties/${id}/media/${mid}`)) } catch (e) { toast(errorMessage(e)) }
  }
  const next = async () => {
    setBusy(true); setError(null)
    try {
      if (step > 0 || id) await save()
      setStep((s) => Math.min(s + 1, LABELS.length - 1))
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const publish = async () => {
    setBusy(true); setError(null)
    try {
      await save()
      if (p?.status === 'published') { toast('Changes saved.'); router.push(`/properties/${id}`); return }
      await http.post(`/properties/${id}/publish`)
      router.push(`/properties/${id}/matches?new=1`)
    } catch (e) {
      if (e instanceof ApiError && e.data?.missing) setError(`Almost there. Add ${(e.data.missing as string[]).join(', ')} to publish.`)
      else setError(errorMessage(e))
      setBusy(false)
    }
  }
  const status = async (action: 'pause' | 'resume' | 'archive') => {
    try { setP(await http.post<Space>(`/properties/${id}/status`, { action })); toast(action === 'pause' ? 'Listing paused.' : action === 'resume' ? 'Listing is live again.' : 'Listing archived.') }
    catch (e) { toast(errorMessage(e)) }
  }

  if (!user) return null
  const good = (p?.media || []).filter((m) => !m.is_duplicate).length
  const live = p?.status === 'published'
  const canNext = step === 0 ? good >= 3 || !!p : step === 1 ? !!pin : step === 2 ? !!form.size_value : true
  return (
    <div className="flow">
      <header className="flow-head"><div className="container row-between"><Logo /><Link href="/home" className="icon-btn" aria-label="Close"><X size={22} /></Link></div></header>
      <main className="flow-body" id="main">
        <Steps step={step} total={LABELS.length} label={LABELS[step]} />
        {step === 0 ? (
          <section className="stack">
            <h1 className="h1">{params.id ? 'Edit your listing' : 'Add photos of the space'}</h1>
            <p className="lead">Add 3 to 8 clear photos: the front, the inside and the street. Spaces with sharp daylight photos get far more interest.</p>
            <div className="photo-grid">
              {(p?.media || []).map((m) => (
                <div key={m.id} className="photo">
                  <img src={m.thumb_url} alt="Listing photo" />
                  {m.is_duplicate ? <Badge tone="warn">Duplicate, not counted</Badge> : m.is_blurry ? <Badge tone="warn">Looks blurry</Badge> : null}
                  <button type="button" className="icon-btn" aria-label="Remove photo" onClick={() => removePhoto(m.id)}><Trash2 size={18} /></button>
                </div>
              ))}
              {(p?.media.length || 0) < 8 ? (
                <label className="dropzone">
                  <Camera size={26} aria-hidden />
                  <span>{uploading ? `Uploading ${uploading}…` : 'Add photos'}</span>
                  <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" multiple className="sr-only" onChange={(e) => upload(e.target.files)} disabled={!!uploading} />
                </label>
              ) : null}
            </div>
            <p className="meta">{good} of 3 required photos{good >= 3 ? ', you can add more.' : '.'} Photos are re-saved without location data.</p>
            {warnings.length ? <Notice tone="warn">{warnings.map((w) => <span key={w}>{w}</span>)}</Notice> : null}
          </section>
        ) : null}
        {step === 1 ? (
          <section className="stack">
            <h1 className="h1">Where is the space?</h1>
            <p className="lead">Drop the pin on the entrance. Businesses see the area, not your exact address.</p>
            <MapView center={pin || loc} pin={pin} onPinChange={setPin} height={340} ariaLabel="Map. Tap or drag the pin to the entrance of the space" />
            <div className="row-between"><p>Near <strong>{locality || '…'}</strong></p>
              <Button variant="secondary" size="sm" onClick={async () => { try { setPin(await locateMe()) } catch (e) { setError((e as Error).message) } }}><LocateFixed size={16} aria-hidden /> I&apos;m at the space</Button></div>
            <Field label="Address (private, optional)" htmlFor="addr" hint="Shared only when you choose to, inside a conversation.">
              <input id="addr" className="input" value={form.address} maxLength={240} onChange={(e) => set('address', e.target.value)} placeholder="Shop number, building, road" />
            </Field>
          </section>
        ) : null}
        {step === 2 ? (
          <section className="stack">
            <h1 className="h1">How big is it, and what type?</h1>
            <div className="row" style={{ alignItems: 'flex-end' }}>
              <Field label="Size" htmlFor="size"><input id="size" className="input" inputMode="decimal" style={{ maxWidth: 180 }} value={form.size_value}
                onChange={(e) => set('size_value', e.target.value.replace(/[^\d.]/g, ''))} placeholder="850" /></Field>
              <Segmented label="Unit" value={form.size_unit} onChange={(u) => set('size_unit', u)} options={UNITS.map((u) => ({ key: u.key, label: u.label }))} />
            </div>
            {sizeSqft && form.size_unit !== 'sqft' ? <p className="meta">That&apos;s about {sqft(sizeSqft)}.</p> : null}
            <div className="tiles">
              {TYPES.map((t) => (
                <button key={t.key} type="button" className="tile" aria-pressed={form.type === t.key} onClick={() => { set('type', t.key); setTypeTouched(true) }}>
                  {t.label}<span className="meta">{suggested === t.key ? 'Suggested for this size' : t.hint}</span>
                </button>
              ))}
            </div>
          </section>
        ) : null}
        {step === 3 ? (
          <section className="stack">
            <h1 className="h1">Price and availability</h1>
            <Segmented label="Listing for" value={form.price_type} onChange={(v) => set('price_type', v)} options={[{ key: 'rent', label: 'For rent' }, { key: 'sale', label: 'For sale' }]} />
            <Field label={form.price_type === 'rent' ? 'Monthly rent' : 'Sale price'} htmlFor="price">
              <div className="input-prefix"><span>₹</span><input id="price" className="input" inputMode="numeric" value={form.price_amount}
                onChange={(e) => set('price_amount', e.target.value.replace(/\D/g, ''))} placeholder={form.price_type === 'rent' ? '28000' : '8500000'} /></div>
            </Field>
            <label className="check"><input type="checkbox" checked={form.price_negotiable} onChange={(e) => set('price_negotiable', e.target.checked)} /> Open to discuss</label>
            <Segmented label="Availability" value={form.availability} onChange={(v) => set('availability', v)} options={[{ key: 'now', label: 'Available now' }, { key: 'future', label: 'Available later' }]} />
            {form.availability === 'future' ? (
              <Field label="Available from" htmlFor="from"><input id="from" type="date" className="input" style={{ maxWidth: 220 }} value={form.available_from}
                min={new Date().toISOString().slice(0, 10)} onChange={(e) => set('available_from', e.target.value)} /></Field>
            ) : null}
          </section>
        ) : null}
        {step === 4 ? (
          <section className="stack">
            <h1 className="h1">{live ? 'Review your listing' : 'Last step: details'}</h1>
            <Field label="Short description" htmlFor="desc" hint={`${form.description.trim().length} characters. 40 or more helps businesses decide.`}>
              <textarea id="desc" className="input" value={form.description} maxLength={2000} onChange={(e) => set('description', e.target.value)}
                placeholder="Ground-floor shop on the main road with a wide shutter and a storage room." />
            </Field>
            <Field label="Features">
              <div className="chips">{(config?.amenities || []).map((a) => (
                <Chip key={a.slug} selected={form.amenities.includes(a.slug)} onClick={() => set('amenities', form.amenities.includes(a.slug) ? form.amenities.filter((x) => x !== a.slug) : [...form.amenities, a.slug])}>{a.label}</Chip>
              ))}</div>
            </Field>
            {ctx ? (
              <div className="panel stack-sm accent-pink">
                <h2 className="h3 row"><TrendingUp size={18} aria-hidden /> Local demand within 2 km: {ctx.density}</h2>
                {ctx.top.length ? ctx.top.slice(0, 4).map((t) => (
                  <p key={t.category}><strong>{num(t.supporters)}</strong> residents want {t.category_name.toLowerCase()}{t.suits.includes(form.type) ? ', a good fit for this space' : ''}</p>
                )) : <p className="meta">No requests nearby yet. We&apos;ll tell you when demand appears.</p>}
              </div>
            ) : null}
            {p ? (
              <div className="stack-sm">
                <div className="row-between"><span className="field-label">Listing quality</span><strong>{p.quality_score ?? 0}/100</strong></div>
                <Progress value={(p.quality_score ?? 0) / 100} light />
                {(p.quality_flags || []).length ? <ul className="meta" style={{ margin: 0, paddingLeft: 18 }}>{(p.quality_flags || []).map((f) => <li key={f}>{f}</li>)}</ul> : null}
              </div>
            ) : null}
            {p && p.status !== 'draft' ? (
              <div className="panel panel-tight stack-sm">
                <div className="row-between"><span className="field-label">Ownership</span>
                  {p.verified ? <Badge tone="verified">Verified</Badge> : p.verification_status === 'pending' ? <Badge tone="pending">In review</Badge>
                    : <Button size="sm" variant="secondary" onClick={() => setVerifyOpen(true)}><ShieldCheck size={16} aria-hidden /> Verify ownership</Button>}</div>
                <div className="row">
                  {p.status === 'published' ? <Button size="sm" variant="secondary" onClick={() => status('pause')}>Pause listing</Button> : null}
                  {p.status === 'paused' ? <Button size="sm" variant="secondary" onClick={() => status('resume')}>Resume listing</Button> : null}
                  <Button size="sm" variant="danger" onClick={() => status('archive')}>Archive</Button>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}
        {error ? <Notice tone="error">{error}</Notice> : null}
      </main>
      <div className="flow-actions">
        <div>
          {step > 0 ? <Button variant="secondary" onClick={() => setStep(step - 1)}>Back</Button> : <span />}
          {step < LABELS.length - 1 ? <Button onClick={next} loading={busy} disabled={!canNext || !!uploading}>Continue</Button>
            : <Button onClick={publish} loading={busy}>{live ? 'Save changes' : 'Publish listing'}</Button>}
        </div>
      </div>
      {id ? <VerifyModal open={verifyOpen} onClose={() => setVerifyOpen(false)} id={id} onDone={(s) => setP((x) => (x ? { ...x, verification_status: s } : x))} /> : null}
    </div>
  )
}

function VerifyModal({ open, onClose, id, onDone }: { open: boolean; onClose: () => void; id: string; onDone: (s: string) => void }) {
  const [kind, setKind] = useState('Electricity bill')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async () => {
    setBusy(true); setError(null)
    try {
      const fd = new FormData()
      fd.append('document_type', kind)
      if (file) fd.append('file', file)
      const r = await http.upload<{ status: string }>(`/properties/${id}/verification`, fd)
      onDone(r.status); onClose()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Verify ownership" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={busy} disabled={!file}>Submit for review</Button></>}>
      <p>Upload one document that links you to this space. Only the BizYukti review team can see it.</p>
      <Field label="Document type" htmlFor="doc-kind">
        <select id="doc-kind" className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
          {['Electricity bill', 'Property tax receipt', 'Sale deed', 'Rent authorisation letter'].map((k) => <option key={k}>{k}</option>)}
        </select>
      </Field>
      <Field label="File (PDF or photo, under 10 MB)" htmlFor="doc-file">
        <input id="doc-file" type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] || null)} />
      </Field>
      {error ? <Notice tone="error">{error}</Notice> : null}
    </Modal>
  )
}

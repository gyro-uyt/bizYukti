'use client'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Briefcase, Building2, MapPin, Users } from 'lucide-react'
import { LocationPicker } from '@/components/location-picker'
import { AppShell } from '@/components/shell'
import { useToast } from '@/components/toast'
import { Badge, Button, Chip, Field, Modal, Notice, PageHeader } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useAuth, useRequireAuth } from '@/lib/auth'
import { useLocation } from '@/lib/location'
import type { Me, Role } from '@/lib/types'

const ROLES: { key: Role; label: string; icon: typeof Users }[] = [
  { key: 'resident', label: 'Resident', icon: Users }, { key: 'owner', label: 'Property owner', icon: Building2 }, { key: 'business', label: 'Business', icon: Briefcase },
]

export default function Profile() {
  const user = useRequireAuth()
  const { setUser, signOut } = useAuth()
  const { categories, config } = useLocation()
  const router = useRouter()
  const toast = useToast()
  const [name, setName] = useState('')
  const [picking, setPicking] = useState(false)
  const [biz, setBiz] = useState({ name: '', categories: [] as string[], preferred_cities: '', budget_min: '', budget_max: '', size_min_sqft: '', size_max_sqft: '', registration_id: '', website: '' })
  const [deleting, setDeleting] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    setName(user.name || '')
    const b = user.business
    if (b) setBiz({ name: b.name, categories: b.categories, preferred_cities: b.preferred_cities.join(', '), budget_min: b.budget_min ? String(b.budget_min) : '',
      budget_max: b.budget_max ? String(b.budget_max) : '', size_min_sqft: b.size_min_sqft ? String(b.size_min_sqft) : '',
      size_max_sqft: b.size_max_sqft ? String(b.size_max_sqft) : '', registration_id: b.registration_id || '', website: b.website || '' })
  }, [user])
  if (!user) return null

  const run = async (key: string, fn: () => Promise<Me | void>, ok: string) => {
    setBusy(key)
    try { const me = await fn(); if (me) setUser(me); toast(ok) } catch (e) { toast(errorMessage(e)) } finally { setBusy(null) }
  }
  const n = (v: string) => (v ? Number(v) : null)
  const saveBusiness = () => run('biz', () => http.put<Me>('/me/business', {
    name: biz.name.trim(), categories: biz.categories, preferred_cities: biz.preferred_cities.split(',').map((c) => c.trim()).filter(Boolean),
    budget_min: n(biz.budget_min), budget_max: n(biz.budget_max), size_min_sqft: n(biz.size_min_sqft), size_max_sqft: n(biz.size_max_sqft),
    registration_id: biz.registration_id.trim() || null, website: biz.website.trim() || null,
  }), 'Business profile saved.')
  const showBusiness = user.active_role === 'business' || !!user.business

  return (
    <AppShell>
      <div className="container stack-lg" style={{ maxWidth: 860 }}>
        <PageHeader title="Profile" sub={user.phone || user.email || undefined} />
        <section className="panel stack">
          <h2 className="h2">You</h2>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <Field label="Name" htmlFor="p-name"><input id="p-name" className="input" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></Field>
            <Button variant="secondary" loading={busy === 'name'} disabled={!name.trim() || name === user.name} onClick={() => run('name', () => http.patch<Me>('/me', { name: name.trim() }), 'Name updated.')}>Save</Button>
          </div>
          <div className="row-between">
            <p className="row"><MapPin size={18} aria-hidden /> Home locality: <strong>{user.home?.label || 'Not set'}</strong></p>
            <Button variant="secondary" size="sm" onClick={() => setPicking(true)}>Change</Button>
          </div>
          <p className="meta">Only residents within {config?.trust.local_radius_km ?? 5} km of a request count as supporters. Changing your locality re-checks your pending support.</p>
        </section>
        <section className="panel stack">
          <h2 className="h2">How you use BizYukti</h2>
          <div className="chips">{ROLES.map((r) => (
            <Chip key={r.key} selected={user.active_role === r.key} onClick={() => run('role', () => http.patch<Me>('/me', { active_role: r.key }), `Switched to ${r.label.toLowerCase()} view.`)}>
              <r.icon size={16} aria-hidden /> {r.label}</Chip>))}
            {user.roles.includes('admin') ? <Chip selected={user.active_role === 'admin'} onClick={() => router.push('/admin')}>Admin</Chip> : null}
          </div>
        </section>
        {showBusiness ? (
          <section className="panel stack">
            <div className="row-between"><h2 className="h2">Your business</h2>
              {user.business ? <Badge tone={user.business.verified ? 'verified' : user.business.verification_status === 'pending' ? 'pending' : 'neutral'}>
                {user.business.verified ? 'Verified business' : user.business.verification_status === 'pending' ? 'Verification in review' : 'Not verified'}</Badge> : null}</div>
            <Field label="Business name" htmlFor="b-name"><input id="b-name" className="input" value={biz.name} onChange={(e) => setBiz({ ...biz, name: e.target.value })} /></Field>
            <Field label="Categories"><div className="chips">{categories.filter((c) => c.slug !== 'other').map((c) => (
              <Chip key={c.slug} selected={biz.categories.includes(c.slug)} onClick={() => setBiz({ ...biz, categories: biz.categories.includes(c.slug) ? biz.categories.filter((x) => x !== c.slug) : [...biz.categories, c.slug].slice(0, 6) })}>{c.name}</Chip>))}</div></Field>
            <Field label="Cities" htmlFor="b-city" hint="Comma separated."><input id="b-city" className="input" value={biz.preferred_cities} onChange={(e) => setBiz({ ...biz, preferred_cities: e.target.value })} placeholder="Gwalior" /></Field>
            <div className="grid-2">
              <Field label="Monthly rent from (₹)" htmlFor="b-bmin"><input id="b-bmin" className="input" inputMode="numeric" value={biz.budget_min} onChange={(e) => setBiz({ ...biz, budget_min: e.target.value.replace(/\D/g, '') })} /></Field>
              <Field label="Monthly rent up to (₹)" htmlFor="b-bmax"><input id="b-bmax" className="input" inputMode="numeric" value={biz.budget_max} onChange={(e) => setBiz({ ...biz, budget_max: e.target.value.replace(/\D/g, '') })} /></Field>
              <Field label="Size from (sq ft)" htmlFor="b-smin"><input id="b-smin" className="input" inputMode="numeric" value={biz.size_min_sqft} onChange={(e) => setBiz({ ...biz, size_min_sqft: e.target.value.replace(/\D/g, '') })} /></Field>
              <Field label="Size up to (sq ft)" htmlFor="b-smax"><input id="b-smax" className="input" inputMode="numeric" value={biz.size_max_sqft} onChange={(e) => setBiz({ ...biz, size_max_sqft: e.target.value.replace(/\D/g, '') })} /></Field>
              <Field label="GSTIN or registration number" htmlFor="b-reg"><input id="b-reg" className="input" value={biz.registration_id} maxLength={40} onChange={(e) => setBiz({ ...biz, registration_id: e.target.value.toUpperCase() })} /></Field>
              <Field label="Website (optional)" htmlFor="b-web"><input id="b-web" className="input" value={biz.website} maxLength={200} onChange={(e) => setBiz({ ...biz, website: e.target.value })} /></Field>
            </div>
            <div className="row">
              <Button onClick={saveBusiness} loading={busy === 'biz'} disabled={biz.name.trim().length < 2}>Save business</Button>
              {user.business && !user.business.verified && user.business.verification_status !== 'pending' ? (
                <Button variant="secondary" loading={busy === 'kyb'} onClick={() => run('kyb', async () => { await http.post('/me/business/verification'); return http.get<Me>('/me') }, 'Sent for verification.')}>Request verification</Button>
              ) : null}
            </div>
          </section>
        ) : null}
        <section className="panel stack">
          <h2 className="h2">Account</h2>
          <div className="row">
            <Button variant="secondary" onClick={async () => { await signOut(); router.replace('/') }}>Sign out</Button>
            <Button variant="danger" onClick={() => setDeleting(true)}>Delete account</Button>
          </div>
          <p className="meta"><Link href="/legal/privacy">Privacy policy</Link> and <Link href="/legal/terms">Terms</Link></p>
        </section>
      </div>
      <LocationPicker open={picking} onClose={() => setPicking(false)} title="Change home locality"
        onPick={(l) => run('home', () => http.patch<Me>('/me', { home: { lat: l.lat, lng: l.lng, label: l.label } }), 'Home locality updated.')} />
      <Modal open={deleting} onClose={() => setDeleting(false)} title="Delete your account?"
        footer={<><Button variant="secondary" onClick={() => setDeleting(false)}>Cancel</Button>
          <Button variant="danger" disabled={confirmText !== 'DELETE'} loading={busy === 'delete'} onClick={async () => {
            setBusy('delete')
            try { await http.del('/me'); await signOut(); router.replace('/') } catch (e) { toast(errorMessage(e)); setBusy(null) }
          }}>Delete permanently</Button></>}>
        <Notice tone="warn">Your profile, listings, messages and points are removed. Requests you published stay as anonymous local demand.</Notice>
        <Field label='Type "DELETE" to confirm' htmlFor="del"><input id="del" className="input" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} autoComplete="off" /></Field>
      </Modal>
    </AppShell>
  )
}

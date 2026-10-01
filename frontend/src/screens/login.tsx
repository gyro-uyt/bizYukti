'use client'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'
import { HeroMotif, Logo } from '@/components/brand'
import { Button, Field, Notice, Segmented } from '@/components/ui'
import { errorMessage, http } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { safeNext } from '@/lib/format'
import type { Me } from '@/lib/types'

const DEMO = process.env.NEXT_PUBLIC_DEMO_ACCOUNTS === '1'
const PERSONAS = [
  { label: 'Resident (Asha)', value: '9800000001' },
  { label: 'Owner (Rajesh)', value: '9800000002' },
  { label: 'Business (Neha)', value: '9800000003' },
]

export default function Login() {
  const router = useRouter()
  const params = useSearchParams()
  const next = safeNext(params.get('next'))
  const { user, ready, signIn } = useAuth()
  const [channel, setChannel] = useState<'phone' | 'email'>('phone')
  const [dest, setDest] = useState('')
  const [sent, setSent] = useState<{ destination: string; dev_code?: string } | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ready && user) router.replace(user.onboarded ? next : `/onboarding?next=${encodeURIComponent(next)}`)
  }, [ready, user, next, router])

  const request = async (e?: FormEvent) => {
    e?.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await http.post<{ destination: string; dev_code?: string }>('/auth/otp/request', { channel, destination: dest })
      setSent(r)
      setCode('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const verify = async (e: FormEvent) => {
    e.preventDefault()
    if (!sent) return
    setBusy(true)
    setError(null)
    try {
      const r = await http.post<{ access_token: string; user: Me }>('/auth/otp/verify', { channel, destination: sent.destination, code })
      signIn(r.access_token, r.user)
      router.replace(r.user.onboarded ? next : `/onboarding?next=${encodeURIComponent(next)}`)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <main className="auth-panel" id="main">
        <Link href="/" aria-label="BizYukti home"><Logo /></Link>
        {!sent ? (
          <form className="stack" onSubmit={request}>
            <h1 className="h1">Sign in or join</h1>
            <p className="lead">We&apos;ll send you a 6-digit code. No passwords to remember.</p>
            <Segmented label="Sign in with" value={channel} onChange={(c) => { setChannel(c); setDest('') }}
              options={[{ key: 'phone', label: 'Mobile number' }, { key: 'email', label: 'Email' }]} />
            {channel === 'phone' ? (
              <Field label="Mobile number" htmlFor="dest" hint="Indian numbers can be typed without +91.">
                <div className="input-prefix"><span>+91</span>
                  <input id="dest" className="input" inputMode="tel" autoComplete="tel-national" value={dest} required
                    onChange={(e) => setDest(e.target.value)} placeholder="98765 43210" style={{ paddingLeft: 52 }} /></div>
              </Field>
            ) : (
              <Field label="Email" htmlFor="dest">
                <input id="dest" className="input" type="email" autoComplete="email" value={dest} required onChange={(e) => setDest(e.target.value)} placeholder="you@example.com" />
              </Field>
            )}
            <Button type="submit" block size="lg" loading={busy} disabled={dest.trim().length < 3}>Send code</Button>
            {DEMO ? (
              <div className="stack-sm">
                <p className="meta">Demo accounts (codes appear on screen in demo mode):</p>
                <div className="chips">{PERSONAS.map((p) => <button key={p.value} type="button" className="chip" onClick={() => { setChannel('phone'); setDest(p.value) }}>{p.label}</button>)}</div>
              </div>
            ) : null}
            <p className="meta">By continuing you agree to the <Link href="/legal/terms">Terms</Link> and <Link href="/legal/privacy">Privacy policy</Link>.</p>
          </form>
        ) : (
          <form className="stack" onSubmit={verify}>
            <h1 className="h1">Enter your code</h1>
            <p className="lead">Sent to <strong>{sent.destination}</strong>. <button type="button" className="link" onClick={() => setSent(null)}>Change</button></p>
            <Field label="6-digit code" htmlFor="code">
              <input id="code" className="input input-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} autoFocus
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
            </Field>
            {sent.dev_code ? <Notice tone="info">Demo mode: your code is <strong>{sent.dev_code}</strong>. Real codes arrive by SMS or email.</Notice> : null}
            <Button type="submit" block size="lg" loading={busy} disabled={code.length !== 6}>Verify and continue</Button>
            <button type="button" className="link" onClick={() => request()} disabled={busy}>Send a new code</button>
          </form>
        )}
        {error ? <Notice tone="error">{error}</Notice> : null}
      </main>
      <aside className="auth-side on-blue" aria-hidden="true">
        <div className="stack" style={{ maxWidth: 420 }}>
          <HeroMotif />
          <p className="h2">Ask for what your area needs. Fill empty spaces. Open where you&apos;re wanted.</p>
        </div>
      </aside>
    </div>
  )
}

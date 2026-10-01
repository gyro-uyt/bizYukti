'use client'
import { useState, type ReactNode } from 'react'
import { LocateFixed, MapPin } from 'lucide-react'
import { http } from '@/lib/api'
import { useApi, useDebounced } from '@/lib/hooks'
import { useLocation, type Loc } from '@/lib/location'
import type { AreaRef } from '@/lib/types'
import { Button, Field, Modal, Notice } from './ui'

export function locateMe(): Promise<{ lat: number; lng: number }> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) return reject(new Error("Location isn't available on this device."))
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => reject(new Error("We couldn't get your location. Check the permission, or pick an area instead.")),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    )
  })
}

export type QuickPick = Loc & { key: string; hint?: string }

export function LocationPicker({ open, onClose, onPick, title = 'Change location', intro, quick }:
  { open: boolean; onClose: () => void; onPick?: (l: Loc) => void; title?: string; intro?: ReactNode; quick?: QuickPick[] }) {
  const { setLoc } = useLocation()
  const [q, setQ] = useState('')
  const dq = useDebounced(q, 250)
  const { data } = useApi<AreaRef[]>(open ? '/geo/areas' : null, { q: dq })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pick = (l: Loc) => {
    if (onPick) onPick(l)
    else setLoc(l)
    onClose()
  }
  const mine = async () => {
    setBusy(true)
    setError(null)
    try {
      const p = await locateMe()
      const r = await http.get<{ locality: string }>('/geo/reverse', p).catch(() => ({ locality: 'My location' }))
      pick({ ...p, label: r.locality })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={title}>
      {intro ? <p>{intro}</p> : null}
      {quick?.length ? (
        <ul className="pick-list">
          {quick.map((l) => (
            <li key={l.key}>
              <button type="button" onClick={() => pick({ lat: l.lat, lng: l.lng, label: l.label })}>
                <MapPin size={16} aria-hidden /> <span>{l.label}</span>{l.hint ? <span className="meta">{l.hint}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <Button variant="secondary" block onClick={mine} loading={busy}><LocateFixed size={18} aria-hidden /> Use my current location</Button>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Field label="Or choose an area" htmlFor="area-q">
        <input id="area-q" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search areas, e.g. Thatipur" autoComplete="off" />
      </Field>
      <ul className="pick-list">
        {(data || []).map((a) => (
          <li key={a.id}>
            <button type="button" onClick={() => pick({ lat: a.lat, lng: a.lng, label: a.name })}>
              <MapPin size={16} aria-hidden /> <span>{a.name}</span><span className="meta">{a.city}</span>
            </button>
          </li>
        ))}
        {data && !data.length ? <li><p className="meta" style={{ padding: 14 }}>No areas match that search yet.</p></li> : null}
      </ul>
    </Modal>
  )
}

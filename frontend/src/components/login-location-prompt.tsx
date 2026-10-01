'use client'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { errorMessage, http } from '@/lib/api'
import { LOCATION_PROMPT_KEY, useAuth } from '@/lib/auth'
import { useLocation, type Loc } from '@/lib/location'
import type { Me, Space } from '@/lib/types'
import { LocationPicker, type QuickPick } from './location-picker'
import { useToast } from './toast'

const COPY: Record<string, { title: string; intro: string }> = {
  resident: { title: 'Where do you live?', intro: 'We show requests near your home. Only residents within 5 km of a request count as supporters.' },
  owner: { title: 'Where is your property?', intro: 'We show the local demand around your space and the requests nearby.' },
  business: { title: 'Where do you want to open?', intro: 'We show demand, available spaces and areas around your target location.' },
}
const FALLBACK_COPY = { title: 'Choose your location', intro: 'We show what is happening around this location.' }
// Wait until sign-in has redirected away from these pages before asking.
const HOLD_ON = ['/login', '/onboarding']

/** Asks once after every sign-in for the location the active role works from, and applies it app-wide. */
export function LoginLocationPrompt() {
  const { user, setUser } = useAuth()
  const { loc, setLoc } = useLocation()
  const toast = useToast()
  const path = usePathname() || '/'
  const [open, setOpen] = useState(false)
  const [spaces, setSpaces] = useState<QuickPick[]>([])

  useEffect(() => {
    if (!user?.onboarded || HOLD_ON.some((p) => path.startsWith(p))) return
    try {
      if (sessionStorage.getItem(LOCATION_PROMPT_KEY) !== '1') return
      sessionStorage.removeItem(LOCATION_PROMPT_KEY)
    } catch { return }
    setOpen(true)
  }, [user?.onboarded, path])

  const role = user?.active_role
  useEffect(() => {
    if (!open || role !== 'owner') return
    http.get<{ spaces: Space[] }>('/properties/mine').then((r) => setSpaces(r.spaces
      .filter((s) => s.lat != null && s.lng != null)
      .map((s) => ({ key: s.id, lat: s.lat as number, lng: s.lng as number, label: `${s.display_title}, ${s.locality || 'your space'}`, hint: 'Your space' }))))
      .catch(() => setSpaces([]))
  }, [open, role])

  if (!user) return null
  const copy = (role && COPY[role]) || FALLBACK_COPY
  const current: QuickPick[] = role === 'resident' && user.home
    ? [{ key: 'home', lat: user.home.lat, lng: user.home.lng, label: user.home.label || 'Home', hint: 'Current home' }]
    : [{ key: 'current', ...loc, hint: 'Current location' }]

  const pick = async (l: Loc) => {
    setLoc(l)
    const sameHome = user.home && user.home.lat === l.lat && user.home.lng === l.lng
    if (role === 'resident' && !sameHome) {
      try {
        setUser(await http.patch<Me>('/me', { home: { lat: l.lat, lng: l.lng, label: l.label } }))
        toast(`Home set to ${l.label}.`)
      } catch (e) { toast(errorMessage(e)) }
    } else {
      toast(`Showing results near ${l.label}.`)
    }
  }

  return (
    <LocationPicker open={open} onClose={() => setOpen(false)} onPick={pick} title={copy.title} intro={copy.intro}
      quick={[...current, ...spaces.filter((s) => !current.some((c) => c.lat === s.lat && c.lng === s.lng))]} />
  )
}

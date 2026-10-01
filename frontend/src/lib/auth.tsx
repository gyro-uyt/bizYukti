'use client'
import { usePathname, useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { http, onSession, refreshSession, setToken } from './api'
import type { Me } from './types'

type AuthCtx = {
  user: Me | null
  ready: boolean
  signIn: (token: string, user: Me) => void
  signOut: () => Promise<void>
  reload: () => Promise<Me | null>
  setUser: (u: Me | null) => void
}

const Ctx = createContext<AuthCtx | null>(null)

// Set on a fresh sign-in so the app asks for the person's location once (see LoginLocationPrompt).
// New accounts skip it: onboarding already asks for their locality.
export const LOCATION_PROMPT_KEY = 'by_loc_prompt'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [ready, setReady] = useState(false)

  const reload = useCallback(async () => {
    try {
      const me = await http.get<Me>('/me')
      setUser(me)
      return me
    } catch {
      return null
    }
  }, [])

  useEffect(() => {
    const off = onSession((u) => setUser((prev) => (u ? { ...(prev || {}), ...u } as Me : null)))
    refreshSession().then(async (ok) => {
      if (ok) await reload()
      setReady(true)
    })
    const keepAlive = setInterval(() => { refreshSession() }, 12 * 60 * 1000)
    return () => { off(); clearInterval(keepAlive) }
  }, [reload])

  const signIn = useCallback((token: string, u: Me) => {
    try {
      if (u.onboarded) sessionStorage.setItem(LOCATION_PROMPT_KEY, '1')
      else sessionStorage.removeItem(LOCATION_PROMPT_KEY)
    } catch { /* storage unavailable: skip the prompt */ }
    setToken(token)
    setUser(u)
    setReady(true)
    reload()
  }, [reload])

  const signOut = useCallback(async () => {
    try { await http.post('/auth/logout') } catch { /* already signed out */ }
    try { sessionStorage.removeItem(LOCATION_PROMPT_KEY) } catch { /* ignore */ }
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, ready, signIn, signOut, reload, setUser }), [user, ready, signIn, signOut, reload])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

/** Redirects to sign-in (or onboarding) when needed; returns the user once available. */
export function useRequireAuth(opts: { role?: string; allowNotOnboarded?: boolean } = {}): Me | null {
  const { user, ready } = useAuth()
  const router = useRouter()
  const path = usePathname()
  useEffect(() => {
    if (!ready) return
    if (!user) {
      const here = typeof window !== 'undefined' ? window.location.pathname + window.location.search : path
      router.replace(`/login?next=${encodeURIComponent(here)}`)
    } else if (!user.onboarded && !opts.allowNotOnboarded) {
      router.replace(`/onboarding?next=${encodeURIComponent(path)}`)
    } else if (opts.role && !user.roles.includes(opts.role as Me['roles'][number])) {
      router.replace('/home')
    }
  }, [ready, user, router, path, opts.allowNotOnboarded, opts.role])
  if (!user || (!user.onboarded && !opts.allowNotOnboarded)) return null
  if (opts.role && !user.roles.includes(opts.role as Me['roles'][number])) return null
  return user
}

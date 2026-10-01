'use client'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { http } from './api'
import { useAuth } from './auth'
import type { AppConfig, Category } from './types'

export type Loc = { lat: number; lng: number; label: string }

type LocCtx = {
  loc: Loc
  setLoc: (l: Loc) => void
  config: AppConfig | null
  categories: Category[]
  category: (slug: string | null | undefined) => Category | undefined
}

const FALLBACK: Loc = { lat: 26.2183, lng: 78.1828, label: 'Gwalior' }
const Ctx = createContext<LocCtx | null>(null)

export function LocationProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [loc, setLocState] = useState<Loc>(FALLBACK)
  const [chosen, setChosen] = useState(false)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [categories, setCategories] = useState<Category[]>([])

  useEffect(() => {
    http.get<AppConfig>('/meta/config').then((c) => {
      setConfig(c)
      setLocState((l) => (l === FALLBACK ? { ...c.default_center, label: c.default_city } : l))
    }).catch(() => {})
    http.get<Category[]>('/meta/categories').then(setCategories).catch(() => {})
    try {
      const saved = localStorage.getItem('by_loc')
      if (saved) { setLocState(JSON.parse(saved)); setChosen(true) }
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (!chosen && user?.home) setLocState({ lat: user.home.lat, lng: user.home.lng, label: user.home.label || 'Home' })
  }, [user?.home, chosen])

  const setLoc = useCallback((l: Loc) => {
    setLocState(l)
    setChosen(true)
    try { localStorage.setItem('by_loc', JSON.stringify(l)) } catch { /* ignore */ }
  }, [])

  const category = useCallback((slug: string | null | undefined) => categories.find((c) => c.slug === slug), [categories])
  const value = useMemo(() => ({ loc, setLoc, config, categories, category }), [loc, setLoc, config, categories, category])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useLocation(): LocCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useLocation must be used inside LocationProvider')
  return ctx
}

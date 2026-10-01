'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, http } from './api'

type Query = Record<string, string | number | boolean | null | undefined>

/** GET with loading/error state. Pass path=null to skip. Stale responses are ignored. */
export function useApi<T = any>(path: string | null, query?: Query) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState<boolean>(!!path)
  const seq = useRef(0)
  const key = path ? `${path}?${JSON.stringify(query || {})}` : null

  const load = useCallback(async () => {
    if (!path) { setLoading(false); return }
    const n = ++seq.current
    setLoading(true)
    try {
      const d = await http.get<T>(path, query)
      if (n === seq.current) { setData(d); setError(null) }
    } catch (e) {
      if (n === seq.current) setError(e instanceof ApiError ? e : new ApiError(0, String(e), null))
    } finally {
      if (n === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => { load() }, [load])
  return { data, error, loading, reload: load, setData }
}

export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function useMedia(query: string): boolean {
  const [match, setMatch] = useState(false)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setMatch(m.matches)
    on()
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [query])
  return match
}

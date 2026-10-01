// Thin fetch client. Access tokens live only in memory; the refresh token is an httpOnly
// cookie scoped to /api/v1/auth, so a page reload restores the session through /auth/refresh.
import type { Me } from './types'

const BASE = `${process.env.NEXT_PUBLIC_API_BASE || ''}/api/v1`

export class ApiError extends Error {
  status: number
  data: any
  constructor(status: number, message: string, data: any) {
    super(message)
    this.status = status
    this.data = data
  }
}

type Query = Record<string, string | number | boolean | null | undefined>
type Opts = { method?: string; body?: unknown; query?: Query; form?: FormData; signal?: AbortSignal }

let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null
const listeners = new Set<(user: Me | null) => void>()

export function setToken(token: string | null) { accessToken = token }
export function hasToken() { return !!accessToken }
export function onSession(fn: (user: Me | null) => void) {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

export function deviceId(): string {
  if (typeof window === 'undefined') return ''
  try {
    let id = localStorage.getItem('by_device')
    if (!id) {
      id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
      localStorage.setItem('by_device', id)
    }
    return id
  } catch {
    return ''
  }
}

export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh`, { method: 'POST', credentials: 'include' })
      .then(async (r) => {
        if (!r.ok) {
          accessToken = null
          listeners.forEach((l) => l(null))
          return false
        }
        const data = await r.json()
        accessToken = data.access_token
        listeners.forEach((l) => l(data.user))
        return true
      })
      .catch(() => false)
      .finally(() => { refreshing = null })
  }
  return refreshing
}

function buildUrl(path: string, query?: Query) {
  const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin
  const url = new URL(BASE + path, origin)
  Object.entries(query || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
  })
  return url.toString()
}

async function send(path: string, opts: Opts, retry: boolean): Promise<Response> {
  const headers: Record<string, string> = { 'X-Device-Id': deviceId() }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method || (body ? 'POST' : 'GET'), headers, body, credentials: 'include', signal: opts.signal,
  })
  if (res.status === 401 && retry && !path.startsWith('/auth/') && (await refreshSession())) {
    return send(path, opts, false)
  }
  return res
}

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  let res: Response
  try {
    res = await send(path, opts, true)
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, "You're offline or the server can't be reached. Try again in a moment.", null)
  }
  const text = await res.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { data = { detail: text } }
  if (!res.ok) {
    const message = (data && (data.detail || data.message)) || `Something went wrong (${res.status}).`
    throw new ApiError(res.status, typeof message === 'string' ? message : 'Something went wrong.', data)
  }
  return data as T
}

export async function apiBlob(path: string): Promise<Blob> {
  const res = await send(path, {}, true)
  if (!res.ok) throw new ApiError(res.status, 'Could not load the file.', null)
  return res.blob()
}

export const http = {
  get: <T = any>(path: string, query?: Query, signal?: AbortSignal) => api<T>(path, { query, signal }),
  post: <T = any>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body }),
  patch: <T = any>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body }),
  put: <T = any>(path: string, body: unknown) => api<T>(path, { method: 'PUT', body }),
  del: <T = any>(path: string, query?: Query) => api<T>(path, { method: 'DELETE', query }),
  upload: <T = any>(path: string, form: FormData) => api<T>(path, { method: 'POST', form }),
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : 'Something went wrong.'
}

import type { Space } from './types'

const trim = (x: number) => String(Math.round(x * 100) / 100)

export const num = (n: number | null | undefined) => (n ?? 0).toLocaleString('en-IN')
export const inr = (n: number) => `₹${Math.round(n).toLocaleString('en-IN')}`

/** Compact rupees for reports: ₹52,400 · ₹5.5 lakh · ₹1.25 crore (sign kept). */
export function inrShort(n: number): string {
  const sign = n < 0 ? '−' : ''
  const a = Math.abs(n)
  if (a >= 1e7) return `${sign}₹${trim(a / 1e7)} crore`
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(1).replace(/\.0$/, '')} lakh`
  return `${sign}₹${Math.round(a).toLocaleString('en-IN')}`
}

export function price(s: Pick<Space, 'price_type' | 'price_amount' | 'price_negotiable'>): string {
  if (!s.price_amount) return s.price_negotiable ? 'Open to discuss' : 'Price on request'
  const neg = s.price_negotiable ? ', negotiable' : ''
  if (s.price_type === 'sale') {
    const a = s.price_amount
    return (a >= 1e7 ? `₹${trim(a / 1e7)} crore` : a >= 1e5 ? `₹${trim(a / 1e5)} lakh` : inr(a)) + neg
  }
  return `${inr(s.price_amount)}/month${neg}`
}

export function budgetLabel(n: number) {
  return n >= 1e5 ? `₹${trim(n / 1e5)} lakh` : `₹${Math.round(n / 1000)}k`
}

export const distance = (m: number | null | undefined) =>
  m == null ? '' : m < 1000 ? `${Math.max(10, Math.round(m / 10) * 10)} m away` : `${(m / 1000).toFixed(1)} km away`

export const sqft = (n: number | null | undefined) => (n ? `${Math.round(n).toLocaleString('en-IN')} sq ft` : '')

export const plural = (n: number, one: string, many = `${one}s`) => `${num(n)} ${n === 1 ? one : many}`

export function ago(iso: string | null | undefined): string {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`
  return date(iso)
}

export function date(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

export const firstName = (name: string | null | undefined) => (name || '').trim().split(/\s+/)[0] || 'there'

export const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft', published: 'Published', growing: 'Growing', matched: 'Matched', fulfilled: 'Opened',
  expired: 'Closed', rejected: 'Removed', paused: 'Paused', archived: 'Archived',
}

export const pct = (v: number | null | undefined) => (v == null ? 'No data yet' : `${Math.round(v * 100)}%`)

export function safeNext(next: string | null | undefined, fallback = '/home'): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : fallback
}

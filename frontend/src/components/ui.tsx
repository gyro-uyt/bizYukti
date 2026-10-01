'use client'
import Link from 'next/link'
import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { ArrowLeft, Check, CircleAlert, CircleCheck, Clock, Info, Loader, ShieldCheck, TriangleAlert, X } from 'lucide-react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'pink' | 'danger' | 'inverse' | 'success'
type Size = 'sm' | 'md' | 'lg'

export function Button({ variant = 'primary', size = 'md', loading, block, className = '', children, type, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; block?: boolean }) {
  return (
    <button {...rest} type={type ?? 'button'} disabled={loading || rest.disabled} aria-busy={loading || undefined}
      className={`btn btn-${variant} btn-${size}${block ? ' btn-block' : ''} ${className}`}>
      {loading ? <Loader className="spin" size={18} aria-hidden /> : null}
      {children}
    </button>
  )
}

export function LinkButton({ href, variant = 'primary', size = 'md', block, children, className = '' }:
  { href: string; variant?: Variant; size?: Size; block?: boolean; children: ReactNode; className?: string }) {
  return <Link href={href} className={`btn btn-${variant} btn-${size}${block ? ' btn-block' : ''} ${className}`}>{children}</Link>
}

export function Field({ label, hint, error, children, htmlFor }:
  { label: string; hint?: ReactNode; error?: string | null; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error ? <p className="field-hint">{hint}</p> : null}
      {error ? <p className="field-error" role="alert"><CircleAlert size={15} aria-hidden /> {error}</p> : null}
    </div>
  )
}

export function Chip({ selected, onClick, children }: { selected?: boolean; onClick?: () => void; children: ReactNode }) {
  return (
    <button type="button" className={`chip${selected ? ' is-selected' : ''}`} aria-pressed={!!selected} onClick={onClick}>
      {selected ? <Check size={16} aria-hidden /> : null}{children}
    </button>
  )
}

export type Tone = 'verified' | 'pending' | 'demand' | 'supply' | 'blue' | 'neutral' | 'warn' | 'strong' | 'promising' | 'early' | 'bad'

export function Badge({ tone = 'neutral', children, icon }: { tone?: Tone; children: ReactNode; icon?: ReactNode }) {
  const auto = tone === 'verified' ? <ShieldCheck size={14} aria-hidden /> : tone === 'pending' ? <Clock size={14} aria-hidden /> : null
  return <span className={`badge badge-${tone}`}>{icon ?? auto}{children}</span>
}

export function Notice({ tone = 'info', children }: { tone?: 'info' | 'error' | 'success' | 'warn'; children: ReactNode }) {
  const Icon = tone === 'error' ? CircleAlert : tone === 'success' ? CircleCheck : tone === 'warn' ? TriangleAlert : Info
  return <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : undefined}><Icon size={18} aria-hidden /><div>{children}</div></div>
}

export function Empty({ title, body, action, icon }: { title: string; body?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return <div className="empty">{icon}<h2 className="h3">{title}</h2>{body ? <p>{body}</p> : null}{action}</div>
}

export function Skeleton({ rows = 3, height = 72 }: { rows?: number; height?: number }) {
  return <div className="stack-sm" aria-busy="true" aria-label="Loading">{Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ minHeight: height }} />)}</div>
}

export function Stat({ value, label, tone }: { value: ReactNode; label: ReactNode; tone?: 'pink' | 'orange' | 'blue' | 'green' }) {
  return <div className={`stat${tone ? ` stat-${tone}` : ''}`}><span className="stat-value">{value}</span><span className="stat-label">{label}</span></div>
}

export function Tabs<T extends string>({ tabs, value, onChange, label }:
  { tabs: { key: T; label: string; count?: number }[]; value: T; onChange: (k: T) => void; label?: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.key} type="button" role="tab" aria-selected={value === t.key} className={`tab${value === t.key ? ' is-active' : ''}`}
          onClick={() => onChange(t.key)}>
          {t.label}{t.count != null ? <span className="tab-count">{t.count}</span> : null}
        </button>
      ))}
    </div>
  )
}

export function Segmented<T extends string>({ options, value, onChange, label }:
  { options: { key: T; label: string }[]; value: T; onChange: (k: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => <button key={o.key} type="button" aria-pressed={value === o.key} onClick={() => onChange(o.key)}>{o.label}</button>)}
    </div>
  )
}

export function Steps({ step, total, label }: { step: number; total: number; label: string }) {
  return (
    <div className="steps">
      <p className="meta">Step {step + 1} of {total}: <strong>{label}</strong></p>
      <div className="steps-bar" aria-hidden>{Array.from({ length: total }).map((_, i) => <span key={i} className={i <= step ? 'is-done' : ''} />)}</div>
    </div>
  )
}

export function Progress({ value, light }: { value: number; light?: boolean }) {
  const v = Math.max(0, Math.min(1, value))
  return <div className={`progress${light ? ' on-light' : ''}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}><span style={{ width: `${v * 100}%` }} /></div>
}

export function PageHeader({ title, sub, back, action }: { title: ReactNode; sub?: ReactNode; back?: string; action?: ReactNode }) {
  return (
    <header className="page-head">
      {back ? <Link href={back} className="back-link"><ArrowLeft size={18} aria-hidden /> Back</Link> : null}
      <div className="page-head-row">
        <div className="stack-sm"><h1 className="h1">{title}</h1>{sub ? <p className="lead">{sub}</p> : null}</div>
        {action}
      </div>
    </header>
  )
}

export function Modal({ open, onClose, title, children, footer }:
  { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    const first = ref.current?.querySelector<HTMLElement>('.modal-body input, .modal-body textarea, .modal-body select, .modal-body button')
    ;(first || ref.current?.querySelector<HTMLElement>('button'))?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close.current()
      if (e.key === 'Tab' && ref.current) {
        const items = Array.from(ref.current.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input, select, textarea'))
        if (!items.length) return
        const [a, b] = [items[0], items[items.length - 1]]
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); b.focus() }
        else if (!e.shiftKey && document.activeElement === b) { e.preventDefault(); a.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; prev?.focus() }
  }, [open])
  if (!open) return null
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" ref={ref}>
        <div className="modal-head">
          <h2 id="modal-title" className="h2">{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-foot">{footer}</div> : null}
      </div>
    </div>
  )
}

export function StickyCTA({ children }: { children: ReactNode }) {
  return <div className="sticky-cta"><div className="cta-row">{children}</div></div>
}

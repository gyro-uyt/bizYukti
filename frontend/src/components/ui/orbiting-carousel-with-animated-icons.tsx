'use client'
// Orbiting carousel (adapted from the 21st.dev "orbiting carousel with animated icons" component).
// Styled with the BizYukti design tokens (globals.css, .orb-*) instead of Tailwind, and driven by props.
import Link from 'next/link'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useCallback, useEffect, useState, type KeyboardEvent, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, type LucideIcon } from 'lucide-react'

export type OrbitTone = 'pink' | 'orange' | 'blue' | 'green'
export type OrbitItem = {
  id: string
  title: string
  href: string
  icon: LucideIcon
  tone: OrbitTone
  image?: string
  eyebrow?: string
  subtitle?: string
  stat?: string
  statLabel?: string
  badge?: ReactNode
  cta?: string
}

type Size = 'xs' | 'sm' | 'md' | 'lg'
const SIZES: Record<Size, { radius: number; node: number; card: number; avatar: number }> = {
  xs: { radius: 112, node: 44, card: 160, avatar: 50 },
  sm: { radius: 134, node: 54, card: 180, avatar: 58 },
  md: { radius: 164, node: 64, card: 204, avatar: 68 },
  lg: { radius: 206, node: 76, card: 236, avatar: 80 },
}

function useResponsive(): Size {
  const [size, setSize] = useState<Size>('lg')
  useEffect(() => {
    const check = () => {
      const w = window.innerWidth
      setSize(w < 480 ? 'xs' : w < 640 ? 'sm' : w < 768 ? 'md' : 'lg')
    }
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])
  return size
}

const mod = (a: number, n: number) => ((a % n) + n) % n

export default function OrbitCarousel({ items, label, autoplayMs = 5000 }: { items: OrbitItem[]; label: string; autoplayMs?: number }) {
  // `step` grows or shrinks without wrapping, so the orbit always turns the short way round.
  const [step, setStep] = useState(0)
  const [paused, setPaused] = useState(false)
  const reduce = useReducedMotion()
  const size = useResponsive()
  const s = SIZES[size]
  const n = items.length
  const active = n ? mod(step, n) : 0

  const next = useCallback(() => setStep((v) => v + 1), [])
  const prev = useCallback(() => setStep((v) => v - 1), [])
  const goTo = useCallback((i: number) => setStep((v) => {
    const cur = mod(v, n)
    let delta = mod(i - cur, n)
    if (delta > n / 2) delta -= n
    return v + delta
  }), [n])

  useEffect(() => { setStep(0) }, [items.map((it) => it.id).join(',')]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (paused || reduce || n < 2) return
    const t = setInterval(next, autoplayMs)
    return () => clearInterval(t)
  }, [paused, reduce, n, next, autoplayMs])

  if (!n) return null
  const cur = items[active]
  const box = s.radius * 2 + s.node + 16
  const orbit = reduce ? { duration: 0 } : { type: 'spring' as const, stiffness: 150, damping: 20 }
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); prev() } else if (e.key === 'ArrowRight') { e.preventDefault(); next() }
  }

  return (
    <div className={`orb orb--${size}`} role="region" aria-roledescription="carousel" aria-label={label} tabIndex={0} onKeyDown={onKey}
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setPaused(false) }}>
      <p className="sr-only" aria-live="polite">{`${active + 1} of ${n}: ${cur.title}`}</p>
      <div className="orb-stage" style={{ width: box, height: box }}>
        <span className="orb-track" aria-hidden style={{ width: s.radius * 2, height: s.radius * 2 }} />
        <span className="orb-track is-inner" aria-hidden style={{ width: s.radius * 1.35, height: s.radius * 1.35 }} />

        <AnimatePresence mode="wait">
          <motion.div key={cur.id} className="orb-card" style={{ width: s.card }}
            initial={reduce ? false : { opacity: 0, scale: 0.92, y: 16 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, scale: 0.92, y: -16 }} transition={{ type: 'spring', stiffness: 300, damping: 25 }}>
            <span className={`orb-avatar tone-${cur.tone}`} style={{ width: s.avatar, height: s.avatar, marginTop: -(s.avatar / 2) - 12 }}>
              {cur.image ? <img src={cur.image} alt="" /> : <cur.icon size={Math.round(s.avatar * 0.46)} aria-hidden />}
            </span>
            {cur.eyebrow ? <p className="orb-eyebrow">{cur.eyebrow}</p> : null}
            <h3 className="orb-title">{cur.title}</h3>
            {cur.subtitle ? <p className="orb-sub">{cur.subtitle}</p> : null}
            {cur.stat ? <p className="orb-stat"><strong>{cur.stat}</strong> {cur.statLabel}</p> : null}
            {cur.badge}
            <div className="orb-actions">
              <button type="button" className="orb-arrow" onClick={prev} aria-label="Previous"><ChevronLeft size={16} aria-hidden /></button>
              <Link href={cur.href} className="btn btn-primary btn-sm orb-cta">{cur.cta || 'View'}</Link>
              <button type="button" className="orb-arrow" onClick={next} aria-label="Next"><ChevronRight size={16} aria-hidden /></button>
            </div>
          </motion.div>
        </AnimatePresence>

        {items.map((it, i) => {
          const rotation = (i - step) * (360 / n)
          const on = i === active
          return (
            <motion.div key={it.id} className="orb-node-wrap" initial={false}
              animate={{ transform: `rotate(${rotation}deg) translateY(-${s.radius}px)` }}
              transition={{ ...orbit, delay: reduce || on ? 0 : Math.min(Math.abs(i - active), 4) * 0.04 }}
              style={{ width: s.node, height: s.node, top: `calc(50% - ${s.node / 2}px)`, left: `calc(50% - ${s.node / 2}px)`, zIndex: on ? 20 : 10 }}>
              {/* Counter-rotation keeps each image upright */}
              <motion.div initial={false} animate={{ rotate: -rotation }} transition={orbit} style={{ width: '100%', height: '100%' }}>
                <motion.button type="button" className={`orb-node tone-${it.tone}${on ? ' is-active' : ''}`} onClick={() => goTo(i)}
                  aria-label={`Show ${it.title}`} aria-pressed={on} whileHover={reduce ? undefined : { scale: 1.12 }} whileTap={reduce ? undefined : { scale: 0.95 }}>
                  {it.image ? <img src={it.image} alt="" /> : (
                    <motion.span className="orb-icon" animate={reduce ? undefined : { y: [0, -3, 0] }}
                      transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut', delay: i * 0.2 }}>
                      <it.icon size={Math.round(s.node * 0.42)} aria-hidden />
                    </motion.span>
                  )}
                </motion.button>
              </motion.div>
            </motion.div>
          )
        })}
      </div>

      <div className="orb-dots" role="group" aria-label="Choose an item">
        {items.map((it, i) => (
          <button key={it.id} type="button" className={`orb-dot${i === active ? ' is-active' : ''}`} onClick={() => goTo(i)}
            aria-label={`Go to ${i + 1}: ${it.title}`} aria-current={i === active ? 'true' : undefined} />
        ))}
      </div>
    </div>
  )
}

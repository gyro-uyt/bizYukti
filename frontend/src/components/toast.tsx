'use client'
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

const Ctx = createContext<(message: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const show = useCallback((m: string) => {
    setMessage(m)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setMessage(null), 4000)
  }, [])
  return (
    <Ctx.Provider value={show}>
      {children}
      <div aria-live="polite" aria-atomic="true">{message ? <div className="toast" role="status">{message}</div> : null}</div>
    </Ctx.Provider>
  )
}

export const useToast = () => useContext(Ctx)

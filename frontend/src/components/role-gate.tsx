'use client'
import { useRouter } from 'next/navigation'
import { useEffect, type ReactNode } from 'react'
import { canUse, type Feature } from '@/lib/access'
import { useAuth } from '@/lib/auth'

/** Sends signed-in people whose active role doesn't use this feature back to their home screen. */
export function RoleGate({ feature, children }: { feature: Feature; children: ReactNode }) {
  const { user, ready } = useAuth()
  const router = useRouter()
  const allowed = canUse(user, feature)
  useEffect(() => {
    if (ready && !allowed) router.replace('/home')
  }, [ready, allowed, router])
  if (ready && !allowed) return null
  return <>{children}</>
}

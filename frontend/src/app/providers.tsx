'use client'
import type { ReactNode } from 'react'
import { LoginLocationPrompt } from '@/components/login-location-prompt'
import { ToastProvider } from '@/components/toast'
import { AuthProvider } from '@/lib/auth'
import { LocationProvider } from '@/lib/location'

export function Providers({ children }: { children: ReactNode }) {
  return <AuthProvider><LocationProvider><ToastProvider>{children}<LoginLocationPrompt /></ToastProvider></LocationProvider></AuthProvider>
}

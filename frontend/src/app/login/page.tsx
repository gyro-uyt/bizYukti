import type { Metadata } from 'next'
import { Suspense } from 'react'
import Login from '@/screens/login'

export const metadata: Metadata = { title: 'Sign in' }

export default function Page() {
  return <Suspense><Login /></Suspense>
}

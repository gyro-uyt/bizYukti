import type { Metadata } from 'next'
import { Suspense } from 'react'
import Profile from '@/screens/profile'

export const metadata: Metadata = { title: 'Profile' }

export default function Page() {
  return <Suspense><Profile /></Suspense>
}

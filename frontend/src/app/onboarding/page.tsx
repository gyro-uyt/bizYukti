import type { Metadata } from 'next'
import { Suspense } from 'react'
import Onboarding from '@/screens/onboarding'

export const metadata: Metadata = { title: 'Get started' }

export default function Page() {
  return <Suspense><Onboarding /></Suspense>
}

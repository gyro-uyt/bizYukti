import type { Metadata } from 'next'
import { Suspense } from 'react'
import PropertyMatches from '@/screens/property-matches'

export const metadata: Metadata = { title: 'Demand matches' }

export default function Page() {
  return <Suspense><PropertyMatches /></Suspense>
}

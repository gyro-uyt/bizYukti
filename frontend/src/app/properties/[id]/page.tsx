import type { Metadata } from 'next'
import { Suspense } from 'react'
import PropertyDetail from '@/screens/property-detail'

export const metadata: Metadata = { title: 'Available space' }

export default function Page() {
  return <Suspense><PropertyDetail /></Suspense>
}

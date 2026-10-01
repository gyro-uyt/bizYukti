import type { Metadata } from 'next'
import { Suspense } from 'react'
import PropertyForm from '@/screens/property-form'

export const metadata: Metadata = { title: 'Edit listing' }

export default function Page() {
  return <Suspense><PropertyForm /></Suspense>
}

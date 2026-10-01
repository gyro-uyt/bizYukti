import type { Metadata } from 'next'
import { Suspense } from 'react'
import Legal from '@/screens/legal'

export const metadata: Metadata = { title: 'Legal' }

export default function Page() {
  return <Suspense><Legal /></Suspense>
}

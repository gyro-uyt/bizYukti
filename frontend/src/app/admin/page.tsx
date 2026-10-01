import type { Metadata } from 'next'
import { Suspense } from 'react'
import Admin from '@/screens/admin'

export const metadata: Metadata = { title: 'Admin review' }

export default function Page() {
  return <Suspense><Admin /></Suspense>
}

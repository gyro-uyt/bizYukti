import type { Metadata } from 'next'
import { Suspense } from 'react'
import Explore from '@/screens/explore'

export const metadata: Metadata = { title: 'Explore' }

export default function Page() {
  return <Suspense><Explore /></Suspense>
}

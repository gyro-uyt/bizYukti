import type { Metadata } from 'next'
import { Suspense } from 'react'
import Rewards from '@/screens/rewards'

export const metadata: Metadata = { title: 'Rewards' }

export default function Page() {
  return <Suspense><Rewards /></Suspense>
}

import type { Metadata } from 'next'
import { Suspense } from 'react'
import MyDemands from '@/screens/demands-mine'

export const metadata: Metadata = { title: 'My requests' }

export default function Page() {
  return <Suspense><MyDemands /></Suspense>
}

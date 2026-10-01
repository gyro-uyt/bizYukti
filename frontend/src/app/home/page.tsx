import type { Metadata } from 'next'
import { Suspense } from 'react'
import Home from '@/screens/home'

export const metadata: Metadata = { title: 'Home' }

export default function Page() {
  return <Suspense><Home /></Suspense>
}

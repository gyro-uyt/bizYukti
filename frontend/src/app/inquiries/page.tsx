import type { Metadata } from 'next'
import { Suspense } from 'react'
import Inquiries from '@/screens/inquiries'

export const metadata: Metadata = { title: 'Messages' }

export default function Page() {
  return <Suspense><Inquiries /></Suspense>
}

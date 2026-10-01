import type { Metadata } from 'next'
import { Suspense } from 'react'
import Notifications from '@/screens/notifications'

export const metadata: Metadata = { title: 'Notifications' }

export default function Page() {
  return <Suspense><Notifications /></Suspense>
}

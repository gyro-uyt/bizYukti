import type { Metadata } from 'next'
import { Suspense } from 'react'
import { RoleGate } from '@/components/role-gate'
import SavedScreen from '@/screens/saved'

export const metadata: Metadata = { title: 'Saved' }

export default function Page() {
  return <Suspense><RoleGate feature="saved"><SavedScreen /></RoleGate></Suspense>
}

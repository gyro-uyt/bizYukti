import type { Metadata } from 'next'
import { Suspense } from 'react'
import { RoleGate } from '@/components/role-gate'
import MapScreen from '@/screens/map'

export const metadata: Metadata = { title: 'Opportunity map' }

export default function Page() {
  return <Suspense><RoleGate feature="map"><MapScreen /></RoleGate></Suspense>
}

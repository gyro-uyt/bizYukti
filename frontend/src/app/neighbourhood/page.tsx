import type { Metadata } from 'next'
import { Suspense } from 'react'
import { RoleGate } from '@/components/role-gate'
import Neighbourhood from '@/screens/neighbourhood'

export const metadata: Metadata = { title: 'Neighbourhood map' }

export default function Page() {
  return <Suspense><RoleGate feature="neighbourhood"><Neighbourhood /></RoleGate></Suspense>
}

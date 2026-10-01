import type { Metadata } from 'next'
import { Suspense } from 'react'
import { RoleGate } from '@/components/role-gate'
import DemandNew from '@/screens/demand-new'

export const metadata: Metadata = { title: 'Request a business' }

export default function Page() {
  return <Suspense><RoleGate feature="demand.create"><DemandNew /></RoleGate></Suspense>
}

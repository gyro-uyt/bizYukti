import type { Metadata } from 'next'
import { Suspense } from 'react'
import { RoleGate } from '@/components/role-gate'
import Opportunity from '@/screens/opportunity'

export const metadata: Metadata = { title: 'Area opportunity' }

export default function Page() {
  return <Suspense><RoleGate feature="opportunities"><Opportunity /></RoleGate></Suspense>
}

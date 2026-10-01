import type { Metadata } from 'next'
import { Suspense } from 'react'
import { RoleGate } from '@/components/role-gate'
import PropertyForm from '@/screens/property-form'

export const metadata: Metadata = { title: 'List a space' }

export default function Page() {
  return <Suspense><RoleGate feature="property.create"><PropertyForm /></RoleGate></Suspense>
}

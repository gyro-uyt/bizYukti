import type { Metadata } from 'next'
import { Suspense } from 'react'
import { RoleGate } from '@/components/role-gate'
import Post from '@/screens/post'

export const metadata: Metadata = { title: 'Post' }

export default function Page() {
  return <Suspense><RoleGate feature="post"><Post /></RoleGate></Suspense>
}

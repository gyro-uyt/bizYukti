import type { Metadata } from 'next'
import { Suspense } from 'react'
import { InquiryThread } from '@/screens/inquiries'

export const metadata: Metadata = { title: 'Conversation' }

export default function Page() {
  return <Suspense><InquiryThread /></Suspense>
}

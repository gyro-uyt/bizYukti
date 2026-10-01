import type { Metadata } from 'next'
import { Suspense } from 'react'
import DemandDetail from '@/screens/demand-detail'

type Props = { params: Promise<{ id: string }> }

// Share previews: "184 residents support this" in the link card is what makes requests spread.
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params
  try {
    const r = await fetch(`${process.env.API_ORIGIN || 'http://localhost:8000'}/api/v1/demands/${id}`, { next: { revalidate: 300 } })
    if (r.ok) {
      const d = await r.json()
      const description = `${d.supporters} residents support this. Add your voice on BizYukti.`
      return { title: d.display_title, description, openGraph: { title: d.display_title, description } }
    }
  } catch {
    // API unreachable at render time: fall back to the generic title
  }
  return { title: 'Local request' }
}

export default function Page() {
  return <Suspense><DemandDetail /></Suspense>
}

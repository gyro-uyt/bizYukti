'use client'
import { useEffect } from 'react'
import { Button, Empty } from '@/components/ui'

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error) }, [error])
  return (
    <main className="container" style={{ paddingTop: 64 }}>
      <Empty title="Something went wrong" body="Please try again. If it keeps happening, reload the page."
        action={<Button onClick={reset}>Try again</Button>} />
    </main>
  )
}

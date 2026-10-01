import { AppShell } from '@/components/shell'
import { Empty, LinkButton } from '@/components/ui'

export default function NotFound() {
  return (
    <AppShell>
      <div className="container">
        <Empty title="We couldn't find that page" body="It may have been removed, or the link is incomplete."
          action={<LinkButton href="/explore">Explore your area</LinkButton>} />
      </div>
    </AppShell>
  )
}

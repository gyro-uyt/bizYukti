'use client'
import { useParams } from 'next/navigation'
import { AppShell } from '@/components/shell'
import { Notice, PageHeader } from '@/components/ui'

const DOCS: Record<string, { title: string; body: [string, string[]][] }> = {
  privacy: {
    title: 'Privacy policy',
    body: [
      ['What we collect', ['Your phone number or email, used only to sign you in and keep accounts genuine.', 'Your name, home locality (as a map point) and role.',
        'What you post: requests, support, listings, photos and messages.', 'Basic device and usage data, such as hashed network identifiers, to prevent abuse.']],
      ['How we use it', ['To count local demand fairly: support is counted only from verified residents within the local radius.',
        'To match spaces with demand and show businesses where to open.', 'To prevent fake demand, duplicate listings and reward farming.']],
      ['What others can see', ['Your first name and initial on requests you post. Never your phone number, email or exact home location.',
        'Listings show the area and photos. The exact address stays private unless you share it in a conversation.', 'Photos are re-saved without location metadata.']],
      ['Your rights', ['You can update your details from your profile at any time.', 'You can delete your account from your profile. Published requests then remain only as anonymous local demand.',
        'Contact the grievance officer at the address published on this site for access or correction requests.']],
    ],
  },
  terms: {
    title: 'Terms of use',
    body: [
      ['Using BizYukti', ['Post genuine local needs and real, available spaces only.', "Don't post contact details, links or advertising in requests.",
        'One account per person. Support from shared devices or far-away accounts is not counted.']],
      ['Listings and conversations', ['Owners are responsible for the accuracy of their listings and for keeping availability up to date.',
        'Any agreement between an owner and a business is made directly between them.']],
      ['Rewards', ['Points are earned only after the action is verified, and can be reversed if it fails review.', 'Points have no cash value and can be used only for the listed rewards.']],
      ['Moderation', ['We may remove content or suspend accounts that break these terms or the law.']],
    ],
  },
}

export default function Legal() {
  const { doc } = useParams<{ doc: string }>()
  const d = DOCS[doc] || DOCS.terms
  return (
    <AppShell>
      <div className="container prose">
        <PageHeader title={d.title} />
        <Notice tone="warn">Template text for the pilot. Have it reviewed by counsel (including against the Digital Personal Data Protection Act, 2023) before public launch.</Notice>
        {d.body.map(([h, items]) => (<section key={h} className="stack-sm"><h2 className="h2">{h}</h2><ul>{items.map((i) => <li key={i}>{i}</li>)}</ul></section>))}
      </div>
    </AppShell>
  )
}

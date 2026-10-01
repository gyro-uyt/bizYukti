import type { Metadata, Viewport } from 'next'
import type { ReactNode } from 'react'
import '@fontsource-variable/anek-latin/wdth.css'
import 'leaflet/dist/leaflet.css'
import './globals.css'
import { Providers } from './providers'

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'),
  title: { default: 'BizYukti: Demand. Space. Opportunity.', template: '%s | BizYukti' },
  description: 'Residents ask for the businesses their area needs, owners list empty spaces, and businesses see exactly where to open.',
  applicationName: 'BizYukti',
  openGraph: { siteName: 'BizYukti', type: 'website', locale: 'en_IN' },
}

export const viewport: Viewport = { themeColor: '#0004ED', width: 'device-width', initialScale: 1 }

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-IN">
      <body><Providers>{children}</Providers></body>
    </html>
  )
}

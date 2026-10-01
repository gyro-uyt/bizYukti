import type { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'BizYukti', short_name: 'BizYukti', start_url: '/home', display: 'standalone',
    description: 'Local demand, available space and business opportunity in one place.',
    background_color: '#F7FAFA', theme_color: '#0004ED',
    icons: [{ src: '/icon.svg', sizes: 'any', type: 'image/svg+xml' }],
  }
}

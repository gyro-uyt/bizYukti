import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return { rules: [{ userAgent: '*', allow: '/', disallow: ['/admin', '/inquiries', '/profile', '/notifications', '/saved', '/onboarding', '/rewards'] }] }
}

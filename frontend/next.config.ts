import type { NextConfig } from 'next'

// In development the web app proxies the API; in production Caddy routes /api and /media directly.
const api = process.env.API_ORIGIN || 'http://localhost:8000'

const config: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${api}/api/:path*` },
      { source: '/media/:path*', destination: `${api}/media/:path*` },
    ]
  },
  async headers() {
    return [{
      source: '/:path*',
      headers: [
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        { key: 'Permissions-Policy', value: 'geolocation=(self), camera=(self), microphone=()' },
        { key: 'X-Frame-Options', value: 'DENY' },
      ],
    }]
  },
}

export default config

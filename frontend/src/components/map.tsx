'use client'
import dynamic from 'next/dynamic'

export type { MapProps, Point, Zone } from './leaflet-map'

// Leaflet touches window, so it only ever loads in the browser.
export const MapView = dynamic(() => import('./leaflet-map'), {
  ssr: false,
  loading: () => <div className="map-skeleton" aria-label="Loading map" />,
})

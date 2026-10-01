'use client'
import L from 'leaflet'
import { Store } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

export interface Zone {
  id?: string; lat: number; lng: number; radius_m: number; intensity: number; label: string; tone?: 'demand' | 'blue' | 'green'; onClick?: () => void
  /** Explicit colour (e.g. a category family); overrides `tone`. */
  color?: string
  /** HTML for a badge pinned at the zone centre (category icon + count). */
  badgeHtml?: string
  /** Pixel offset for the badge, so badges of zones sharing a centre sit side by side. */
  badgeOffset?: [number, number]
  selected?: boolean
}
export interface Point { id: string; lat: number; lng: number; label: string; kind: 'space' | 'demand' | 'area' | 'me'; selected?: boolean; onClick?: () => void }
export interface MapProps {
  center: { lat: number; lng: number }
  zoom?: number
  zones?: Zone[]
  points?: Point[]
  pin?: { lat: number; lng: number } | null
  onPinChange?: (p: { lat: number; lng: number }) => void
  height?: number | string
  fitKey?: string
  ariaLabel?: string
}

const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTR = process.env.NEXT_PUBLIC_MAP_ATTRIBUTION || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const COLORS = { demand: ['#C80F48', '#FB2462'], blue: ['#0004ED', '#0004ED'], green: ['#1E7A00', '#7AF444'] } as const
// Stick figure (lucide "person-standing") for the "you are here" marker.
export const PERSON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
  + '<circle cx="12" cy="5" r="1"/><path d="m9 20 3-6 3 6"/><path d="m6 8 6 2 6-2"/><path d="M12 10v4"/></svg>'
// Vacant space marker: a shopfront glyph on an orange tile (a different shape from round demand zones).
const STORE_SVG = renderToStaticMarkup(<Store size={16} strokeWidth={2.4} aria-hidden />)

export default function LeafletMap({ center, zoom = 14, zones, points, pin, onPinChange, height = 360, fitKey, ariaLabel }: MapProps) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const pinRef = useRef<L.Marker | null>(null)
  const lastFit = useRef<string | undefined>(undefined)
  const onPin = useRef(onPinChange)
  onPin.current = onPinChange

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { center: [center.lat, center.lng], zoom, scrollWheelZoom: true })
    L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 19 }).addTo(m)
    layer.current = L.layerGroup().addTo(m)
    m.on('click', (e: L.LeafletMouseEvent) => onPin.current?.({ lat: e.latlng.lat, lng: e.latlng.lng }))
    map.current = m
    const t = setTimeout(() => m.invalidateSize(), 60)
    return () => { clearTimeout(t); m.remove(); map.current = null; pinRef.current = null; layer.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const m = map.current
    if (m) m.setView([center.lat, center.lng], m.getZoom(), { animate: true })
  }, [center.lat, center.lng])

  useEffect(() => {
    const g = layer.current
    const m = map.current
    if (!g || !m) return
    g.clearLayers()
    const bounds: [number, number][] = []
    ;(zones || []).forEach((z) => {
      const [stroke, fill] = z.color ? [z.color, z.color] : COLORS[z.tone || 'demand']
      const c = L.circle([z.lat, z.lng], {
        radius: z.radius_m, color: stroke, weight: z.selected ? 3 : 1.5, opacity: z.selected ? 1 : 0.9,
        fillColor: fill, fillOpacity: (z.color ? 0.1 : 0.12) + z.intensity * (z.color ? 0.22 : 0.32),
      })
      c.bindTooltip(z.label)
      if (z.onClick) c.on('click', z.onClick)
      c.addTo(g)
      if (z.badgeHtml) {
        const badge = L.marker([z.lat, z.lng], {
          icon: L.divIcon({ className: '', iconSize: [0, 0], iconAnchor: [0, 0],
            html: `<span class="zone-badge${z.selected ? ' is-selected' : ''}" style="--zc:${stroke};--dx:${z.badgeOffset?.[0] ?? 0}px;--dy:${z.badgeOffset?.[1] ?? 0}px">${z.badgeHtml}</span>` }),
          title: z.label, alt: z.label, keyboard: true, riseOnHover: true, zIndexOffset: z.selected ? 900 : 500,
        })
        badge.bindTooltip(z.label)
        if (z.onClick) badge.on('click', z.onClick)
        badge.addTo(g)
      }
      bounds.push([z.lat, z.lng])
    })
    ;(points || []).forEach((p) => {
      const me = p.kind === 'me'
      const icon = me
        ? L.divIcon({ className: '', html: `<span class="pin-me">${PERSON_SVG}</span>`, iconSize: [34, 34], iconAnchor: [17, 17] })
        : p.kind === 'space'
          ? L.divIcon({ className: '', html: `<span class="pin-store${p.selected ? ' is-selected' : ''}">${STORE_SVG}</span>`, iconSize: [26, 26], iconAnchor: [13, 13] })
          : L.divIcon({ className: '', html: `<span class="pin pin-${p.kind}${p.selected ? ' is-selected' : ''}"></span>`, iconSize: [22, 22], iconAnchor: [11, 11] })
      const mk = L.marker([p.lat, p.lng], { icon, title: p.label, alt: p.label, keyboard: true, riseOnHover: true, zIndexOffset: me ? 1000 : p.selected ? 950 : 300 })
      mk.bindTooltip(p.label)
      if (p.onClick) mk.on('click', p.onClick)
      mk.addTo(g)
      bounds.push([p.lat, p.lng])
    })
    if (fitKey && fitKey !== lastFit.current && bounds.length > 1) {
      lastFit.current = fitKey
      m.fitBounds(L.latLngBounds(bounds).pad(0.12), { maxZoom: 15 })
    }
  }, [zones, points, fitKey])

  useEffect(() => {
    const m = map.current
    if (!m) return
    if (!pin) { pinRef.current?.remove(); pinRef.current = null; return }
    if (!pinRef.current) {
      const icon = L.divIcon({ className: '', html: '<span class="drop-pin"></span>', iconSize: [30, 40], iconAnchor: [15, 38] })
      const mk = L.marker([pin.lat, pin.lng], { icon, draggable: true, keyboard: true, title: 'Selected location. Drag to adjust', alt: 'Selected location', autoPan: true })
      mk.on('dragend', () => { const ll = mk.getLatLng(); onPin.current?.({ lat: ll.lat, lng: ll.lng }) })
      mk.addTo(m)
      pinRef.current = mk
    } else {
      pinRef.current.setLatLng([pin.lat, pin.lng])
    }
  }, [pin?.lat, pin?.lng, pin])

  return <div ref={el} className="map" style={{ height }} role="region" aria-label={ariaLabel || 'Map'} />
}

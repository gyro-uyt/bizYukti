// Usage example for the orbiting carousel (not routed; the live use is the Explore "Spotlight" tab).
import { Coffee, Dumbbell, Pill } from 'lucide-react'
import OrbitCarousel, { type OrbitItem } from '@/components/ui/orbiting-carousel-with-animated-icons'

const items: OrbitItem[] = [
  { id: '1', title: 'Pharmacy', subtitle: 'Gol Pahadiya', href: '/explore', icon: Pill, tone: 'green', stat: '183', statLabel: 'supporters' },
  { id: '2', title: 'Gym', subtitle: 'Phool Bagh', href: '/explore', icon: Dumbbell, tone: 'pink', image: '/categories/gym.webp' },
  { id: '3', title: 'Café', subtitle: 'City Centre', href: '/explore', icon: Coffee, tone: 'orange', image: '/categories/coworking.webp' },
]

export default function DemoOne() {
  return <OrbitCarousel items={items} label="Example carousel" />
}

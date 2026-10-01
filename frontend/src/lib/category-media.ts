// Imagery for business categories: a real photo where we have one, otherwise an icon on a tinted circle.
import {
  Baby, BookOpen, Coffee, Croissant, Dumbbell, GraduationCap, Landmark, Laptop, Microscope, PawPrint, Pill, Scissors,
  Shirt, ShoppingBasket, Smartphone, Stethoscope, Store, Trophy, Truck, UtensilsCrossed, Wrench, type LucideIcon,
} from 'lucide-react'

export type CategoryTone = 'pink' | 'orange' | 'blue' | 'green'

export const CATEGORY_PHOTOS: Record<string, string> = {
  coworking: '/categories/coworking.webp', cafe: '/categories/coworking.webp',
  grocery: '/categories/grocery.webp', delivery_hub: '/categories/grocery.webp',
  gym: '/categories/gym.webp', sports: '/categories/gym.webp',
  bakery: '/categories/bakery.webp',
  bank_atm: '/categories/atm.webp',
  pharmacy: '/categories/pharmacy.webp',
  clinic: '/categories/clinic.webp', diagnostics: '/categories/clinic.webp',
  coaching: '/categories/coaching.webp',
  bookstore: '/categories/bookstore.webp',
  salon: '/categories/salon.webp',
  hardware: '/categories/hardware.webp',
  restaurant: '/categories/restaurant.webp', // Unsplash photo-1552566626-52f8b828add9 (Unsplash License)
}

const ICONS: Record<string, [LucideIcon, CategoryTone]> = {
  pharmacy: [Pill, 'green'], clinic: [Stethoscope, 'green'], diagnostics: [Microscope, 'green'], pet_care: [PawPrint, 'green'],
  grocery: [ShoppingBasket, 'orange'], cafe: [Coffee, 'orange'], restaurant: [UtensilsCrossed, 'orange'], bakery: [Croissant, 'orange'],
  gym: [Dumbbell, 'pink'], salon: [Scissors, 'pink'], sports: [Trophy, 'pink'], laundry: [Shirt, 'pink'],
  coaching: [GraduationCap, 'blue'], daycare: [Baby, 'blue'], bookstore: [BookOpen, 'blue'], coworking: [Laptop, 'blue'],
  hardware: [Wrench, 'orange'], electronics: [Smartphone, 'blue'], bank_atm: [Landmark, 'blue'], delivery_hub: [Truck, 'orange'],
}

export function categoryIcon(slug: string): { icon: LucideIcon; tone: CategoryTone } {
  const [icon, tone] = ICONS[slug] || [Store, 'pink']
  return { icon, tone }
}

// Map colour families for demand zones. Zones can sit beside any other zone, so the hues were checked
// all-pairs for colour-blind separation (dataviz validator: CVD ΔE ≥ 10.7, normal ≥ 18.7, together with
// SPACE_COLOR). Each zone also shows its category icon and count, so colour is never the only cue.
export type DemandGroup = { key: string; label: string; color: string }
export const DEMAND_GROUPS: DemandGroup[] = [
  { key: 'daily', label: 'Food and daily needs', color: '#c80f48' },
  { key: 'health', label: 'Health and care', color: '#1baf7a' },
  { key: 'lifestyle', label: 'Learning, fitness and lifestyle', color: '#2a78d6' },
  { key: 'other', label: 'Other shops and services', color: '#7c858a' },
]
export const SPACE_COLOR = '#e8701a'
const GROUP_OF: Record<string, string> = {
  grocery: 'daily', bakery: 'daily', cafe: 'daily', restaurant: 'daily', delivery_hub: 'daily', laundry: 'daily', bank_atm: 'daily',
  pharmacy: 'health', clinic: 'health', diagnostics: 'health', pet_care: 'health', daycare: 'health',
  gym: 'lifestyle', salon: 'lifestyle', sports: 'lifestyle', coaching: 'lifestyle', bookstore: 'lifestyle', coworking: 'lifestyle',
}

export function demandGroup(slug: string): DemandGroup {
  return DEMAND_GROUPS.find((g) => g.key === (GROUP_OF[slug] || 'other')) as DemandGroup
}

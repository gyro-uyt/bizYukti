// Which features each role's view shows. Driven by the active role (switched from the profile),
// matching how /home picks the resident, owner or business screen. Signed-out visitors and the
// admin view see everything, as before.
import type { Me, Role } from './types'

export type Feature =
  | 'explore' | 'map' | 'post' | 'saved' | 'opportunities'
  | 'explore.requests' | 'explore.spaces' | 'explore.areas'
  | 'saved.requests' | 'saved.spaces' | 'saved.areas'
  | 'demand.create' | 'property.create' | 'neighbourhood' | 'rewards.topbar' | 'activity' | 'assistant' | 'reports'

// Role-specific variants of shared features (e.g. the resident's own map instead of the opportunity
// map). The admin and signed-out views keep the general version, so these are never granted to them.
const EXCLUSIVE: readonly Feature[] = ['neighbourhood', 'rewards.topbar', 'activity', 'assistant', 'reports']

const ACCESS: Record<Exclude<Role, 'admin'>, readonly Feature[]> = {
  // R1-R4: ask for businesses, back neighbours' requests, see them on a map, track them, earn rewards
  resident: ['explore', 'explore.requests', 'post', 'demand.create', 'neighbourhood', 'rewards.topbar', 'activity', 'assistant'],
  // P1-P3: list spaces and see the local demand they fit
  owner: ['explore', 'explore.requests', 'post', 'property.create'],
  // B1-B3: rank areas, compare spaces, use the opportunity map, save areas
  business: ['explore', 'explore.requests', 'explore.spaces', 'explore.areas', 'map', 'opportunities',
    'saved', 'saved.areas', 'saved.spaces', 'saved.requests', 'reports'],
}

export function canUse(user: Me | null | undefined, feature: Feature): boolean {
  if (!user || user.active_role === 'admin') return !EXCLUSIVE.includes(feature)
  return (ACCESS[user.active_role] ?? []).includes(feature)
}

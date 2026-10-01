export type Role = 'resident' | 'owner' | 'business' | 'admin'

export interface Home { lat: number; lng: number; label: string | null; area_id: string | null }

export interface Business {
  id: string; name: string; categories: string[]; preferred_cities: string[]
  budget_min: number | null; budget_max: number | null; size_min_sqft: number | null; size_max_sqft: number | null
  registration_id: string | null; website: string | null; verification_status: string; verified: boolean
}

export interface Me {
  id: string; name: string | null; display_name: string; email: string | null; phone: string | null
  roles: Role[]; active_role: Role; onboarded: boolean; home: Home | null; business: Business | null
  unread_notifications?: number; unread_messages?: number
}

export interface Demand {
  id: string; title: string; description: string | null; display_title: string; category: string; category_name: string
  reason: string; reason_label: string; reason_note: string | null; why: string; lat: number; lng: number
  locality: string; area_id: string | null; status: string; verification_status: string; verified: boolean
  supporters: number; pending_supporters: number; views: number; shares: number; distance_m: number | null
  my_support: string | null; mine: boolean; interested: boolean | null; author: { name: string } | null
  created_at: string; published_at: string | null; fulfilled_at: string | null; matched_spaces?: number
}

export interface Media { id: string; url: string; thumb_url: string; width: number; height: number; is_blurry: boolean; is_duplicate: boolean }

export interface TopDemand { category: string; category_name: string; supporters: number; score: number; demand_id: string; match_id: string }

export interface Space {
  id: string; title: string | null; display_title: string; type: string; type_label: string
  size_value: number | null; size_unit: string; size_sqft: number | null
  price_type: string; price_amount: number | null; price_negotiable: boolean
  availability: string; available_from: string | null; lat: number | null; lng: number | null
  locality: string | null; area_id: string | null; description: string | null; amenities: string[]; amenity_labels: string[]
  status: string; verification_status: string; verified: boolean; verification_level: string; recently_updated: boolean
  media: Media[]; cover_url: string | null; distance_m: number | null; owner: { name: string } | null
  last_confirmed_at: string | null; published_at: string | null; created_at: string
  address?: string | null; quality_score?: number; quality_flags?: string[]; views?: number
  matches?: number; top_demand?: TopDemand | null; demand?: { count: number; top: TopDemand | null } | null
  fit?: number; availability_text?: string
}

export interface MatchItem {
  id: string; score: number; distance_m: number; status: string; summary: string; reasons: string[]
  cluster_supporters: number | null; demand: Demand | null; property: Space | null; updated_at: string
  fit_label?: string; density?: { label: string; supporters: number; radius_m: number }; interested_businesses?: number
}

export interface AreaRef { id: string; name: string; city: string; lat: number; lng: number; radius_m: number; slug?: string }

export interface AreaOpp {
  area: AreaRef; category: string; category_name: string; label: string; tone: 'strong' | 'promising' | 'early'
  score: number; supporters: number; demands: number; spaces: number; competitors: number
  trend: { direction: string; change_pct: number; text: string }
  access: { transit: string; road: string | null; footfall_index: number; notes: string | null }
  reasons: string[]; saved?: boolean
}

export interface Category { slug: string; name: string; noun: string; why: string; types: string[]; size_min: number; size_max: number }

export interface AppConfig {
  app_name: string; default_city: string; default_center: { lat: number; lng: number }; cities: string[]
  reasons: { slug: string; label: string }[]; property_types: { slug: string; label: string }[]
  amenities: { slug: string; label: string }[]
  rewards: { demand_max_points: number; tiers: { name: string; at: number }[] }
  trust: { local_radius_km: number; verify_min_supporters: number; growing_threshold: number }
}

export interface Message { id: string; body: string; mine: boolean; created_at: string; sender: string }

export interface Inquiry {
  id: string; kind: string; subject: string; status: string; direction: 'sent' | 'received'; with: { name: string }
  property_id: string | null; demand_id: string | null; area_id: string | null; category: string | null
  unread: number; last_message: string | null; last_message_at: string; created_at: string
  context: { property?: { id: string; title: string; cover_url: string | null; locality: string | null };
             demand?: { id: string; title: string; supporters: number }; area?: { id: string; name: string; city: string } }
  messages?: Message[]
}

export interface Paged<T> { total: number; center?: { lat: number; lng: number }; items: T[] }

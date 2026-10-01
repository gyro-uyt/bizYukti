"""Response shapes. Contact details (phone/email) never leave the API except to their owner;
people reach each other through in-app inquiries."""

from datetime import date, datetime

from . import taxonomy
from .models import BusinessProfile, Demand, Inquiry, Match, OpportunityArea, Property, PropertyMedia, User
from .security import display_name
from .services.media import is_recently_updated
from .storage import public_url


def iso(v: datetime | date | None) -> str | None:
    return v.isoformat() if v else None


def user_private(u: User, business: BusinessProfile | None = None) -> dict:
    return {
        "id": str(u.id), "name": u.name, "display_name": display_name(u), "email": u.email, "phone": u.phone,
        "roles": u.role_names, "active_role": u.active_role, "onboarded": u.onboarded,
        "home": {"lat": u.home_lat, "lng": u.home_lng, "label": u.home_label,
                 "area_id": str(u.home_area_id) if u.home_area_id else None} if u.home_lat is not None else None,
        "business": business_out(business) if business else None,
        "created_at": iso(u.created_at),
    }


def business_out(b: BusinessProfile) -> dict:
    return {
        "id": str(b.id), "name": b.name, "categories": b.categories or [], "preferred_cities": b.preferred_cities or [],
        "budget_min": b.budget_min, "budget_max": b.budget_max, "size_min_sqft": b.size_min_sqft,
        "size_max_sqft": b.size_max_sqft, "registration_id": b.registration_id, "website": b.website,
        "verification_status": b.verification_status, "verified": b.verification_status == "verified",
    }


def area_out(a: OpportunityArea) -> dict:
    return {"id": str(a.id), "slug": a.slug, "name": a.name, "city": a.city, "lat": a.lat, "lng": a.lng,
            "radius_m": a.radius_m}


def demand_out(d: Demand, *, distance_m: float | None = None, my_support: str | None = None,
               author: User | None = None, mine: bool = False, interested: bool | None = None) -> dict:
    cat = taxonomy.get(d.category)
    return {
        "id": str(d.id), "title": d.title, "description": d.description,
        "display_title": f"{d.title} near {d.locality}",
        "category": d.category, "category_name": cat.name, "tags": d.tags or [],
        "reason": d.reason, "reason_label": taxonomy.REASONS.get(d.reason, "Other"), "reason_note": d.reason_note,
        "why": d.reason_note or cat.why,
        "lat": d.lat, "lng": d.lng, "locality": d.locality, "area_id": str(d.area_id) if d.area_id else None,
        "status": d.status, "verification_status": d.verification_status,
        "verified": d.verification_status == "verified",
        "supporters": d.verified_support_count, "pending_supporters": d.pending_support_count,
        "views": d.view_count, "shares": d.share_count,
        "distance_m": round(distance_m) if distance_m is not None else None,
        "my_support": my_support, "mine": mine, "interested": interested,
        "author": {"name": display_name(author)} if author else None,
        "created_at": iso(d.created_at), "published_at": iso(d.published_at), "fulfilled_at": iso(d.fulfilled_at),
    }


def media_out(m: PropertyMedia) -> dict:
    return {"id": str(m.id), "url": public_url(m.storage_key), "thumb_url": public_url(m.thumb_key),
            "width": m.width, "height": m.height, "is_blurry": m.is_blurry, "is_duplicate": m.is_duplicate}


def property_out(p: Property, *, distance_m: float | None = None, private: bool = False,
                 owner: User | None = None) -> dict:
    kind = taxonomy.PROPERTY_TYPES.get(p.type, "space")
    size = f"{p.size_sqft:,.0f} sq ft " if p.size_sqft else ""
    media = [media_out(m) for m in p.media]
    cover = next((m for m in media if not m["is_duplicate"]), media[0] if media else None)
    out = {
        "id": str(p.id), "title": p.title, "display_title": p.title or f"{size}{kind}".strip().capitalize(),
        "type": p.type, "type_label": kind,
        "size_value": p.size_value, "size_unit": p.size_unit, "size_sqft": p.size_sqft,
        "price_type": p.price_type, "price_amount": p.price_amount, "price_negotiable": p.price_negotiable,
        "availability": p.availability, "available_from": iso(p.available_from),
        "lat": p.lat, "lng": p.lng, "locality": p.locality, "area_id": str(p.area_id) if p.area_id else None,
        "description": p.description, "amenities": p.amenities or [],
        "amenity_labels": [taxonomy.AMENITIES.get(a, a) for a in (p.amenities or [])],
        "status": p.status, "verification_status": p.verification_status,
        "verified": p.verification_status == "verified", "verification_level": p.verification_level,
        "recently_updated": is_recently_updated(p),
        "media": media, "cover_url": cover["thumb_url"] if cover else None,
        "distance_m": round(distance_m) if distance_m is not None else None,
        "owner": {"name": display_name(owner)} if owner else None,
        "last_confirmed_at": iso(p.last_confirmed_at), "published_at": iso(p.published_at),
        "created_at": iso(p.created_at),
    }
    if private:
        out.update(address=p.address, quality_score=p.quality_score, quality_flags=p.quality_flags or [],
                   views=p.view_count)
    return out


def match_out(m: Match, demand: Demand | None = None, prop: Property | None = None) -> dict:
    return {
        "id": str(m.id), "score": m.score, "distance_m": round(m.distance_m), "status": m.status,
        "summary": (m.reasons or [""])[0], "reasons": (m.reasons or [])[1:],
        "cluster_supporters": (m.components or {}).get("cluster_supporters"),
        "demand": demand_out(demand) if demand else None,
        "property": property_out(prop) if prop else None,
        "updated_at": iso(m.updated_at),
    }


def inquiry_out(i: Inquiry, me: User, people: dict, context: dict | None = None) -> dict:
    other_id = i.to_user_id if i.from_user_id == me.id else i.from_user_id
    other = people.get(other_id)
    unread = sum(1 for m in i.messages if m.sender_id != me.id and m.read_at is None)
    last = i.messages[-1] if i.messages else None
    return {
        "id": str(i.id), "kind": i.kind, "subject": i.subject, "status": i.status,
        "direction": "sent" if i.from_user_id == me.id else "received",
        "with": {"name": display_name(other) if other else "BizYukti team"},
        "property_id": str(i.property_id) if i.property_id else None,
        "demand_id": str(i.demand_id) if i.demand_id else None,
        "area_id": str(i.area_id) if i.area_id else None, "category": i.category,
        "unread": unread, "last_message": last.body[:140] if last else None,
        "last_message_at": iso(i.last_message_at), "created_at": iso(i.created_at),
        "context": context or {},
    }

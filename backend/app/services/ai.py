"""Optional intelligence providers. Everything here degrades gracefully to deterministic
logic, so the product never depends on a model being reachable."""

import json
import logging

import httpx

from .. import taxonomy
from ..config import settings

log = logging.getLogger("bizyukti.ai")


def _llm_categorize(text: str) -> tuple[str, list[str]] | None:
    slugs = ", ".join(c.slug for c in taxonomy.CATEGORIES)
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": settings.llm_model,
                "max_tokens": 120,
                "system": "You classify short local business requests from Indian neighbourhoods. "
                          "Reply with JSON only, no prose: {\"category\": <slug>, \"tags\": [<up to 4 short lowercase tags>]}. "
                          f"Allowed slugs: {slugs}.",
                "messages": [{"role": "user", "content": text[:500]}],
            },
            timeout=8,
        )
        r.raise_for_status()
        raw = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        data = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        slug = data.get("category")
        if slug in taxonomy.BY_SLUG:
            tags = [str(t)[:40].lower() for t in data.get("tags", [])][:4]
            return slug, tags
    except Exception as exc:
        log.warning("LLM categorisation unavailable: %s", exc)
    return None


def categorize(text: str) -> dict:
    slug, confidence, hits = taxonomy.classify(text)
    result = {"category": slug, "confidence": confidence, "tags": hits, "source": "rules"}
    if confidence < 0.6 and settings.anthropic_api_key:
        llm = _llm_categorize(text)
        if llm:
            result.update(category=llm[0], tags=llm[1] or hits, confidence=0.8, source="llm")
    return result


def embed(text: str) -> list[float] | None:
    if not (settings.embeddings_url and settings.embeddings_model):
        return None
    try:
        r = httpx.post(settings.embeddings_url, json={"input": [text[:2000]], "model": settings.embeddings_model},
                       headers={"Authorization": f"Bearer {settings.embeddings_api_key}"}, timeout=8)
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception as exc:
        log.warning("embedding unavailable: %s", exc)
        return None

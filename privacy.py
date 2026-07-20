"""
Location and field privacy helpers for public surfaces (Nearby, public profile).

Hybrid approach:
- Deterministic Gaussian noise on lat/lon (stable per entity + day + level)
- Address coarsening by privacy level
- Optional light free-text redaction for public service snippets (regex, no LLM required)

Privacy levels: precise | neighborhood | city | hidden
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from typing import Any, Dict, Optional, Tuple

PRIVACY_LEVELS = ("precise", "neighborhood", "city", "hidden")
DEFAULT_PUBLIC_PRIVACY = "neighborhood"

# Approximate meters of Gaussian noise (σ) per public level
_SIGMA_METERS = {
    "precise": 0.0,
    "neighborhood": 150.0,
    "city": 2500.0,
    "hidden": 0.0,  # coords omitted
}


def normalize_privacy_level(level: Optional[str]) -> str:
    if not level:
        return DEFAULT_PUBLIC_PRIVACY
    level = str(level).strip().lower()
    if level not in PRIVACY_LEVELS:
        return DEFAULT_PUBLIC_PRIVACY
    return level


def _stable_rng(seed_parts: Tuple[Any, ...]) -> random.Random:
    raw = "|".join(str(p) for p in seed_parts).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return random.Random(int(digest[:16], 16))


def day_bucket(ts: Optional[float] = None) -> int:
    import time
    t = int(ts if ts is not None else time.time())
    return t // 86400


def noisy_lat_lon(
    lat: float,
    lon: float,
    level: str,
    *,
    entity_id: str = "",
    day: Optional[int] = None,
) -> Optional[Tuple[float, float]]:
    """
    Apply small Gaussian noise in meters, converted to degrees.
    Returns None when level is hidden (omit public coordinates).
    """
    level = normalize_privacy_level(level)
    if level == "hidden":
        return None
    sigma = _SIGMA_METERS.get(level, _SIGMA_METERS[DEFAULT_PUBLIC_PRIVACY])
    if sigma <= 0:
        return float(lat), float(lon)

    rng = _stable_rng((entity_id, level, day if day is not None else day_bucket()))
    # Independent Gaussian in meters
    north_m = rng.gauss(0.0, sigma)
    east_m = rng.gauss(0.0, sigma)
    dlat = north_m / 111_320.0
    cos_lat = math.cos(math.radians(lat))
    # Avoid division by zero near poles
    dlon = east_m / (111_320.0 * cos_lat) if abs(cos_lat) > 1e-6 else 0.0
    return lat + dlat, lon + dlon


def coarsen_address(address: Optional[str], level: str) -> Optional[str]:
    """Reduce free-text address precision for public surfaces."""
    if not address:
        return None
    level = normalize_privacy_level(level)
    text = str(address).strip()
    if not text:
        return None
    if level == "precise":
        return text
    if level == "hidden":
        return None

    parts = [p.strip() for p in text.split(",") if p.strip()]
    if level == "city":
        if len(parts) >= 2:
            return ", ".join(parts[-2:])
        # Single field: drop leading house number if present
        return re.sub(r"^\d+\s+", "", parts[0]) if parts else None

    # neighborhood: drop leading house numbers; keep area/street name + locality
    def _strip_num(p: str) -> str:
        return re.sub(r"^\d+[A-Za-z]?\s+", "", p).strip() or p

    if len(parts) >= 3:
        head = _strip_num(parts[0])
        return ", ".join([head] + parts[1:])
    if len(parts) == 2:
        return ", ".join([_strip_num(parts[0]), parts[1]])
    return _strip_num(parts[0]) if parts else None


_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\w)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact_public_text(text: Optional[str], level: str) -> Optional[str]:
    """Lightweight public text cloaking (phones/emails/SSN)."""
    if text is None:
        return None
    level = normalize_privacy_level(level)
    s = str(text)
    if level == "precise":
        return s
    s = _SSN_RE.sub("[redacted]", s)
    s = _EMAIL_RE.sub("[email]", s)
    s = _PHONE_RE.sub("[phone]", s)
    if level in ("city", "hidden"):
        # Drop very long trailing free-form detail
        if len(s) > 280:
            s = s[:277] + "…"
    if level == "hidden":
        # Category-ish: first clause only
        for sep in (".", "—", "-", "\n"):
            if sep in s:
                s = s.split(sep)[0].strip()
                break
        if len(s) > 80:
            s = s[:77] + "…"
    return s


def project_nearby_service(bid: Dict[str, Any], distance: float) -> Dict[str, Any]:
    """Public Nearby card projection for one bid."""
    level = normalize_privacy_level(bid.get("privacy_level") or DEFAULT_PUBLIC_PRIVACY)
    entity_id = str(bid.get("bid_id") or bid.get("id") or "")
    lat, lon = bid.get("lat"), bid.get("lon")
    public_coords = None
    if lat is not None and lon is not None:
        public_coords = noisy_lat_lon(float(lat), float(lon), level, entity_id=entity_id)

    service = bid.get("service")
    if isinstance(service, dict):
        service = service.get("description") or str(service)
    service_text = redact_public_text(service, level)

    out: Dict[str, Any] = {
        "bid_id": bid.get("bid_id"),
        "service": service_text,
        "price": bid.get("price"),
        "currency": bid.get("currency", "USD"),
        "distance": round(distance, 2),
        "address": coarsen_address(bid.get("address"), level),
        "buyer_reputation": bid.get("buyer_reputation", 2.5),
        "privacy_level": level,
    }
    if public_coords is not None:
        out["lat"] = round(public_coords[0], 5)
        out["lon"] = round(public_coords[1], 5)
    return out


def project_public_location_field(location: Optional[str], level: str) -> Optional[str]:
    return coarsen_address(location, level) if location else None

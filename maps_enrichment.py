"""
Optional location enrichment for /nearby.

Builds deep-links and light metadata from public map providers. API keys are
optional; without keys we still return usable open URLs and OpenStreetMap /
Nominatim / Mapbox (if token present) enrichment.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

UA = "RSE-NearbyMaps/1.0 (+https://therobotservicesexchange.com)"


def _cfg(name: str, default: str = "") -> str:
    try:
        import config as cfg

        return str(getattr(cfg, name, None) or os.environ.get(name, default) or default)
    except Exception:
        return str(os.environ.get(name, default) or default)


def _http_json(url: str, timeout: float = 6.0) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        logger.debug("maps_enrichment fetch failed %s: %s", url[:80], e)
        return None


def deep_links(lat: float, lon: float, label: str = "Nearby") -> Dict[str, str]:
    """Static deep links that never require server-side API keys."""
    q = urllib.parse.quote(label)
    lat_s, lon_s = f"{lat:.6f}", f"{lon:.6f}"
    return {
        "google_maps": f"https://www.google.com/maps/search/?api=1&query={lat_s},{lon_s}",
        "apple_maps": f"https://maps.apple.com/?ll={lat_s},{lon_s}&q={q}",
        "bing_maps": f"https://www.bing.com/maps?cp={lat_s}~{lon_s}&lvl=14&sp=point.{lat_s}_{lon_s}_{q}",
        "yahoo_maps": f"https://maps.yahoo.com/?lat={lat_s}&lon={lon_s}&zoom=14",
        "openstreetmap": f"https://www.openstreetmap.org/?mlat={lat_s}&mlon={lon_s}#map=14/{lat_s}/{lon_s}",
        "mapbox": f"https://www.mapbox.com/maps/?lat={lat_s}&lng={lon_s}&zoom=13",
        "geo_uri": f"geo:{lat_s},{lon_s}?q={lat_s},{lon_s}({q})",
    }


def reverse_geocode_nominatim(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        + urllib.parse.urlencode(
            {
                "lat": f"{lat:.6f}",
                "lon": f"{lon:.6f}",
                "format": "jsonv2",
                "zoom": 14,
                "addressdetails": 1,
            }
        )
    )
    data = _http_json(url)
    if not isinstance(data, dict):
        return None
    addr = data.get("address") or {}
    return {
        "provider": "openstreetmap_nominatim",
        "display_name": data.get("display_name"),
        "city": addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet"),
        "state": addr.get("state"),
        "country": addr.get("country"),
        "postcode": addr.get("postcode"),
        "neighbourhood": addr.get("neighbourhood") or addr.get("suburb"),
    }


def reverse_geocode_mapbox(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    token = _cfg("MAPBOX_ACCESS_TOKEN") or _cfg("MAPBOX_TOKEN")
    if not token:
        return None
    url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon:.6f},{lat:.6f}.json?"
        + urllib.parse.urlencode({"access_token": token, "limit": 1})
    )
    data = _http_json(url)
    if not isinstance(data, dict):
        return None
    feats = data.get("features") or []
    if not feats:
        return None
    f0 = feats[0]
    ctx = {c.get("id", "").split(".")[0]: c.get("text") for c in (f0.get("context") or []) if c.get("id")}
    return {
        "provider": "mapbox",
        "display_name": f0.get("place_name"),
        "city": ctx.get("place") or ctx.get("locality"),
        "state": ctx.get("region"),
        "country": ctx.get("country"),
        "postcode": ctx.get("postcode"),
        "neighbourhood": ctx.get("neighborhood") or ctx.get("locality"),
    }


def places_overpass(lat: float, lon: float, radius_m: int = 2500, limit: int = 12) -> List[Dict[str, Any]]:
    """Lightweight nearby POIs via Overpass (no key)."""
    # Keep query small for latency
    query = f"""
    [out:json][timeout:8];
    (
      node(around:{radius_m},{lat:.5f},{lon:.5f})[amenity~"cafe|restaurant|charging_station|fuel|library|community_centre"];
      node(around:{radius_m},{lat:.5f},{lon:.5f})[shop~"convenience|supermarket"];
      node(around:{radius_m},{lat:.5f},{lon:.5f})[tourism~"attraction|museum"];
    );
    out body {limit};
    """
    url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(query)
    data = _http_json(url, timeout=10.0)
    if not isinstance(data, dict):
        return []
    out: List[Dict[str, Any]] = []
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        kind = (
            tags.get("amenity")
            or tags.get("shop")
            or tags.get("tourism")
            or "place"
        )
        out.append(
            {
                "name": name,
                "kind": kind,
                "lat": el.get("lat"),
                "lon": el.get("lon"),
                "source": "openstreetmap_overpass",
            }
        )
        if len(out) >= limit:
            break
    return out


def map_display_payload(lat: float, lon: float, zoom: int = 12) -> Dict[str, Any]:
    """Client-ready map hints (embed/static links where free)."""
    token = _cfg("MAPBOX_ACCESS_TOKEN") or _cfg("MAPBOX_TOKEN")
    lat_s, lon_s = f"{lat:.5f}", f"{lon:.5f}"
    static = None
    if token:
        static = (
            f"https://api.mapbox.com/styles/v1/mapbox/dark-v11/static/"
            f"pin-s+00ffff({lon_s},{lat_s})/{lon_s},{lat_s},{zoom},0/800x450@2x"
            f"?access_token={token}"
        )
    return {
        "center": {"lat": lat, "lon": lon},
        "zoom": zoom,
        "style_suggestions": [
            "mapbox://styles/mapbox/dark-v11",
            "mapbox://styles/mapbox/streets-v12",
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        ],
        "static_map_url": static,
        "openstreetmap_embed": (
            f"https://www.openstreetmap.org/export/embed.html?"
            f"bbox={float(lon)-0.05}%2C{float(lat)-0.03}%2C{float(lon)+0.05}%2C{float(lat)+0.03}"
            f"&layer=mapnik&marker={lat_s}%2C{lon_s}"
        ),
    }


def build_events_feed(
    *,
    lat: float,
    lon: float,
    services: List[Dict[str, Any]],
    places: Optional[List[Dict[str, Any]]] = None,
    bulletins: Optional[List[Dict[str, Any]]] = None,
    max_items: int = 40,
) -> List[Dict[str, Any]]:
    """
    Text activity feed similar to the demo dashboard: mix of nearby services,
    community bulletins, and place landmarks.
    """
    now = int(time.time())
    feed: List[Dict[str, Any]] = []

    for s in services[:25]:
        dist = s.get("distance")
        dist_s = f"{dist:.1f} mi" if isinstance(dist, (int, float)) else ""
        svc = (s.get("service") or "Service request")[:120]
        feed.append(
            {
                "type": "service",
                "ts": now,
                "title": "Open request nearby",
                "text": f"{svc}" + (f" · {dist_s}" if dist_s else ""),
                "bid_id": s.get("bid_id"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "privacy_level": s.get("privacy_level"),
            }
        )

    for b in bulletins or []:
        feed.append(
            {
                "type": "bulletin",
                "ts": int(b.get("posted_at") or now),
                "title": (b.get("title") or "Community")[:80],
                "text": (b.get("content") or "")[:200],
                "category": b.get("category"),
            }
        )

    for p in places or []:
        feed.append(
            {
                "type": "place",
                "ts": now,
                "title": f"Landmark · {p.get('kind', 'place')}",
                "text": p.get("name") or "",
                "lat": p.get("lat"),
                "lon": p.get("lon"),
                "source": p.get("source"),
            }
        )

    # Sort bulletins/services by recency-ish (services first as most actionable)
    type_rank = {"service": 0, "bulletin": 1, "place": 2}
    feed.sort(key=lambda x: (type_rank.get(x.get("type"), 9), -int(x.get("ts") or 0)))
    return feed[:max_items]


def enrich_nearby(
    lat: float,
    lon: float,
    services: List[Dict[str, Any]],
    *,
    include_places: bool = True,
    include_reverse: bool = True,
    bulletins: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Assemble maps + feed enrichment block for /nearby response."""
    providers_hit: List[str] = []
    reverse = None
    if include_reverse:
        reverse = reverse_geocode_mapbox(lat, lon)
        if reverse:
            providers_hit.append("mapbox_geocoding")
        else:
            reverse = reverse_geocode_nominatim(lat, lon)
            if reverse:
                providers_hit.append("nominatim")

    places: List[Dict[str, Any]] = []
    if include_places:
        places = places_overpass(lat, lon)
        if places:
            providers_hit.append("overpass")

    label = "Nearby"
    if reverse and reverse.get("city"):
        label = str(reverse["city"])

    return {
        "query_point": {"lat": round(lat, 5), "lon": round(lon, 5)},
        "reverse_geocode": reverse,
        "map_links": deep_links(lat, lon, label),
        "map_display": map_display_payload(lat, lon),
        "places": places,
        "events": build_events_feed(
            lat=lat, lon=lon, services=services, places=places, bulletins=bulletins
        ),
        "providers_used": providers_hit,
        "provider_notes": {
            "google_maps": "Deep link only (no server-side Google API key required)",
            "apple_maps": "Deep link only",
            "bing_maps": "Deep link only",
            "yahoo_maps": "Deep link only",
            "mapbox": "Geocoding/static map when MAPBOX_ACCESS_TOKEN is set; else link only",
            "openstreetmap": "Nominatim reverse + Overpass POIs (public, rate-limited)",
        },
    }

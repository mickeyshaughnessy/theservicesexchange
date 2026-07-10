"""
Service Exchange Business Logic
------------------------------
This module contains the core business logic for the Service Exchange Protocol.
It handles user management, bid/job matching, messaging, and seat verification.
"""

import uuid
import json
import time
import logging
import math
import secrets
import threading
import requests
from typing import Dict, List, Optional, Tuple, Union, Any
from werkzeug.security import generate_password_hash, check_password_hash

import config
import seat_verification
from utils import (
    get_account, save_account, account_exists, get_signup_stats,
    save_token,
    save_bid, get_bid, delete_bid, get_all_bids, get_user_bids,
    save_job, get_job, get_all_jobs, get_user_jobs,
    save_message, get_user_messages,
    save_bulletin, get_all_bulletins,
    get_feedback, save_feedback,
    get_financing_applications, save_financing_applications,
    get_follows, save_follows,
    get_username_by_slug, save_slug_mapping,
    save_avatar,
    get_shop_orders, save_shop_orders,
    get_all_accounts,
    save_campaign, get_campaign, get_all_campaigns,
    get_endorsements, save_endorsements,
    get_disputes, save_disputes,
)

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Data Loading (Mock Database)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two geographic points using Haversine formula.
    Returns distance in miles.
    """
    if not all([lat1 is not None, lon1 is not None, lat2 is not None, lon2 is not None]):
        return float('inf')
    
    # Radius of Earth in miles
    R = 3959
    
    try:
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    except ValueError:
        return float('inf')

# ── Geocoding ─────────────────────────────────────────────────────────────────
# Uses Nominatim (OpenStreetMap) via plain HTTP requests with:
#   • Fast-path lookup table for common test addresses (no I/O)
#   • In-process cache (up to 2000 entries; evicts oldest when full)
#   • 1.1 s rate-limit gate between Nominatim requests (ToS requirement)
#   • Returns (None, None) on failure so callers skip distance filtering
#     rather than silently collapsing every unknown address to one point.

_GEOCODE_CACHE: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
_GEOCODE_LOCK = threading.Lock()
_GEOCODE_LAST_REQ: float = 0.0
_NOMINATIM_MIN_INTERVAL = 1.1   # seconds between requests
_GEOCODE_CACHE_MAX = 2000

# Hardcoded fast-path for addresses that appear frequently in tests/examples.
_KNOWN_COORDS: Dict[str, Tuple[float, float]] = {
    "123 main st, denver, co 80202": (39.7392, -104.9903),
    "456 oak ave, denver, co 80203": (39.7431, -104.9792),
    "789 pine st, denver, co 80204": (39.7391, -105.0178),
    "downtown denver, co":           (39.7392, -104.9903),
    "denver airport":                (39.8561, -104.6737),
    "denver, co":                    (39.7392, -104.9903),
    "colorado":                      (39.5501, -105.7821),
}


def geocode_address(address: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Geocode an address string to (lat, lon).

    Resolution order:
      1. Hardcoded fast-path table  (instant)
      2. In-process cache           (instant)
      3. Nominatim / OpenStreetMap  (HTTP, rate-limited to 1 req/sec, free)

    Returns (None, None) when geocoding fails.  Callers that receive None
    coords should skip distance filtering (fail-open) rather than treating
    the bid/provider as being at an arbitrary default location.
    """
    global _GEOCODE_LAST_REQ

    if not address:
        return None, None

    key = address.lower().strip()

    # 1. Hardcoded fast path
    for known_key, coords in _KNOWN_COORDS.items():
        if known_key in key or key in known_key:
            return coords

    # 2. In-process cache (read without lock — worst case a duplicate request)
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]

    # 3. Nominatim HTTP request (serialised by lock to respect rate limit)
    with _GEOCODE_LOCK:
        if key in _GEOCODE_CACHE:          # double-checked
            return _GEOCODE_CACHE[key]

        wait = _NOMINATIM_MIN_INTERVAL - (time.time() - _GEOCODE_LAST_REQ)
        if wait > 0:
            time.sleep(wait)

        result: Tuple[Optional[float], Optional[float]] = (None, None)
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": "TheServicesExchange/1.0 contact@theservicesexchange.com"},
                timeout=5,
            )
            _GEOCODE_LAST_REQ = time.time()
            if resp.status_code == 200:
                hits = resp.json()
                if hits:
                    result = (float(hits[0]["lat"]), float(hits[0]["lon"]))
                    logger.info(f"Geocoded '{address}' → {result}")
                else:
                    logger.info(f"Nominatim: no results for '{address}'")
            else:
                logger.warning(f"Nominatim returned HTTP {resp.status_code} for '{address}'")
        except Exception as exc:
            _GEOCODE_LAST_REQ = time.time()
            logger.warning(f"Geocoding error for '{address}': {exc}")

        # Evict oldest entry when cache is at capacity
        if len(_GEOCODE_CACHE) >= _GEOCODE_CACHE_MAX:
            try:
                _GEOCODE_CACHE.pop(next(iter(_GEOCODE_CACHE)))
            except StopIteration:
                pass

        _GEOCODE_CACHE[key] = result
        return result


# Keep old name as an alias so any remaining call sites still work
def simple_geocode(address: str) -> Tuple[Optional[float], Optional[float]]:
    return geocode_address(address)

def call_openrouter_llm(prompt: str, temperature: float = 0, max_tokens: int = 20, fallback_level: int = 0) -> Optional[str]:
    """
    Call OpenRouter API with 3-tier fallback on rate limiting:
      0 → OPENROUTER_MODEL            (best free model)
      1 → OPENROUTER_FALLBACK_FREE_MODEL (smaller free model)
      2 → OPENROUTER_FALLBACK_MODEL   (paid model)
    """
    _models = [
        config.OPENROUTER_MODEL,
        getattr(config, 'OPENROUTER_FALLBACK_FREE_MODEL', config.OPENROUTER_FALLBACK_MODEL),
        config.OPENROUTER_FALLBACK_MODEL,
    ]

    if fallback_level >= len(_models):
        logger.error("All OpenRouter fallback tiers exhausted")
        return None

    if not config.OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not configured")
        return None

    model = _models[fallback_level]

    try:
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://theservicesexchange.com",
            "X-Title": "The Services Exchange"
        }

        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            config.OPENROUTER_API_URL,
            headers=headers,
            json=data,
            timeout=15
        )

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content'].strip()

        # Rate-limited or quota — try next tier
        is_rate_limited = response.status_code == 429
        if not is_rate_limited:
            try:
                err_msg = response.json().get('error', {}).get('message', '').lower()
                is_rate_limited = any(w in err_msg for w in ('rate', 'limit', 'quota'))
            except Exception:
                pass

        if is_rate_limited:
            next_model = _models[fallback_level + 1] if fallback_level + 1 < len(_models) else None
            logger.warning(f"OpenRouter rate-limited on {model} (tier {fallback_level})"
                           + (f", falling back to {next_model}" if next_model else ", all tiers exhausted"))
            return call_openrouter_llm(prompt, temperature, max_tokens, fallback_level + 1)

        logger.error(f"OpenRouter API error on {model}: {response.status_code} - {response.text[:200]}")

    except requests.exceptions.RequestException as e:
        logger.error(f"OpenRouter request error (tier {fallback_level}, {model}): {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error calling OpenRouter (tier {fallback_level}): {str(e)}")

    return None

def match_service_with_capabilities(service_description: Union[str, Dict], provider_capabilities: str) -> bool:
    """
    Use OpenRouter to determine if provider can fulfill service, with keyword fallback.
    """
    try:
        # Handle service objects
        if isinstance(service_description, dict):
            service_description = json.dumps(service_description)
        
        prompt = f"""You are a service marketplace matching engine. Decide whether a provider can fulfill a service request.

SERVICE REQUEST:
{service_description}

PROVIDER CAPABILITIES:
{provider_capabilities}

RULES:
- Answer YES if the provider's skills, equipment, or credentials reasonably cover this service.
- Be lenient: if there is a plausible chance the provider can do the job, answer YES.
- Answer NO only when the service clearly requires a completely different domain of expertise or equipment.
  Examples that must be NO: a landscaper doing post-surgery nursing; a nurse erecting steel frames;
  a food delivery driver performing a cybersecurity audit; a party entertainer doing EPA emissions testing.
- Partial skill overlap is fine — lean toward YES when in doubt.

Respond with exactly one word: YES or NO.

Answer:"""

        answer = call_openrouter_llm(prompt, temperature=0, max_tokens=20)
        
        if answer:
            if "YES" in answer.upper():
                return True
            if "NO" in answer.upper():
                return False
        
    except Exception as e:
        logger.error(f"LLM matching error: {str(e)}")
    
    # Fallback to keyword matching
    return keyword_match_service(service_description, provider_capabilities)

def keyword_match_service(service_description: Union[str, Dict], provider_capabilities: str) -> bool:
    """Fallback keyword matching."""
    # Handle service objects
    if isinstance(service_description, dict):
        service_description = json.dumps(service_description)
    
    service_words = set(str(service_description).lower().split())
    capability_words = set(provider_capabilities.lower().split())
    common_words = service_words & capability_words
    return len(common_words) >= 1  # More lenient for testing

def calculate_reputation_score(user_data: Dict[str, Any]) -> float:
    """Calculate user reputation score (0.0 - 5.0)."""
    stars = user_data.get('stars', 0)
    total_ratings = user_data.get('total_ratings', 0)
    
    if total_ratings == 0:
        return 2.5
    
    avg_rating = stars / total_ratings
    confidence_factor = min(total_ratings / 10, 1.0)
    return (avg_rating * confidence_factor) + (2.5 * (1 - confidence_factor))

# -----------------------------------------------------------------------------
# Business Logic Handlers
# -----------------------------------------------------------------------------

def register_user(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Register a new user."""
    try:
        username = data.get('username', '').strip()
        password = data.get('password', '')
        user_type = data.get('user_type', '').strip().lower()
        
        if not username or not password:
            return {"error": "Username and password required"}, 400
            
        if len(username) < 3 or len(username) > 20:
            return {"error": "Username must be 3-20 characters"}, 400
            
        if len(password) < 8:
            return {"error": "Password must be at least 8 characters"}, 400
        
        if user_type not in ['demand', 'supply']:
            return {"error": "User type must be 'demand' or 'supply'"}, 400
        
        if account_exists(username):
            return {"error": "Username already exists"}, 409
        
        user_data = {
            'username': username,
            'password': generate_password_hash(password),
            'user_type': user_type,
            'created_on': int(time.time()),
            'stars': 0,
            'total_ratings': 0,
            'completed_jobs': 0
        }
        
        save_account(username, user_data)
        logger.info(f"User registered: {username} (type: {user_type})")
        
        return {"message": "Registration successful"}, 201
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return {"error": "Internal server error"}, 500

def login_user(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Authenticate user and return token."""
    try:
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return {"error": "Username and password required"}, 400
        
        user_data = get_account(username)
        if not user_data:
            return {"error": "Invalid credentials"}, 401
        
        if not check_password_hash(user_data['password'], password):
            return {"error": "Invalid credentials"}, 401
        
        token = str(uuid.uuid4())
        expiry_time = int(time.time()) + config.TOKEN_EXPIRY_SECONDS
        save_token(token, username, expiry_time)
        
        logger.info(f"User logged in: {username}")
        return {"access_token": token, "username": username}, 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_account_info(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get account information."""
    try:
        username = data.get('username')

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        avg_rating = 0
        if user_data['total_ratings'] > 0:
            avg_rating = user_data['stars'] / user_data['total_ratings']

        wallet_address = user_data.get('wallet_address') or None
        seat_status = "no_wallet"
        seat_token_id = None

        if wallet_address:
            result = seat_verification.verify_seat(wallet_address)
            if result["error"]:
                seat_status = "unknown"
            elif result["valid"]:
                seat_status = "valid"
                seat_token_id = result["token_id"]
            elif result["revoked"]:
                seat_status = "revoked"
                seat_token_id = result["token_id"]
            else:
                seat_status = "no_seat"

        return {
            'username': username,
            'created_on': user_data['created_on'],
            'stars': round(avg_rating, 2),
            'total_ratings': user_data['total_ratings'],
            'completed_jobs': user_data.get('completed_jobs', 0),
            'reputation_score': round(calculate_reputation_score(user_data), 2),
            'wallet_address': wallet_address,
            'seat_status': seat_status,
            'seat_token_id': seat_token_id,
        }, 200

    except Exception as e:
        logger.error(f"Account error: {str(e)}")
        return {"error": "Internal server error"}, 500


def set_wallet(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Link an Ethereum wallet address to the authenticated user's account."""
    try:
        username = data.get('username')
        raw_address = (data.get('wallet_address') or '').strip()

        if not raw_address:
            return {"error": "wallet_address required"}, 400

        address = seat_verification.normalize_address(raw_address)
        if address is None:
            return {"error": "Invalid Ethereum address"}, 400

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        user_data['wallet_address'] = address
        seat_result = seat_verification.verify_seat(address)
        if not seat_result["error"]:
            user_data['seat_active'] = seat_result["valid"]
        save_account(username, user_data)

        logger.info(f"Wallet linked for {username}: {address}")
        return {"message": "Wallet address linked", "wallet_address": address}, 200

    except Exception as e:
        logger.error(f"Set wallet error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Profile Management
# -----------------------------------------------------------------------------

_ALLOWED_AVATAR_TYPES = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2MB


def _profile_defaults(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in default shapes for optional profile fields on an account dict (backward-compat for pre-existing accounts)."""
    user_data.setdefault('display_name', None)
    user_data.setdefault('about', None)
    user_data.setdefault('location', None)
    user_data.setdefault('contact_info', None)
    user_data.setdefault('avatar_url', None)
    user_data.setdefault('robots_owned', [])
    user_data.setdefault('subscriptions', [])
    user_data.setdefault('credits', 0)
    user_data.setdefault('cosmetics_owned', {'frames': [], 'backgrounds': [], 'fonts': [], 'text_colors': []})
    user_data.setdefault('cosmetics_equipped', {'frame': None, 'background': None, 'font': None, 'text_color': None})
    return user_data


def _reputation_breakdown(username: str) -> Dict[str, int]:
    """
    Count a user's completed jobs by cooperation type: solo, ad-hoc job-party,
    or campaign-fulfilled. Purely additive context for profiles — does not
    feed back into calculate_reputation_score (which grab_job matching relies on).
    """
    solo = party = campaign = 0
    for job in get_all_jobs():
        if job.get('status') != 'completed':
            continue
        is_primary = username in (job.get('buyer_username'), job.get('provider_username'))
        is_party_member = any(
            p.get('member_username') == username and p.get('status') == 'accepted'
            for p in job.get('party', [])
        )
        if not is_primary and not is_party_member:
            continue
        if job.get('campaign_id'):
            campaign += 1
        elif is_party_member or any(p.get('status') == 'accepted' for p in job.get('party', [])):
            party += 1
        else:
            solo += 1
    return {'solo_jobs_completed': solo, 'party_jobs_completed': party, 'campaign_jobs_completed': campaign}


def _endorsement_summary(username: str) -> Dict[str, Any]:
    """Lightweight endorsement summary for profile display."""
    endorsements = get_endorsements(username)
    by_skill: Dict[str, int] = {}
    for e in endorsements:
        by_skill[e['skill']] = by_skill.get(e['skill'], 0) + 1
    top_skills = sorted(by_skill.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        'total_endorsements': len(endorsements),
        'top_skills': [{'skill': s, 'count': c} for s, c in top_skills],
    }


def get_profile(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get the authenticated user's full profile (private + public fields)."""
    try:
        username = data.get('username')
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        _profile_defaults(user_data)
        follows = get_follows(username)

        return {
            'username': username,
            'display_name': user_data['display_name'],
            'about': user_data['about'],
            'location': user_data['location'],
            'contact_info': user_data['contact_info'],
            'avatar_url': user_data['avatar_url'],
            'reputation_score': round(calculate_reputation_score(user_data), 2),
            'stars': user_data.get('stars', 0),
            'total_ratings': user_data.get('total_ratings', 0),
            'wallet_address': user_data.get('wallet_address'),
            'credits': user_data['credits'],
            'robots_owned': user_data['robots_owned'],
            'subscriptions': user_data['subscriptions'],
            'cosmetics_owned': user_data['cosmetics_owned'],
            'cosmetics_equipped': user_data['cosmetics_equipped'],
            'follower_count': len(follows['followers']),
            'following_count': len(follows['following']),
            'profile_slug': user_data.get('profile_slug'),
            'reputation_breakdown': _reputation_breakdown(username),
            'endorsements': _endorsement_summary(username),
        }, 200
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        return {"error": "Internal server error"}, 500


def update_profile(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Update the authenticated user's editable profile fields. Username is immutable, all fields optional."""
    try:
        username = data.get('username')
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        _profile_defaults(user_data)

        if 'display_name' in data:
            user_data['display_name'] = (data.get('display_name') or '').strip()[:40] or None
        if 'about' in data:
            user_data['about'] = (data.get('about') or '').strip()[:1000] or None
        if 'location' in data:
            user_data['location'] = (data.get('location') or '').strip()[:120] or None
        if 'contact_info' in data:
            user_data['contact_info'] = (data.get('contact_info') or '').strip()[:300] or None

        save_account(username, user_data)
        return {"message": "Profile updated"}, 200
    except Exception as e:
        logger.error(f"Update profile error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_or_create_profile_slug(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Return the authenticated user's public profile share slug, generating one if absent."""
    try:
        username = data.get('username')
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        slug = user_data.get('profile_slug')
        if not slug:
            slug = secrets.token_urlsafe(9)
            user_data['profile_slug'] = slug
            save_account(username, user_data)
            save_slug_mapping(slug, username)

        return {"profile_slug": slug}, 200
    except Exception as e:
        logger.error(f"Get share link error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_public_profile(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get the public subset of a profile by its share slug. No auth required."""
    try:
        slug = data.get('slug')
        username = get_username_by_slug(slug) if slug else None
        if not username:
            return {"error": "Profile not found"}, 404

        user_data = get_account(username)
        if not user_data:
            return {"error": "Profile not found"}, 404

        _profile_defaults(user_data)
        follows = get_follows(username)

        return {
            'username': username,
            'display_name': user_data['display_name'],
            'avatar_url': user_data['avatar_url'],
            'location': user_data['location'],
            'about': user_data['about'],
            'reputation_score': round(calculate_reputation_score(user_data), 2),
            'stars': user_data.get('stars', 0),
            'total_ratings': user_data.get('total_ratings', 0),
            'robots_owned': user_data['robots_owned'],
            'cosmetics_equipped': user_data['cosmetics_equipped'],
            'follower_count': len(follows['followers']),
            'following_count': len(follows['following']),
            'reputation_breakdown': _reputation_breakdown(username),
            'endorsements': _endorsement_summary(username),
        }, 200
    except Exception as e:
        logger.error(f"Get public profile error: {str(e)}")
        return {"error": "Internal server error"}, 500


def _sniff_image_type(file_bytes: bytes) -> Optional[str]:
    """Identify an image's real content-type from its magic bytes (don't trust the client header)."""
    if file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if file_bytes[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if file_bytes[:4] == b'RIFF' and file_bytes[8:12] == b'WEBP':
        return 'image/webp'
    return None


def upload_avatar(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Upload and link an avatar image for the authenticated user."""
    try:
        username = data.get('username')
        file_bytes = data.get('file_bytes')

        if not file_bytes:
            return {"error": "No file uploaded"}, 400
        if len(file_bytes) > _MAX_AVATAR_BYTES:
            return {"error": "File must be 2MB or smaller"}, 400

        content_type = _sniff_image_type(file_bytes)
        if content_type not in _ALLOWED_AVATAR_TYPES:
            return {"error": "File must be PNG, JPEG, or WEBP"}, 400

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        ext = _ALLOWED_AVATAR_TYPES[content_type]
        avatar_url = save_avatar(username, ext, file_bytes, content_type)
        if not avatar_url:
            return {"error": "Failed to upload avatar"}, 500

        user_data['avatar_url'] = avatar_url
        save_account(username, user_data)

        return {"avatar_url": avatar_url}, 200
    except Exception as e:
        logger.error(f"Upload avatar error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Follow / Followers
# -----------------------------------------------------------------------------

def follow_user(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Follow another user. Follower/followee lists are stored separately from the account blob."""
    try:
        follower = data.get('username')
        followee = (data.get('target_username') or '').strip()

        if not followee:
            return {"error": "target_username required"}, 400
        if followee == follower:
            return {"error": "Cannot follow yourself"}, 400
        if not account_exists(followee):
            return {"error": "User not found"}, 404

        follower_follows = get_follows(follower)
        followee_follows = get_follows(followee)

        if followee not in follower_follows['following']:
            follower_follows['following'].append(followee)
        if follower not in followee_follows['followers']:
            followee_follows['followers'].append(follower)

        save_follows(follower, follower_follows)
        save_follows(followee, followee_follows)

        return {"message": f"Now following {followee}"}, 200
    except Exception as e:
        logger.error(f"Follow user error: {str(e)}")
        return {"error": "Internal server error"}, 500


def unfollow_user(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Unfollow another user."""
    try:
        follower = data.get('username')
        followee = (data.get('target_username') or '').strip()

        if not followee:
            return {"error": "target_username required"}, 400

        follower_follows = get_follows(follower)
        followee_follows = get_follows(followee)

        follower_follows['following'] = [u for u in follower_follows['following'] if u != followee]
        followee_follows['followers'] = [u for u in followee_follows['followers'] if u != follower]

        save_follows(follower, follower_follows)
        save_follows(followee, followee_follows)

        return {"message": f"Unfollowed {followee}"}, 200
    except Exception as e:
        logger.error(f"Unfollow user error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_follow_lists(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get the authenticated user's own followers/following lists (private)."""
    try:
        username = data.get('username')
        follows = get_follows(username)
        return {"following": follows['following'], "followers": follows['followers']}, 200
    except Exception as e:
        logger.error(f"Get follow lists error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Request History (demand-side bids + supply-side jobs, surfaced for the profile page)
# -----------------------------------------------------------------------------

def get_request_history(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get the authenticated user's demand-side (bids) and supply-side (jobs) history."""
    try:
        username = data.get('username')
        return {"bids": get_user_bids(username), "jobs": get_user_jobs(username)}, 200
    except Exception as e:
        logger.error(f"Get request history error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Robots Owned (self-reported)
# -----------------------------------------------------------------------------

def add_robot_owned(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Add a self-reported robot to the authenticated user's profile."""
    try:
        username = data.get('username')
        model = (data.get('model') or '').strip()
        capabilities = data.get('capabilities') or []

        if not model:
            return {"error": "model required"}, 400
        if not isinstance(capabilities, list):
            return {"error": "capabilities must be a list"}, 400

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        robots_owned = user_data.setdefault('robots_owned', [])
        robot = {
            'id': str(uuid.uuid4()),
            'model': model[:80],
            'capabilities': [str(c)[:40] for c in capabilities][:20],
        }
        robots_owned.append(robot)
        save_account(username, user_data)

        return {"robot": robot}, 201
    except Exception as e:
        logger.error(f"Add robot owned error: {str(e)}")
        return {"error": "Internal server error"}, 500


def remove_robot_owned(username: str, robot_id: str) -> Tuple[Dict[str, Any], int]:
    """Remove a self-reported robot from the authenticated user's profile."""
    try:
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        robots_owned = user_data.setdefault('robots_owned', [])
        remaining = [r for r in robots_owned if r.get('id') != robot_id]
        if len(remaining) == len(robots_owned):
            return {"error": "Robot not found"}, 404

        user_data['robots_owned'] = remaining
        save_account(username, user_data)

        return {"message": "Robot removed"}, 200
    except Exception as e:
        logger.error(f"Remove robot owned error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Subscriptions (recurring demand — stubbed, no real billing processed)
# -----------------------------------------------------------------------------

_VALID_CADENCES = ("weekly", "monthly", "quarterly")

def create_subscription(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Create a recurring-demand subscription record. No real billing is processed yet."""
    try:
        username = data.get('username')
        name = (data.get('name') or '').strip()
        cadence = (data.get('cadence') or '').strip().lower()

        if not name:
            return {"error": "name required"}, 400
        if cadence not in _VALID_CADENCES:
            return {"error": f"cadence must be one of {_VALID_CADENCES}"}, 400

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        subscriptions = user_data.setdefault('subscriptions', [])
        subscription = {
            'id': str(uuid.uuid4()),
            'name': name[:80],
            'cadence': cadence,
            'status': 'active',
            'created_on': int(time.time()),
        }
        subscriptions.append(subscription)
        save_account(username, user_data)

        return {"subscription": subscription}, 201
    except Exception as e:
        logger.error(f"Create subscription error: {str(e)}")
        return {"error": "Internal server error"}, 500


def cancel_subscription(username: str, subscription_id: str) -> Tuple[Dict[str, Any], int]:
    """Cancel a recurring-demand subscription record."""
    try:
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        subscriptions = user_data.setdefault('subscriptions', [])
        target = next((s for s in subscriptions if s.get('id') == subscription_id), None)
        if not target:
            return {"error": "Subscription not found"}, 404

        target['status'] = 'cancelled'
        save_account(username, user_data)

        return {"subscription": target}, 200
    except Exception as e:
        logger.error(f"Cancel subscription error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Cosmetics Shop (frames, backgrounds, fonts, text colors)
# -----------------------------------------------------------------------------

COSMETICS_CATALOG = [
    {"id": "frame-neon-cyan", "category": "frame", "name": "Neon Cyan Frame", "price_credits": 100},
    {"id": "frame-neon-magenta", "category": "frame", "name": "Neon Magenta Frame", "price_credits": 100},
    {"id": "frame-gold", "category": "frame", "name": "Gold Frame", "price_credits": 250},
    {"id": "bg-circuit", "category": "background", "name": "Circuit Board", "price_credits": 150},
    {"id": "bg-synthwave-grid", "category": "background", "name": "Synthwave Grid", "price_credits": 150},
    {"id": "bg-starfield", "category": "background", "name": "Starfield", "price_credits": 200},
    {"id": "font-press-start", "category": "font", "name": "Press Start 2P", "price_credits": 75},
    {"id": "font-share-tech", "category": "font", "name": "Share Tech Mono", "price_credits": 75},
    {"id": "color-cyan", "category": "text_color", "name": "Cyan", "price_credits": 50},
    {"id": "color-magenta", "category": "text_color", "name": "Magenta", "price_credits": 50},
    {"id": "color-green", "category": "text_color", "name": "Acid Green", "price_credits": 50},
]

_COSMETICS_CATEGORY_TO_OWNED_KEY = {
    "frame": "frames",
    "background": "backgrounds",
    "font": "fonts",
    "text_color": "text_colors",
}

PAYMENT_PROVIDERS = [
    {
        "id": "phantom_wallet",
        "name": "Phantom Wallet",
        "description": "Pay with SOL/USDC via Phantom Wallet. Integration pending.",
        "integration_status": "pending",
    },
    {
        "id": "xmoney",
        "name": "XMoney",
        "description": "Pay with card or bank transfer via XMoney. Integration pending.",
        "integration_status": "pending",
    },
]

def handle_get_cosmetics_catalog() -> Tuple[Dict[str, Any], int]:
    """Return the cosmetics catalog and available payment providers."""
    return {"items": COSMETICS_CATALOG, "payment_providers": PAYMENT_PROVIDERS}, 200


def handle_purchase_cosmetic(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Purchase a cosmetic item. payment_method 'credits' deducts from the user's internal
    balance and fulfills immediately. External providers (Phantom Wallet, XMoney) are
    stubbed pending real integration, following the financing-partner pattern: the
    order is recorded as pending, no charge is attempted, nothing is added to inventory.
    """
    try:
        username = data.get('username')
        item_id = (data.get('item_id') or '').strip()
        payment_method = (data.get('payment_method') or 'credits').strip().lower()

        item = next((i for i in COSMETICS_CATALOG if i['id'] == item_id), None)
        if not item:
            return {"error": "Item not found"}, 404

        valid_methods = {'credits'} | {p['id'] for p in PAYMENT_PROVIDERS}
        if payment_method not in valid_methods:
            return {"error": f"payment_method must be one of {sorted(valid_methods)}"}, 400

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        _profile_defaults(user_data)
        owned_key = _COSMETICS_CATEGORY_TO_OWNED_KEY[item['category']]

        order = {
            'order_id': str(uuid.uuid4()),
            'username': username,
            'item_id': item['id'],
            'category': item['category'],
            'price_credits': item['price_credits'],
            'payment_method': payment_method,
            'created_on': int(time.time()),
        }

        if payment_method == 'credits':
            if item_id in user_data['cosmetics_owned'][owned_key]:
                return {"error": "Item already owned"}, 400
            if user_data['credits'] < item['price_credits']:
                return {"error": "Insufficient credits"}, 402

            user_data['credits'] -= item['price_credits']
            user_data['cosmetics_owned'][owned_key].append(item_id)
            save_account(username, user_data)
            order['status'] = 'fulfilled'
        else:
            provider = next(p for p in PAYMENT_PROVIDERS if p['id'] == payment_method)
            order['status'] = 'pending'
            order['note'] = f"Order queued — {provider['name']} integration pending. You will be contacted by email."

        orders = get_shop_orders()
        orders.insert(0, order)
        save_shop_orders(orders[:2000])

        return order, 201
    except Exception as e:
        logger.error(f"Purchase cosmetic error: {str(e)}")
        return {"error": "Internal server error"}, 500


def equip_cosmetic(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Equip an owned cosmetic item on the authenticated user's profile."""
    try:
        username = data.get('username')
        item_id = (data.get('item_id') or '').strip()

        item = next((i for i in COSMETICS_CATALOG if i['id'] == item_id), None)
        if not item:
            return {"error": "Item not found"}, 404

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        _profile_defaults(user_data)
        owned_key = _COSMETICS_CATEGORY_TO_OWNED_KEY[item['category']]
        if item_id not in user_data['cosmetics_owned'][owned_key]:
            return {"error": "Item not owned"}, 403

        user_data['cosmetics_equipped'][item['category']] = item_id
        save_account(username, user_data)

        return {"cosmetics_equipped": user_data['cosmetics_equipped']}, 200
    except Exception as e:
        logger.error(f"Equip cosmetic error: {str(e)}")
        return {"error": "Internal server error"}, 500


def admin_adjust_credits(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Admin-only: adjust a user's internal credits balance. Stopgap until a real top-up/payment flow exists."""
    try:
        username = (data.get('username') or '').strip()
        delta = data.get('delta')

        if not username:
            return {"error": "username required"}, 400
        if delta is None:
            return {"error": "delta required"}, 400
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return {"error": "delta must be an integer"}, 400

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        _profile_defaults(user_data)
        user_data['credits'] = max(0, user_data['credits'] + delta)
        save_account(username, user_data)

        return {"username": username, "credits": user_data['credits']}, 200
    except Exception as e:
        logger.error(f"Admin adjust credits error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_my_bids(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get user's active bids."""
    try:
        username = data.get('username')
        
        user_bids = get_user_bids(username)
        current_time = int(time.time())
        
        outstanding_bids = []
        for bid in user_bids:
            if bid['end_time'] > current_time:
                outstanding_bids.append({
                    'bid_id': bid['bid_id'],
                    'service': bid['service'],
                    'price': bid['price'],
                    'currency': bid.get('currency', 'USD'),
                    'payment_method': bid.get('payment_method', 'cash'),
                    'xmoney_account': bid.get('xmoney_account'),
                    'end_time': bid['end_time'],
                    'location_type': bid['location_type'],
                    'address': bid.get('address'),
                    'created_at': bid['created_at'],
                    'status': 'active'
                })
        
        # Sort by newest first
        outstanding_bids.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {"bids": outstanding_bids}, 200
        
    except Exception as e:
        logger.error(f"Get my bids error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_my_jobs(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get user's completed and active jobs, plus any pending/past job-party invitations."""
    try:
        username = data.get('username')
        all_jobs = get_all_jobs()
        user_jobs = [j for j in all_jobs if j.get('buyer_username') == username or j.get('provider_username') == username]

        completed_jobs = []
        active_jobs = []
        rejected_jobs = []

        for job in user_jobs:
            job_info = {
                'job_id': job['job_id'],
                'bid_id': job.get('bid_id'),
                'service': job['service'],
                'price': job['price'],
                'currency': job.get('currency', 'USD'),
                'payment_method': job.get('payment_method', 'cash'),
                'location_type': job['location_type'],
                'address': job.get('address'),
                'start_address': job.get('start_address'),
                'end_address': job.get('end_address'),
                'accepted_at': job['accepted_at'],
                'status': job['status'],
                'buyer_username': job['buyer_username'],
                'provider_username': job['provider_username'],
                'buyer_reputation': job.get('buyer_reputation'),
                'provider_reputation': job.get('provider_reputation'),
                'party': job.get('party', []),
                'campaign_id': job.get('campaign_id'),
            }

            # Add role information
            if username == job['buyer_username']:
                job_info['role'] = 'buyer'
                job_info['counterparty'] = job['provider_username']
                job_info['my_rating'] = job.get('buyer_rating')
                job_info['their_rating'] = job.get('provider_rating')
            else:
                job_info['role'] = 'provider'
                job_info['counterparty'] = job['buyer_username']
                job_info['my_rating'] = job.get('provider_rating')
                job_info['their_rating'] = job.get('buyer_rating')
            
            if job['status'] == 'completed':
                job_info['completed_at'] = job.get('completed_at')
                completed_jobs.append(job_info)
            elif job['status'] == 'rejected':
                job_info['rejected_at'] = job.get('rejected_at')
                rejected_jobs.append(job_info)
            elif job['status'] == 'accepted':
                active_jobs.append(job_info)
        
        # Sort by time (newest first)
        completed_jobs.sort(key=lambda x: x.get('completed_at', 0), reverse=True)
        active_jobs.sort(key=lambda x: x['accepted_at'], reverse=True)
        rejected_jobs.sort(key=lambda x: x.get('rejected_at', 0), reverse=True)

        # Jobs where this user was invited as an ad-hoc job-party co-provider
        # (not the primary provider, so not covered by user_jobs above).
        party_invites = []
        for job in all_jobs:
            if job.get('provider_username') == username:
                continue
            member = next((p for p in job.get('party', []) if p.get('member_username') == username), None)
            if not member:
                continue
            party_invites.append({
                'job_id': job['job_id'],
                'service': job['service'],
                'price': job['price'],
                'currency': job.get('currency', 'USD'),
                'primary_provider': job.get('provider_username'),
                'share': member['share'],
                'invite_status': member['status'],
                'job_status': job.get('status'),
            })
        party_invites.sort(key=lambda x: x['job_status'] != 'accepted')

        return {
            "completed_jobs": completed_jobs[:10],  # Limit to last 10
            "active_jobs": active_jobs,
            "rejected_jobs": rejected_jobs[:10],
            "party_invites": party_invites,
        }, 200

    except Exception as e:
        logger.error(f"Get my jobs error: {str(e)}")
        return {"error": "Internal server error"}, 500

def submit_bid(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Submit a new service request."""
    try:
        username = data.get('username')
        service = data.get('service')
        price = data.get('price')
        currency = data.get('currency', 'USD')
        payment_method = data.get('payment_method', 'cash')
        xmoney_account = data.get('xmoney_account')
        end_time = data.get('end_time')
        location_type = data.get('location_type', 'physical')

        if not service or price is None or end_time is None:
            return {"error": "Service, price, and end_time required"}, 400

        if location_type not in ('physical', 'hybrid', 'remote'):
            return {"error": "location_type must be 'physical', 'hybrid', or 'remote'"}, 400
        
        if price <= 0:
            return {"error": "Price must be positive"}, 400
        
        if end_time <= time.time():
            return {"error": "End time must be in the future"}, 400
            
        lat, lon = None, None
        address = None
        
        # Ridesharing-specific fields
        start_address = data.get('start_address')
        end_address = data.get('end_address')
        start_lat, start_lon = None, None
        end_lat, end_lon = None, None
        
        # Handle ridesharing requests with start/end locations
        if start_address and end_address:
            # Geocode pickup location
            start_lat, start_lon = simple_geocode(start_address)
            # Geocode dropoff location
            end_lat, end_lon = simple_geocode(end_address)
            # For ridesharing, the primary location is the pickup point
            lat, lon = start_lat, start_lon
            address = start_address
            logger.info(f"Ridesharing bid: {start_address} -> {end_address}")
        elif location_type in ['physical', 'hybrid']:
            # Traditional physical service with single location
            if 'lat' in data and 'lon' in data:
                lat = data['lat']
                lon = data['lon']
            elif 'address' in data:
                address = data['address']
                lat, lon = simple_geocode(address)
            else:
                return {"error": "Location required for physical services"}, 400
        
        user_data = get_account(username)
        if not user_data or user_data.get('user_type') != 'demand':
            return {"error": "Only demand-type accounts can submit bids"}, 403

        reputation = calculate_reputation_score(user_data)

        bid_id = str(uuid.uuid4())
        bid = {
            'bid_id': bid_id,
            'username': username,
            'service': service,
            'price': price,
            'currency': currency,
            'payment_method': payment_method,
            'xmoney_account': xmoney_account,
            'end_time': end_time,
            'location_type': location_type,
            'lat': lat,
            'lon': lon,
            'address': address,
            'created_at': int(time.time()),
            'buyer_reputation': reputation,
            # Ridesharing-specific fields (None for non-ridesharing)
            'start_address': start_address,
            'end_address': end_address,
            'start_lat': start_lat,
            'start_lon': start_lon,
            'end_lat': end_lat,
            'end_lon': end_lon
        }
        
        save_bid(bid_id, bid)
        logger.info(f"Bid created: {bid_id}")
        
        return {"bid_id": bid_id}, 200
        
    except Exception as e:
        logger.error(f"Bid error: {str(e)}")
        return {"error": "Internal server error"}, 500

def cancel_bid(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Cancel a pending bid."""
    try:
        username = data.get('username')
        bid_id = data.get('bid_id')
        
        if not bid_id:
            return {"error": "Bid ID required"}, 400
        
        bid = get_bid(bid_id)
        if not bid:
            # Check if the bid was already accepted (turned into an active job)
            active_job = next(
                (j for j in get_user_jobs(username)
                 if j.get('bid_id') == bid_id and j.get('status') == 'accepted'),
                None
            )
            if active_job:
                return {
                    "error": "Bid has already been accepted by a provider",
                    "job_id": active_job['job_id'],
                }, 409
            return {"error": "Bid not found"}, 404

        if bid['username'] != username:
            return {"error": "Not authorized"}, 403
        
        delete_bid(bid_id)
        logger.info(f"Bid cancelled: {bid_id}")
        
        return {"message": "Bid cancelled"}, 200
        
    except Exception as e:
        logger.error(f"Cancel error: {str(e)}")
        return {"error": "Internal server error"}, 500

def grab_job(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Match provider with best job using prioritized matching algorithm:
    1. Location filtering
    2. Capability matching (AI)
    3. Reputation alignment
    4. Price (Highest first)
    """
    try:
        username = data.get('username')

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        if config.SEAT_VERIFICATION_ENABLED:
            if not user_data.get('seat_active'):
                wallet = user_data.get('wallet_address')
                if not wallet:
                    return {"error": "No wallet address linked. Use /set_wallet to link your Ethereum wallet."}, 403
                return {"error": f"No valid RSE Seat found for wallet {wallet}. Use /set_wallet to re-sync after acquiring a seat."}, 403

        _GRAB_COOLDOWN = 900
        last_grab = user_data.get('last_grab_at', 0)
        remaining = _GRAB_COOLDOWN - (time.time() - last_grab)
        if remaining > 0:
            return {"error": f"Rate limit: wait {int(remaining)}s before next /grab_job"}, 429

        capabilities = data.get('capabilities', '').strip()
        location_type = data.get('location_type', 'physical')

        if not capabilities:
            return {"error": "Capabilities required"}, 400

        if user_data.get('user_type') != 'supply':
            return {"error": "Only supply-type accounts can grab jobs"}, 403

        provider_reputation = calculate_reputation_score(user_data)
        
        provider_lat, provider_lon = None, None
        max_distance = data.get('max_distance', config.DEFAULT_MAX_DISTANCE_MILES)
        
        if location_type in ['physical', 'hybrid']:
            if 'lat' in data and 'lon' in data:
                provider_lat = data['lat']
                provider_lon = data['lon']
            elif 'address' in data:
                provider_lat, provider_lon = simple_geocode(data['address'])
            else:
                return {"error": "Location required for physical services"}, 400
        
        all_bids = get_all_bids()
        
        # Step 1: Location filtering
        location_filtered = []
        for bid in all_bids:
            if bid['end_time'] <= time.time():
                continue

            # Skip bids previously rejected by this provider
            if username in bid.get('rejected_by', []):
                continue

            # Filter by location type compatibility
            if location_type == 'remote' and bid['location_type'] in ['physical', 'hybrid']:
                continue
            if location_type == 'physical' and bid['location_type'] == 'remote':
                continue
            
            # Check distance for physical services
            if bid['location_type'] in ['physical', 'hybrid'] and location_type in ['physical', 'hybrid']:
                if bid.get('lat') and bid.get('lon') and provider_lat and provider_lon:
                    distance = calculate_distance(
                        bid['lat'], bid['lon'],
                        provider_lat, provider_lon
                    )
                    if distance > max_distance:
                        continue
            
            location_filtered.append(bid)
        
        if not location_filtered:
            return {"message": "No jobs in your area"}, 204
        
        # Step 2: Capability matching using LLM
        capability_matched = []
        for bid in location_filtered:
            if match_service_with_capabilities(bid['service'], capabilities):
                capability_matched.append(bid)
        
        if not capability_matched:
            return {"message": "No matching jobs for your capabilities"}, 204
        
        # Step 3: Sort by reputation alignment (smaller difference is better)
        capability_matched.sort(key=lambda b: abs(provider_reputation - b['buyer_reputation']))
        
        # Step 4: Within same reputation tier, sort by price (highest first)
        final_sorted = []
        current_rep_diff = None
        current_group = []
        
        for bid in capability_matched:
            rep_diff = abs(provider_reputation - bid['buyer_reputation'])
            if current_rep_diff is None or abs(rep_diff - current_rep_diff) < 0.5:
                current_group.append(bid)
                current_rep_diff = rep_diff
            else:
                current_group.sort(key=lambda b: b['price'], reverse=True)
                final_sorted.extend(current_group)
                current_group = [bid]
                current_rep_diff = rep_diff
        
        if current_group:
            current_group.sort(key=lambda b: b['price'], reverse=True)
            final_sorted.extend(current_group)
        
        # Select the best job
        best_bid = final_sorted[0]
        
        job_id = str(uuid.uuid4())
        job_record = {
            'job_id': job_id,
            'bid_id': best_bid['bid_id'],
            'status': 'accepted',
            'service': best_bid['service'],
            'price': best_bid['price'],
            'currency': best_bid.get('currency', 'USD'),
            'payment_method': best_bid.get('payment_method', 'cash'),
            'xmoney_account': best_bid.get('xmoney_account'),
            'location_type': best_bid['location_type'],
            'lat': best_bid.get('lat'),
            'lon': best_bid.get('lon'),
            'address': best_bid.get('address'),
            'buyer_username': best_bid['username'],
            'provider_username': username,
            'accepted_at': int(time.time()),
            'buyer_reputation': best_bid['buyer_reputation'],
            'provider_reputation': provider_reputation,
            # Ridesharing fields (None for non-ridesharing jobs)
            'start_address': best_bid.get('start_address'),
            'end_address': best_bid.get('end_address'),
            'start_lat': best_bid.get('start_lat'),
            'start_lon': best_bid.get('start_lon'),
            'end_lat': best_bid.get('end_lat'),
            'end_lon': best_bid.get('end_lon')
        }
        
        save_job(job_id, job_record)
        delete_bid(best_bid['bid_id'])

        user_data['last_grab_at'] = int(time.time())
        save_account(username, user_data)

        logger.info(f"Job matched: {job_id}")

        return job_record, 200
        
    except Exception as e:
        logger.error(f"Job grab error: {str(e)}")
        return {"error": "Internal server error"}, 500

def reject_job(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Reject a job that was assigned."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        reason = data.get('reason', 'No reason provided')
        
        if not job_id:
            return {"error": "Job ID required"}, 400
        
        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        
        if job['provider_username'] != username:
            return {"error": "Only provider can reject job"}, 403
        
        if job['status'] != 'accepted':
            return {"error": "Can only reject jobs in accepted state"}, 400

        if job.get('campaign_id'):
            # Campaign-originated jobs have no bid to restore — return the
            # committed units to the campaign's pool instead.
            campaign = get_campaign(job['campaign_id'])
            if campaign:
                campaign['units_remaining'] = campaign.get('units_remaining', 0) + job.get('campaign_units', 1)
                if campaign['status'] == 'fulfilled' and campaign['end_time'] > time.time():
                    campaign['status'] = 'open'
                commitment = next(
                    (c for c in campaign.get('commitments', []) if c.get('commitment_id') == job.get('campaign_commitment_id')),
                    None
                )
                if commitment:
                    commitment['status'] = 'rejected'
                    commitment['job_ids'] = []
                save_campaign(campaign['campaign_id'], campaign)
        else:
            # Restore the bid, preserving the original bid_id so the buyer can still track it
            bid_id = job['bid_id']
            rejected_by = list(job.get('rejected_by', []))
            if username not in rejected_by:
                rejected_by.append(username)
            bid = {
                'bid_id': bid_id,
                'username': job['buyer_username'],
                'service': job['service'],
                'price': job['price'],
                'currency': job.get('currency', 'USD'),
                'payment_method': job.get('payment_method', 'cash'),
                'xmoney_account': job.get('xmoney_account'),
                'end_time': int(time.time()) + 3600,  # Extend by 1 hour
                'location_type': job['location_type'],
                'lat': job.get('lat'),
                'lon': job.get('lon'),
                'address': job.get('address'),
                'start_address': job.get('start_address'),
                'end_address': job.get('end_address'),
                'start_lat': job.get('start_lat'),
                'start_lon': job.get('start_lon'),
                'end_lat': job.get('end_lat'),
                'end_lon': job.get('end_lon'),
                'created_at': int(time.time()),
                'buyer_reputation': job['buyer_reputation'],
                'rejected_by': rejected_by
            }
            save_bid(bid_id, bid)

        job['status'] = 'rejected'
        job['rejected_at'] = int(time.time())
        job['rejection_reason'] = reason
        save_job(job_id, job)

        logger.info(f"Job rejected: {job_id}")

        return {"message": "Job rejected successfully"}, 200
        
    except Exception as e:
        logger.error(f"Reject job error: {str(e)}")
        return {"error": "Internal server error"}, 500

def sign_job(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Complete and rate a job."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        # Accept both 'rating' (documented) and 'star_rating' (legacy field name)
        star_rating = data.get('rating') if data.get('rating') is not None else data.get('star_rating')

        if not job_id or star_rating is None:
            return {"error": "Job ID and rating required"}, 400
        
        if not isinstance(star_rating, int) or star_rating < 1 or star_rating > 5:
            return {"error": "Rating must be an integer between 1 and 5"}, 400
        
        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        
        is_buyer = username == job['buyer_username']
        is_provider = username == job['provider_username']
        
        if not (is_buyer or is_provider):
            return {"error": "Not authorized"}, 403

        if job.get('status') not in ('accepted',):
            return {"error": f"Cannot sign a job with status '{job.get('status')}'"}, 400

        sign_field = 'buyer_signed' if is_buyer else 'provider_signed'
        if job.get(sign_field):
            return {"error": "Already signed"}, 400
        
        job[sign_field] = True
        job[f"{'buyer' if is_buyer else 'provider'}_rating"] = star_rating
        
        # Update counterparty stats
        counterparty = job['provider_username'] if is_buyer else job['buyer_username']
        counterparty_data = get_account(counterparty)
        if counterparty_data:
            counterparty_data['stars'] = counterparty_data.get('stars', 0) + star_rating
            counterparty_data['total_ratings'] = counterparty_data.get('total_ratings', 0) + 1
            
            # If both signed, mark complete
            if job.get('buyer_signed') and job.get('provider_signed'):
                counterparty_data['completed_jobs'] = counterparty_data.get('completed_jobs', 0) + 1
                job['status'] = 'completed'
                job['completed_at'] = int(time.time())

                # Update own completed jobs count too
                own_data = get_account(username)
                if own_data:
                    own_data['completed_jobs'] = own_data.get('completed_jobs', 0) + 1
                    save_account(username, own_data)

                # Credit accepted job-party members with the same rating the
                # buyer gave the primary provider, so ad-hoc coalition work
                # reflects on every contributor's reputation.
                buyer_rating = job.get('buyer_rating')
                if buyer_rating:
                    for member in job.get('party', []):
                        if member.get('status') != 'accepted':
                            continue
                        member_data = get_account(member['member_username'])
                        if member_data:
                            member_data['stars'] = member_data.get('stars', 0) + buyer_rating
                            member_data['total_ratings'] = member_data.get('total_ratings', 0) + 1
                            member_data['completed_jobs'] = member_data.get('completed_jobs', 0) + 1
                            save_account(member['member_username'], member_data)

            save_account(counterparty, counterparty_data)
        
        save_job(job_id, job)
        logger.info(f"Job signed: {job_id}")
        
        return {"message": "Job signed successfully"}, 200
        
    except Exception as e:
        logger.error(f"Sign job error: {str(e)}")
        return {"error": "Internal server error"}, 500

def nearby_services(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Find nearby services."""
    try:
        if 'lat' in data and 'lon' in data:
            user_lat = data['lat']
            user_lon = data['lon']
        elif 'address' in data:
            user_lat, user_lon = simple_geocode(data['address'])
            if user_lat is None or user_lon is None:
                return {"error": f"Could not geocode address: '{data['address']}'"}, 400
        else:
            return {"error": "Location required"}, 400

        radius = data.get('radius', 10)
        
        nearby_bids = []
        all_bids = get_all_bids()
        
        for bid in all_bids:
            if bid['location_type'] == 'remote':
                continue
            if bid['end_time'] <= time.time():
                continue
            
            if bid.get('lat') and bid.get('lon'):
                distance = calculate_distance(
                    user_lat, user_lon,
                    bid['lat'], bid['lon']
                )
                
                if distance <= radius:
                    nearby_bids.append({
                        'bid_id': bid['bid_id'],
                        'service': bid['service'],
                        'price': bid['price'],
                        'currency': bid.get('currency', 'USD'),
                        'distance': round(distance, 2),
                        'address': bid.get('address'),
                        'buyer_reputation': bid.get('buyer_reputation', 2.5)
                    })
        
        nearby_bids.sort(key=lambda x: x['distance'])
        
        return {"services": nearby_bids}, 200
        
    except Exception as e:
        logger.error(f"Nearby error: {str(e)}")
        return {"error": "Internal server error"}, 500

def send_chat_message(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Send a chat message."""
    try:
        sender = data.get('username')
        recipient = data.get('recipient')
        message_text = data.get('message', '').strip()
        job_id = data.get('job_id')
        
        if not recipient or not message_text:
            return {"error": "Recipient and message required"}, 400

        if recipient == sender:
            return {"error": "Cannot send a message to yourself"}, 400

        if not account_exists(recipient):
            return {"error": "Recipient not found"}, 404
        
        message_id = str(uuid.uuid4())
        message_data = {
            'message_id': message_id,
            'sender': sender,
            'recipient': recipient,
            'message': message_text,
            'job_id': job_id,
            'sent_at': int(time.time()),
            'read': False
        }
        
        save_message(f"{sender}_{message_id}", message_data)
        save_message(f"{recipient}_{message_id}", message_data)
        
        return {
            "message_id": message_id,
            "sent_at": message_data['sent_at']
        }, 200
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return {"error": "Internal server error"}, 500

def post_bulletin(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Post to the community bulletin."""
    try:
        username = data.get('username')
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        category = data.get('category', 'general')
        
        if not title or not content:
            return {"error": "Title and content required"}, 400
        
        valid_categories = ['announcement', 'question', 'offer', 'general']
        if category not in valid_categories:
            category = 'general'
        
        post_id = str(uuid.uuid4())
        bulletin_data = {
            'post_id': post_id,
            'username': username,
            'title': title,
            'content': content,
            'category': category,
            'posted_at': int(time.time())
        }
        
        save_bulletin(post_id, bulletin_data)
        
        return {
            "post_id": post_id,
            "posted_at": bulletin_data['posted_at']
        }, 200
        
    except Exception as e:
        logger.error(f"Bulletin error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_exchange_data(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get comprehensive exchange data for the dashboard."""
    try:
        category_filter = data.get('category')
        location_filter = data.get('location')
        limit = min(data.get('limit', 50), 200)
        include_completed = data.get('include_completed', False)
        
        all_bids = get_all_bids()
        current_time = int(time.time())
        
        active_bids = []
        for bid in all_bids:
            if bid['end_time'] > current_time:
                # Filter
                if category_filter:
                    service_str = json.dumps(bid['service']) if isinstance(bid['service'], dict) else bid['service']
                    if category_filter.lower() not in service_str.lower():
                        continue
                
                if location_filter:
                    if not bid.get('address') or location_filter.lower() not in bid['address'].lower():
                        continue

                active_bids.append({
                    'bid_id': bid['bid_id'],
                    'service': bid['service'],
                    'price': bid['price'],
                    'currency': bid.get('currency', 'USD'),
                    'location': bid.get('address', 'Remote'),
                    'address': bid.get('address'),
                    'lat': bid.get('lat'),
                    'lon': bid.get('lon'),
                    'buyer_reputation': bid.get('buyer_reputation'),
                    'posted_at': bid['created_at']
                })
        
        active_bids.sort(key=lambda x: x['posted_at'], reverse=True)
        active_bids = active_bids[:limit]
        
        result = {
            'active_bids': active_bids
        }
        
        if include_completed:
            all_jobs = get_all_jobs()
            completed_jobs = []
            
            for job in all_jobs:
                if job['status'] == 'completed':
                    if category_filter:
                        service_str = json.dumps(job['service']) if isinstance(job['service'], dict) else job['service']
                        if category_filter.lower() not in service_str.lower():
                            continue
                    
                    if location_filter:
                        if not job.get('address') or location_filter.lower() not in job['address'].lower():
                            continue
                    
                    ratings = []
                    if job.get('buyer_rating'): ratings.append(job['buyer_rating'])
                    if job.get('provider_rating'): ratings.append(job['provider_rating'])
                    avg_rating = sum(ratings) / len(ratings) if ratings else None
                    
                    completed_jobs.append({
                        'job_id': job['job_id'],
                        'service': job['service'],
                        'price': job['price'],
                        'currency': job.get('currency', 'USD'),
                        'address': job.get('address'),
                        'lat': job.get('lat'),
                        'lon': job.get('lon'),
                        'avg_rating': avg_rating,
                        'completed_at': job.get('completed_at', job['accepted_at'])
                    })
            
            completed_jobs.sort(key=lambda x: x['completed_at'], reverse=True)
            completed_jobs = completed_jobs[:limit]
            
            result['completed_jobs'] = completed_jobs
        
        # Market statistics
        market_stats = {
            'total_active_bids': len([b for b in all_bids if b['end_time'] > current_time]),
            'total_completed_today': 0
        }
        
        if category_filter and active_bids:
            prices = [b['price'] for b in active_bids]
            market_stats[f'avg_price_{category_filter}'] = round(sum(prices) / len(prices), 2)
        
        if include_completed:
            today_start = int(time.time()) - 86400
            all_jobs = get_all_jobs()
            market_stats['total_completed_today'] = len([
                j for j in all_jobs 
                if j['status'] == 'completed' and j.get('completed_at', 0) > today_start
            ])
        
        result['market_stats'] = market_stats
        
        return result, 200
        
    except Exception as e:
        logger.error(f"Exchange data error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_conversations(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get list of conversations for the user."""
    try:
        username = data.get('username')
        messages = get_user_messages(username)
        
        conversations = {}
        for msg in messages:
            other_user = msg['recipient'] if msg['sender'] == username else msg['sender']
            
            if other_user not in conversations:
                conversations[other_user] = {
                    'user': other_user,
                    'lastMessage': msg['message'],
                    'timestamp': msg['sent_at'],
                    'unread': False,
                    'conversation_id': other_user
                }
            else:
                if msg['sent_at'] > conversations[other_user]['timestamp']:
                    conversations[other_user]['lastMessage'] = msg['message']
                    conversations[other_user]['timestamp'] = msg['sent_at']
            
            if msg['recipient'] == username and not msg.get('read'):
                conversations[other_user]['unread'] = True
                
        conv_list = list(conversations.values())
        conv_list.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return {"conversations": conv_list}, 200
    except Exception as e:
        logger.error(f"Get conversations error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_chat_history(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get message history for a specific conversation."""
    try:
        username = data.get('username')
        other_user = data.get('conversation_id')
        
        if not other_user:
            return {"error": "Conversation ID required"}, 400
            
        all_messages = get_user_messages(username)
        chat_messages = []
        
        for msg in all_messages:
            if (msg.get('sender') == username and msg.get('recipient') == other_user) or \
               (msg.get('sender') == other_user and msg.get('recipient') == username):
                chat_messages.append({
                    'sender': msg['sender'],
                    'message': msg['message'],
                    'timestamp': msg['sent_at'],
                    'read': msg.get('read', False)
                })
        
        chat_messages.sort(key=lambda x: x['timestamp'])
        
        return {"messages": chat_messages}, 200
    except Exception as e:
        logger.error(f"Get chat history error: {str(e)}")
        return {"error": "Internal server error"}, 500

def send_reply(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Reply to a conversation."""
    return send_chat_message(data)

def get_bulletin_feed(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get bulletin feed."""
    try:
        bulletins = get_all_bulletins()
        posts = []
        for b in bulletins:
            posts.append({
                'post_id': b['post_id'],
                'title': b['title'],
                'content': b['content'],
                'category': b['category'],
                'author': b['username'],
                'timestamp': b['posted_at']
            })
        return {"posts": posts}, 200
    except Exception as e:
        logger.error(f"Get bulletin feed error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_platform_stats() -> Tuple[Dict[str, Any], int]:
    """Get platform statistics including signup counts."""
    try:
        signup_stats = get_signup_stats()
        all_bids = get_all_bids()
        all_jobs = get_all_jobs()
        current_time = int(time.time())
        
        active_bids = len([b for b in all_bids if b['end_time'] > current_time])
        completed_jobs = len([j for j in all_jobs if j.get('status') == 'completed'])
        
        return {
            'demand_signups': signup_stats['demand'],
            'supply_signups': signup_stats['supply'],
            'total_users': signup_stats['total'],
            'active_requests': active_bids,
            'completed_jobs': completed_jobs
        }, 200
    except Exception as e:
        logger.error(f"Get platform stats error: {str(e)}")
        return {"error": "Internal server error"}, 500

def handle_get_feedback() -> Tuple[Dict[str, Any], int]:
    """Return all feedback posts."""
    try:
        posts = get_feedback()
        return {"posts": posts}, 200
    except Exception as e:
        logger.error(f"Get feedback error: {str(e)}")
        return {"error": "Internal server error"}, 500

def handle_post_feedback(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Create a new feedback post. No auth required; defaults username to Guest."""
    message = (data.get('message') or '').strip()
    if not message:
        return {"error": "Message required"}, 400
    username = (data.get('username') or 'Guest').strip() or 'Guest'
    try:
        posts = get_feedback()
        post = {
            "id": str(uuid.uuid4()),
            "username": username[:40],
            "message": message[:2000],
            "created": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "replies": [],
        }
        posts.insert(0, post)
        save_feedback(posts[:500])
        return {"post": post}, 201
    except Exception as e:
        logger.error(f"Post feedback error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Robot Financing
# -----------------------------------------------------------------------------
# Partner integrations are stubbed: applications are validated, stored, and
# queued per partner with status "pending" until real partner APIs are wired up.

FINANCING_PARTNERS = [
    {
        "id": "robocapital",
        "name": "RoboCapital",
        "description": "Equipment loans for commercial robotics. 24-60 month terms.",
        "rates_from": "7.9% APR",
        "min_amount": 5000,
        "max_amount": 2000000,
        "integration_status": "pending",
    },
    {
        "id": "meridian-fleet",
        "name": "Meridian Fleet Finance",
        "description": "Lease-to-own programs for earning robots. 12-48 month terms.",
        "rates_from": "9.5% APR",
        "min_amount": 1500,
        "max_amount": 250000,
        "integration_status": "pending",
    },
    {
        "id": "first-automation-cu",
        "name": "First Automation Credit Union",
        "description": "Personal robotics loans for home and side-income robots.",
        "rates_from": "6.5% APR",
        "min_amount": 1000,
        "max_amount": 50000,
        "integration_status": "pending",
    },
]

_VALID_CREDIT_RANGES = ("excellent", "good", "fair", "poor", "unknown")

def handle_get_financing_partners() -> Tuple[Dict[str, Any], int]:
    """Return the list of financing partners."""
    return {"partners": FINANCING_PARTNERS}, 200

def handle_submit_financing(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Accept a robot financing application and queue it for up to 3 partners.
    No auth required. Partner delivery is stubbed pending real integrations.
    """
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    robot_model = (data.get('robot_model') or '').strip()
    loan_amount = data.get('loan_amount')

    if not name or not email or not robot_model or loan_amount is None:
        return {"error": "name, email, robot_model, and loan_amount required"}, 400
    if '@' not in email or '.' not in email.split('@')[-1]:
        return {"error": "Invalid email address"}, 400
    try:
        loan_amount = float(loan_amount)
    except (TypeError, ValueError):
        return {"error": "loan_amount must be a number"}, 400
    if loan_amount <= 0 or loan_amount > 5000000:
        return {"error": "loan_amount must be between 0 and 5,000,000 USD"}, 400

    credit_range = (data.get('credit_range') or 'unknown').strip().lower()
    if credit_range not in _VALID_CREDIT_RANGES:
        credit_range = 'unknown'

    valid_ids = {p['id'] for p in FINANCING_PARTNERS}
    requested = data.get('partners') or list(valid_ids)
    if not isinstance(requested, list):
        return {"error": "partners must be a list of partner ids"}, 400
    partner_ids = [p for p in requested if p in valid_ids][:3]
    if not partner_ids:
        return {"error": f"No valid partners selected. Valid ids: {sorted(valid_ids)}"}, 400

    try:
        application = {
            'application_id': str(uuid.uuid4()),
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'name': name[:80],
            'email': email[:120],
            'phone': (data.get('phone') or '').strip()[:40],
            'robot_model': robot_model[:120],
            'loan_amount': round(loan_amount, 2),
            'term_months': int(data.get('term_months') or 36),
            'credit_range': credit_range,
            'status': 'submitted',
            'partner_responses': [
                {
                    'partner_id': pid,
                    'partner_name': next(p['name'] for p in FINANCING_PARTNERS if p['id'] == pid),
                    'status': 'pending',
                    'note': 'Application queued — partner integration pending. You will be contacted by email.',
                }
                for pid in partner_ids
            ],
        }
        applications = get_financing_applications()
        applications.insert(0, application)
        save_financing_applications(applications[:2000])
        logger.info(f"Financing application {application['application_id']} for {robot_model} (${loan_amount:,.0f}, {len(partner_ids)} partners)")

        return {
            "application_id": application['application_id'],
            "status": "submitted",
            "partner_responses": application['partner_responses'],
        }, 201
    except Exception as e:
        logger.error(f"Financing application error: {str(e)}")
        return {"error": "Internal server error"}, 500

def handle_reply_feedback(post_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Append a threaded reply to a feedback post. Open to anyone (like posting)."""
    message = (data.get('message') or '').strip()
    if not message:
        return {"error": "Message required"}, 400
    username = (data.get('username') or 'Guest').strip() or 'Guest'
    try:
        posts = get_feedback()
        target = next((p for p in posts if p.get('id') == post_id), None)
        if target is None:
            return {"error": "Post not found"}, 404
        reply = {
            "id": str(uuid.uuid4()),
            "username": username[:40],
            "message": message[:2000],
            "created": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        replies = target.setdefault('replies', [])
        replies.append(reply)
        target['replies'] = replies[-200:]
        save_feedback(posts)
        return {"reply": reply}, 201
    except Exception as e:
        logger.error(f"Reply feedback error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Job Party (ad-hoc per-job coalitions — no persistent identity)
# -----------------------------------------------------------------------------
# A provider who grabbed (or was assigned) a job can invite other supply-type
# accounts to co-provide that single job. Invitees must accept before their
# share counts. There is no standing "coalition" entity — the party lives on
# the job record itself and dissolves once the job is completed or rejected.

_PARTY_MIN_PROVIDER_SHARE = 0.05  # primary provider always keeps at least 5%

def invite_job_party(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Invite a co-provider to share a job the caller is the primary provider on."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        member_username = (data.get('member_username') or '').strip()
        share = data.get('share')

        if not job_id or not member_username or share is None:
            return {"error": "job_id, member_username, and share required"}, 400
        try:
            share = float(share)
        except (TypeError, ValueError):
            return {"error": "share must be a number"}, 400
        if share <= 0 or share >= 1:
            return {"error": "share must be between 0 and 1 (exclusive)"}, 400
        if member_username == username:
            return {"error": "Cannot invite yourself"}, 400

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        if job['provider_username'] != username:
            return {"error": "Only the primary provider can invite party members"}, 403
        if job.get('status') != 'accepted':
            return {"error": "Job must be in accepted state to form a party"}, 400

        member_account = get_account(member_username)
        if not member_account:
            return {"error": "member_username not found"}, 404
        if member_account.get('user_type') != 'supply':
            return {"error": "Only supply-type accounts can join a job party"}, 400

        party = job.setdefault('party', [])
        if any(p['member_username'] == member_username for p in party):
            return {"error": "Already invited"}, 400

        committed = sum(p['share'] for p in party if p['status'] in ('invited', 'accepted'))
        available = round(1 - _PARTY_MIN_PROVIDER_SHARE - committed, 4)
        if share > available:
            return {"error": f"Share exceeds available capacity (max additional share: {max(available, 0)})"}, 400

        invite = {
            'member_username': member_username,
            'share': share,
            'status': 'invited',
            'invited_at': int(time.time()),
            'responded_at': None,
        }
        party.append(invite)
        save_job(job_id, job)

        logger.info(f"Job party invite: {job_id} {username} -> {member_username} ({share})")
        return {"job_id": job_id, "party": party}, 201
    except Exception as e:
        logger.error(f"Invite job party error: {str(e)}")
        return {"error": "Internal server error"}, 500


def respond_job_party(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Accept or decline a pending job-party invitation."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        action = (data.get('action') or '').strip().lower()

        if not job_id or action not in ('accept', 'decline'):
            return {"error": "job_id and action ('accept' or 'decline') required"}, 400

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404

        party = job.setdefault('party', [])
        invite = next((p for p in party if p['member_username'] == username), None)
        if not invite:
            return {"error": "No invitation found for this job"}, 404
        if invite['status'] != 'invited':
            return {"error": f"Invitation already {invite['status']}"}, 400
        if job.get('status') != 'accepted':
            return {"error": f"Cannot respond to an invitation on a job with status '{job.get('status')}'"}, 400

        invite['status'] = 'accepted' if action == 'accept' else 'declined'
        invite['responded_at'] = int(time.time())
        save_job(job_id, job)

        return {"job_id": job_id, "status": invite['status']}, 200
    except Exception as e:
        logger.error(f"Respond job party error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_job_party(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """View the party roster for a job. Visible to the buyer, primary provider, and party members."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404

        party = job.get('party', [])
        involved = (
            username == job.get('buyer_username')
            or username == job.get('provider_username')
            or any(p['member_username'] == username for p in party)
        )
        if not involved:
            return {"error": "Not authorized"}, 403

        accepted_share = sum(p['share'] for p in party if p['status'] == 'accepted')
        return {
            "job_id": job_id,
            "provider_username": job.get('provider_username'),
            "provider_share": round(1 - accepted_share, 4),
            "party": party,
        }, 200
    except Exception as e:
        logger.error(f"Get job party error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Campaigns (multi-unit demand-side initiatives; providers commit capacity)
# -----------------------------------------------------------------------------
# A demand-side account posts a campaign describing a bulk/recurring need
# (e.g. "500 deliveries this month, need 10 robots") along with a per-unit
# price and total units needed. Supply-side accounts commit to fulfilling a
# slice of it; the campaign owner accepts or rejects each commitment.
# Accepting a commitment spins up a normal job record (reusing sign_job/
# reputation exactly as the grab_job flow does) for that slice of work.

def create_campaign(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Create a multi-unit campaign. Demand-type accounts only."""
    try:
        username = data.get('username')
        title = (data.get('title') or '').strip()
        description = (data.get('description') or '').strip()
        service = data.get('service')
        unit_price = data.get('unit_price')
        units_needed = data.get('units_needed')
        currency = data.get('currency', 'USD')
        payment_method = data.get('payment_method', 'cash')
        location_type = data.get('location_type', 'physical')
        end_time = data.get('end_time')

        if not title or not service or unit_price is None or units_needed is None or end_time is None:
            return {"error": "title, service, unit_price, units_needed, and end_time required"}, 400
        try:
            unit_price = float(unit_price)
            units_needed = int(units_needed)
        except (TypeError, ValueError):
            return {"error": "unit_price must be a number and units_needed an integer"}, 400
        if unit_price <= 0:
            return {"error": "unit_price must be positive"}, 400
        if units_needed < 1:
            return {"error": "units_needed must be at least 1"}, 400
        if end_time <= time.time():
            return {"error": "end_time must be in the future"}, 400
        if location_type not in ('physical', 'hybrid', 'remote'):
            return {"error": "location_type must be 'physical', 'hybrid', or 'remote'"}, 400

        user_data = get_account(username)
        if not user_data or user_data.get('user_type') != 'demand':
            return {"error": "Only demand-type accounts can create campaigns"}, 403

        lat, lon = None, None
        address = data.get('address')
        if location_type in ('physical', 'hybrid'):
            if 'lat' in data and 'lon' in data:
                lat, lon = data['lat'], data['lon']
            elif address:
                lat, lon = simple_geocode(address)
            else:
                return {"error": "Location required for physical/hybrid campaigns"}, 400

        campaign_id = str(uuid.uuid4())
        campaign = {
            'campaign_id': campaign_id,
            'owner_username': username,
            'title': title[:120],
            'description': description[:2000],
            'service': service,
            'unit_price': unit_price,
            'currency': currency,
            'payment_method': payment_method,
            'units_needed': units_needed,
            'units_remaining': units_needed,
            'location_type': location_type,
            'address': address,
            'lat': lat,
            'lon': lon,
            'end_time': end_time,
            'created_at': int(time.time()),
            'status': 'open',
            'commitments': [],
        }
        save_campaign(campaign_id, campaign)
        logger.info(f"Campaign created: {campaign_id} by {username} ({units_needed} units @ {unit_price})")
        return campaign, 201
    except Exception as e:
        logger.error(f"Create campaign error: {str(e)}")
        return {"error": "Internal server error"}, 500


def _campaign_is_open(campaign: Dict[str, Any]) -> bool:
    return (
        campaign.get('status') == 'open'
        and campaign.get('end_time', 0) > time.time()
        and campaign.get('units_remaining', 0) > 0
    )


def get_campaigns(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """List open campaigns (public), optionally filtered by category/location."""
    try:
        category_filter = data.get('category')
        location_filter = data.get('location')
        limit = min(data.get('limit', 50), 200)

        campaigns = get_all_campaigns()
        open_campaigns = []
        for c in campaigns:
            if not _campaign_is_open(c):
                continue
            if category_filter:
                service_str = json.dumps(c['service']) if isinstance(c['service'], dict) else str(c['service'])
                haystack = f"{c.get('title', '')} {service_str}".lower()
                if category_filter.lower() not in haystack:
                    continue
            if location_filter:
                if not c.get('address') or location_filter.lower() not in c['address'].lower():
                    continue
            open_campaigns.append({k: v for k, v in c.items() if k != 'commitments'})

        open_campaigns.sort(key=lambda x: x['created_at'], reverse=True)
        return {"campaigns": open_campaigns[:limit]}, 200
    except Exception as e:
        logger.error(f"Get campaigns error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_campaign_detail(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get full campaign detail including commitments (public)."""
    try:
        campaign_id = data.get('campaign_id')
        campaign = get_campaign(campaign_id)
        if not campaign:
            return {"error": "Campaign not found"}, 404
        return campaign, 200
    except Exception as e:
        logger.error(f"Get campaign detail error: {str(e)}")
        return {"error": "Internal server error"}, 500


def commit_to_campaign(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Commit capacity (a number of units) toward fulfilling a campaign. Supply-type accounts only."""
    try:
        username = data.get('username')
        campaign_id = data.get('campaign_id')
        units = data.get('units')
        capabilities = (data.get('capabilities') or '').strip()
        message = (data.get('message') or '').strip()

        if not campaign_id or units is None:
            return {"error": "campaign_id and units required"}, 400
        try:
            units = int(units)
        except (TypeError, ValueError):
            return {"error": "units must be an integer"}, 400
        if units < 1:
            return {"error": "units must be at least 1"}, 400

        user_data = get_account(username)
        if not user_data or user_data.get('user_type') != 'supply':
            return {"error": "Only supply-type accounts can commit to campaigns"}, 403

        campaign = get_campaign(campaign_id)
        if not campaign:
            return {"error": "Campaign not found"}, 404
        if campaign['owner_username'] == username:
            return {"error": "Cannot commit to your own campaign"}, 400
        if not _campaign_is_open(campaign):
            return {"error": "Campaign is not open for commitments"}, 400
        if units > campaign['units_remaining']:
            return {"error": f"Only {campaign['units_remaining']} unit(s) remaining"}, 400

        commitment = {
            'commitment_id': str(uuid.uuid4()),
            'provider_username': username,
            'units': units,
            'capabilities': capabilities[:400],
            'message': message[:500],
            'status': 'pending',
            'created_at': int(time.time()),
            'responded_at': None,
            'job_ids': [],
        }
        campaign['commitments'].append(commitment)
        save_campaign(campaign_id, campaign)

        logger.info(f"Campaign commitment: {campaign_id} <- {username} ({units} units)")
        return {"campaign_id": campaign_id, "commitment": commitment}, 201
    except Exception as e:
        logger.error(f"Commit to campaign error: {str(e)}")
        return {"error": "Internal server error"}, 500


def respond_campaign_commitment(campaign_id: str, commitment_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Accept or reject a pending commitment. Campaign owner only. Accepting spins up a job record."""
    try:
        username = data.get('username')
        action = (data.get('action') or '').strip().lower()
        if action not in ('accept', 'reject'):
            return {"error": "action must be 'accept' or 'reject'"}, 400

        campaign = get_campaign(campaign_id)
        if not campaign:
            return {"error": "Campaign not found"}, 404
        if campaign['owner_username'] != username:
            return {"error": "Only the campaign owner can respond to commitments"}, 403

        commitment = next((c for c in campaign['commitments'] if c['commitment_id'] == commitment_id), None)
        if not commitment:
            return {"error": "Commitment not found"}, 404
        if commitment['status'] != 'pending':
            return {"error": f"Commitment already {commitment['status']}"}, 400

        if action == 'reject':
            commitment['status'] = 'rejected'
            commitment['responded_at'] = int(time.time())
            save_campaign(campaign_id, campaign)
            return {"campaign_id": campaign_id, "commitment": commitment}, 200

        # Accept: turn the commitment into a real job
        if not _campaign_is_open(campaign):
            return {"error": "Campaign is no longer open"}, 400
        if commitment['units'] > campaign['units_remaining']:
            return {"error": "Insufficient units remaining to accept this commitment"}, 400

        provider_data = get_account(commitment['provider_username'])
        provider_reputation = calculate_reputation_score(provider_data) if provider_data else 2.5
        owner_reputation = calculate_reputation_score(get_account(username) or {})

        job_id = str(uuid.uuid4())
        job_record = {
            'job_id': job_id,
            'bid_id': None,
            'status': 'accepted',
            'service': campaign['service'],
            'price': round(campaign['unit_price'] * commitment['units'], 2),
            'currency': campaign.get('currency', 'USD'),
            'payment_method': campaign.get('payment_method', 'cash'),
            'location_type': campaign['location_type'],
            'lat': campaign.get('lat'),
            'lon': campaign.get('lon'),
            'address': campaign.get('address'),
            'buyer_username': username,
            'provider_username': commitment['provider_username'],
            'accepted_at': int(time.time()),
            'buyer_reputation': owner_reputation,
            'provider_reputation': provider_reputation,
            'campaign_id': campaign_id,
            'campaign_commitment_id': commitment_id,
            'campaign_units': commitment['units'],
        }
        save_job(job_id, job_record)

        commitment['status'] = 'accepted'
        commitment['responded_at'] = int(time.time())
        commitment['job_ids'] = [job_id]

        campaign['units_remaining'] -= commitment['units']
        if campaign['units_remaining'] <= 0:
            campaign['status'] = 'fulfilled'
        save_campaign(campaign_id, campaign)

        logger.info(f"Campaign commitment accepted: {campaign_id}/{commitment_id} -> job {job_id}")
        return {"campaign_id": campaign_id, "commitment": commitment, "job": job_record}, 200
    except Exception as e:
        logger.error(f"Respond campaign commitment error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_my_campaigns(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Campaigns owned by the caller, plus commitments the caller has made on others' campaigns."""
    try:
        username = data.get('username')
        all_campaigns = get_all_campaigns()

        owned = [c for c in all_campaigns if c['owner_username'] == username]
        owned.sort(key=lambda x: x['created_at'], reverse=True)

        committed = []
        for c in all_campaigns:
            if c['owner_username'] == username:
                continue
            for commitment in c.get('commitments', []):
                if commitment['provider_username'] == username:
                    committed.append({
                        'campaign_id': c['campaign_id'],
                        'campaign_title': c['title'],
                        'campaign_status': c['status'],
                        **commitment,
                    })
        committed.sort(key=lambda x: x['created_at'], reverse=True)

        return {"owned_campaigns": owned, "my_commitments": committed}, 200
    except Exception as e:
        logger.error(f"Get my campaigns error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Endorsements (peer skill endorsements)
# -----------------------------------------------------------------------------
# Lightweight social proof that complements star ratings: any user can
# endorse another for a specific skill/capability. Endorsements are shown on
# profiles alongside reputation_score but never alter calculate_reputation_score
# itself (which grab_job matching depends on).

def submit_endorsement(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Endorse another user for a specific skill/capability. Idempotent per (endorser, target, skill)."""
    try:
        endorser = data.get('username')
        target_username = (data.get('target_username') or '').strip()
        skill = (data.get('skill') or '').strip()

        if not target_username or not skill:
            return {"error": "target_username and skill required"}, 400
        if target_username == endorser:
            return {"error": "Cannot endorse yourself"}, 400
        if not account_exists(target_username):
            return {"error": "User not found"}, 404

        skill = skill[:40]
        endorsements = get_endorsements(target_username)
        existing = next(
            (e for e in endorsements if e['endorser'] == endorser and e['skill'].lower() == skill.lower()),
            None
        )
        if existing:
            existing['created_at'] = int(time.time())
        else:
            endorsements.append({'endorser': endorser, 'skill': skill, 'created_at': int(time.time())})
        save_endorsements(target_username, endorsements[:1000])

        return {"target_username": target_username, "skill": skill, "message": "Endorsement recorded"}, 201
    except Exception as e:
        logger.error(f"Submit endorsement error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_user_endorsements(username: str) -> Tuple[Dict[str, Any], int]:
    """Get a user's received endorsements, aggregated by skill (public)."""
    try:
        if not account_exists(username):
            return {"error": "User not found"}, 404

        endorsements = get_endorsements(username)
        by_skill: Dict[str, List[str]] = {}
        for e in endorsements:
            by_skill.setdefault(e['skill'], []).append(e['endorser'])

        skills = [
            {'skill': skill, 'count': len(endorsers), 'endorsers': endorsers}
            for skill, endorsers in by_skill.items()
        ]
        skills.sort(key=lambda s: s['count'], reverse=True)

        return {"username": username, "total_endorsements": len(endorsements), "skills": skills}, 200
    except Exception as e:
        logger.error(f"Get user endorsements error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Leaderboard
# -----------------------------------------------------------------------------

def get_leaderboard() -> Tuple[Dict[str, Any], int]:
    """Public leaderboard: top reputation, top campaign fulfillers, top job-party collaborators."""
    try:
        accounts = get_all_accounts()
        rep_ranked = []
        for username, acc in accounts:
            total_ratings = acc.get('total_ratings', 0)
            if total_ratings < 3:
                continue
            rep_ranked.append({
                'username': username,
                'reputation_score': round(calculate_reputation_score(acc), 2),
                'total_ratings': total_ratings,
                'completed_jobs': acc.get('completed_jobs', 0),
            })
        rep_ranked.sort(key=lambda x: (x['reputation_score'], x['total_ratings']), reverse=True)

        completed_jobs = [j for j in get_all_jobs() if j.get('status') == 'completed']

        campaign_units: Dict[str, int] = {}
        for j in completed_jobs:
            if j.get('campaign_id'):
                campaign_units[j['provider_username']] = campaign_units.get(j['provider_username'], 0) + j.get('campaign_units', 1)
        top_campaign_fulfillers = [
            {'username': u, 'units_fulfilled': n}
            for u, n in sorted(campaign_units.items(), key=lambda kv: kv[1], reverse=True)
        ]

        collaborator_counts: Dict[str, int] = {}
        for j in completed_jobs:
            accepted_members = [p for p in j.get('party', []) if p.get('status') == 'accepted']
            for member in accepted_members:
                collaborator_counts[member['member_username']] = collaborator_counts.get(member['member_username'], 0) + 1
            if accepted_members:
                collaborator_counts[j['provider_username']] = collaborator_counts.get(j['provider_username'], 0) + 1
        top_collaborators = [
            {'username': u, 'party_jobs_completed': n}
            for u, n in sorted(collaborator_counts.items(), key=lambda kv: kv[1], reverse=True)
        ]

        return {
            "top_reputation": rep_ranked[:10],
            "top_campaign_fulfillers": top_campaign_fulfillers[:10],
            "top_collaborators": top_collaborators[:10],
        }, 200
    except Exception as e:
        logger.error(f"Get leaderboard error: {str(e)}")
        return {"error": "Internal server error"}, 500

# -----------------------------------------------------------------------------
# Disputes (flagged jobs, admin review queue)
# -----------------------------------------------------------------------------

_VALID_DISPUTE_RESOLUTIONS = ('resolved', 'dismissed')

def file_dispute(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """File a dispute on a job. Either the buyer or the provider on that job may file."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        reason = (data.get('reason') or '').strip()

        if not job_id or not reason:
            return {"error": "job_id and reason required"}, 400

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404

        if username not in (job.get('buyer_username'), job.get('provider_username')):
            return {"error": "Only the buyer or provider on this job can file a dispute"}, 403

        counterparty = job['provider_username'] if username == job['buyer_username'] else job['buyer_username']
        dispute = {
            'dispute_id': str(uuid.uuid4()),
            'job_id': job_id,
            'filed_by': username,
            'counterparty': counterparty,
            'reason': reason[:1000],
            'filed_at': int(time.time()),
            'status': 'open',
            'resolution_note': None,
            'resolved_at': None,
        }
        disputes = get_disputes()
        disputes.insert(0, dispute)
        save_disputes(disputes[:2000])

        logger.info(f"Dispute filed: {dispute['dispute_id']} on job {job_id} by {username}")
        return dispute, 201
    except Exception as e:
        logger.error(f"File dispute error: {str(e)}")
        return {"error": "Internal server error"}, 500


def admin_list_disputes(status_filter: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
    """Admin-only: list all filed disputes, optionally filtered by status."""
    try:
        disputes = get_disputes()
        if status_filter:
            disputes = [d for d in disputes if d.get('status') == status_filter]
        return {"disputes": disputes}, 200
    except Exception as e:
        logger.error(f"Admin list disputes error: {str(e)}")
        return {"error": "Internal server error"}, 500


def admin_resolve_dispute(dispute_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Admin-only: resolve or dismiss a dispute."""
    try:
        status = (data.get('status') or '').strip().lower()
        note = (data.get('note') or '').strip()

        if status not in _VALID_DISPUTE_RESOLUTIONS:
            return {"error": f"status must be one of {_VALID_DISPUTE_RESOLUTIONS}"}, 400

        disputes = get_disputes()
        dispute = next((d for d in disputes if d['dispute_id'] == dispute_id), None)
        if not dispute:
            return {"error": "Dispute not found"}, 404

        dispute['status'] = status
        dispute['resolution_note'] = note[:1000] or None
        dispute['resolved_at'] = int(time.time())
        save_disputes(disputes)

        return dispute, 200
    except Exception as e:
        logger.error(f"Admin resolve dispute error: {str(e)}")
        return {"error": "Internal server error"}, 500

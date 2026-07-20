"""
The RSE Business Logic
----------------------
This module contains the core business logic for The RSE (Robot Services Exchange) Protocol.
It handles user management, bid/job matching, messaging, and seat verification.
"""

import uuid
import json
import time
import logging
import math
import hashlib
import hmac
import re
import secrets
import threading
import requests
from typing import Dict, List, Optional, Tuple, Union, Any
from werkzeug.security import generate_password_hash, check_password_hash

import config
import seat_verification
import privacy as privacy_mod
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
    get_contact_hash_record, save_contact_hash_record, delete_contact_hash_record,
    save_avatar,
    get_shop_orders, save_shop_orders,
    get_all_accounts,
    save_campaign, get_campaign, get_all_campaigns,
    get_endorsements, save_endorsements,
    get_disputes, save_disputes,
    save_agent_token_record, get_agent_token_record, delete_agent_token_record,
    append_activity_event, list_activity_for_user,
    save_channel, get_channel, save_channel_message, get_channel_message,
    list_channel_messages, find_channel_message_by_client_id,
    get_chat_cursors, save_chat_cursors,
    _user_on_job_party,
)

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Identity helpers (username auth; seat public_id for supply)
# -----------------------------------------------------------------------------

def public_actor(username: str, *, agent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a public identity card for activity, proofs, and account responses."""
    user = get_account(username) or {}
    user_type = user.get('user_type') or 'demand'
    seat_token_id = user.get('seat_token_id')
    seat_active = user.get('seat_active')
    seat_status_cached = user.get('seat_status_cached')

    if user_type == 'supply' and seat_active and seat_token_id is not None:
        public_id = f"seat:{seat_token_id}"
    else:
        public_id = username

    card = {
        'username': username,
        'user_type': user_type,
        'public_id': public_id,
        'handle': username,
        'profile_slug': user.get('profile_slug'),
        'seat_token_id': seat_token_id if user_type == 'supply' else None,
        'seat_status': seat_status_cached,
        'agent_id': None,
        'robot_id': None,
    }
    if agent:
        card['agent_id'] = agent.get('agent_id')
        card['robot_id'] = agent.get('robot_id')
    return card


def _emit(event_type: str, **kwargs) -> None:
    """Best-effort activity emit; never raises to caller.

    Supports related_usernames= so party members get index entries.
    """
    try:
        append_activity_event(event_type, **kwargs)
    except Exception as e:
        logger.warning(f"_emit failed {event_type}: {e}")


def user_is_job_participant(username: str, job: Dict[str, Any]) -> bool:
    """True if username is buyer, provider, or accepted party member (either side)."""
    if username == job.get('buyer_username') or username == job.get('provider_username'):
        return True
    for p in job.get('party', []) + job.get('supply_party', []) + job.get('demand_party', []):
        if p.get('member_username') == username and p.get('status') == 'accepted':
            return True
    # pending invitees are participants for roster visibility
    for p in job.get('party', []) + job.get('supply_party', []) + job.get('demand_party', []):
        if p.get('member_username') == username:
            return True
    return False


# Agent scope matrix: route_key → allowed scopes (any one matches).
# Agents require an explicit entry; missing → 403 (default-deny).
AGENT_ROUTE_SCOPES = {
    'GET /account': {'history:read', 'jobs:read', 'chat:read'},
    'GET /my_jobs': {'history:read', 'jobs:read'},
    'GET /my_bids': {'history:read', 'jobs:read'},
    'GET /request_history': {'history:read'},
    'GET /profile': {'history:read'},
    'POST /grab_job': {'jobs:grab'},
    'POST /reject_job': {'jobs:write'},
    'POST /sign_job': {'jobs:write'},
    'POST /chat': {'chat:write'},
    'POST /chat/reply': {'chat:write'},
    'POST /chat/read': {'chat:read', 'chat:write', 'history:read'},
    'GET /chat/conversations': {'chat:read', 'history:read'},
    'POST /chat/messages': {'chat:read', 'history:read'},
    'GET /jobs/*/party': {'jobs:read', 'history:read'},
    'POST /jobs/*/party/respond': {'jobs:write'},
    'GET /jobs/*/channel': {'chat:read', 'history:read'},
    'GET /jobs/*/messages': {'chat:read', 'history:read'},
    'POST /jobs/*/messages': {'chat:write'},
    'POST /jobs/*/messages/read': {'chat:read', 'chat:write', 'history:read'},
    'GET /agents': {'history:read'},
    'GET /activity/me': {'history:read'},
    'GET /activity/jobs/*': {'history:read'},
    'GET /export/history': {'history:read'},
    'GET /export/proof/*': {'history:read'},
    'GET /portfolio/*': {'history:read'},
    'GET /campaigns': {'history:read'},
    'GET /campaigns/*': {'history:read'},
    'POST /campaigns/*/commit': {'jobs:grab', 'jobs:write'},
}

# In-process rate counters: key -> (window_start, count)
_rate_buckets: Dict[str, Tuple[float, int]] = {}
_CHANNEL_BODY_MAX = 4000
_CHANNEL_PAYLOAD_MAX_BYTES = 8 * 1024
_CHANNEL_POST_LIMIT_PER_MIN = 30
_AGENT_STRUCTURED_LIMIT_PER_MIN = 10

_MAX_AGENTS_PER_ACCOUNT = 10
_DEFAULT_AGENT_SCOPES = ['history:read']
_ALL_AGENT_SCOPES = {
    'history:read', 'jobs:read', 'jobs:grab', 'jobs:write',
    'chat:read', 'chat:write',
}

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

def call_openrouter_llm(
    prompt: str,
    temperature: float = 0,
    max_tokens: int = 20,
    fallback_level: int = 0,
    timeout: float = 15,
) -> Optional[str]:
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
            timeout=timeout
        )

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content'].strip()

        # Rate-limit / quota / unavailable free model — try next tier
        should_fallback = response.status_code in (401, 402, 403, 404, 408, 429, 502, 503)
        err_msg = ''
        try:
            err_msg = response.json().get('error', {}).get('message', '').lower()
        except Exception:
            pass
        if not should_fallback:
            should_fallback = any(w in err_msg for w in ('rate', 'limit', 'quota', 'not found', 'unavailable'))

        if should_fallback and fallback_level + 1 < len(_models):
            next_model = _models[fallback_level + 1]
            logger.warning(
                f"OpenRouter error on {model} (HTTP {response.status_code}, tier {fallback_level}); "
                f"falling back to {next_model}"
            )
            return call_openrouter_llm(prompt, temperature, max_tokens, fallback_level + 1, timeout)

        logger.error(f"OpenRouter API error on {model}: {response.status_code} - {response.text[:200]}")

    except requests.exceptions.RequestException as e:
        logger.error(f"OpenRouter request error (tier {fallback_level}, {model}): {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error calling OpenRouter (tier {fallback_level}): {str(e)}")

    return None

def _heuristic_parse_service(description: str) -> Dict[str, Any]:
    """Fast offline defaults when LLM is unavailable."""
    text = (description or '').strip()
    low = text.lower()
    location_type = 'physical'
    price = 100.0
    duration_hours = 24

    remote_keys = ('remote', 'online', 'label', 'annotat', 'data ', 'teleop', 'software', 'virtual')
    lawn_keys = ('lawn', 'mow', 'grass', 'yard')
    delivery_keys = ('deliver', 'drone delivery', 'package', 'courier')
    security_keys = ('security', 'patrol', 'guard', 'watch')
    clean_keys = ('clean', 'vacuum', 'scrub', 'janitor')
    photo_keys = ('photo', 'aerial', 'survey', 'inspect')

    if any(k in low for k in remote_keys):
        location_type = 'remote'
        price = 60.0
    elif any(k in low for k in lawn_keys):
        price = 85.0
        duration_hours = 48
    elif any(k in low for k in delivery_keys):
        price = 35.0
        duration_hours = 12
    elif any(k in low for k in security_keys):
        price = 200.0
        duration_hours = 24
    elif any(k in low for k in clean_keys):
        price = 90.0
    elif any(k in low for k in photo_keys):
        price = 120.0

    if 'weekend' in low or 'tomorrow' in low:
        duration_hours = max(duration_hours, 48)
    elif 'weekly' in low or low.startswith('week ') or ' week ' in low:
        duration_hours = max(duration_hours, 168)

    service = text if text else 'General robot service request'
    return {
        'service': service[:500],
        'price': price,
        'currency': 'USD',
        'location_type': location_type,
        'duration_hours': duration_hours,
        'address_hint': None,
        'confidence': 0.35,
        'model': None,
        'source': 'heuristic',
    }


def parse_service_request(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Turn a free-text service description into bid fields via OpenRouter (fast free → Haiku)
    with heuristic fallback. Always returns 200 with best-effort defaults.
    """
    description = (data.get('description') or data.get('service') or '').strip()
    if not description:
        return {'error': 'description required'}, 400
    if len(description) > 2000:
        description = description[:2000]

    base = _heuristic_parse_service(description)

    prompt = f"""You extract structured fields for a robot labor marketplace bid.
Return ONLY valid JSON (no markdown) with keys:
service (string, clear concise task title/description),
price (number, USD estimate for a typical completion),
currency (string, usually USD),
location_type (one of: physical, remote, hybrid),
duration_hours (integer 1-168, how long the request stays open),
address_hint (string or null).

User request:
\"\"\"{description}\"\"\"

Rules:
- Prefer the user's wording in service; lightly clean spelling.
- If price is unclear, estimate a fair marketplace price.
- If location unclear, use physical for real-world tasks else remote.
- duration_hours default 24; weekend/tomorrow → 48; weekly → 168.
JSON only:"""

    try:
        # Fast path: short timeout + low tokens; free model first, Haiku fallback
        raw = call_openrouter_llm(prompt, temperature=0, max_tokens=220, timeout=8)
        if not raw:
            return base, 200

        cleaned = raw.strip()
        if cleaned.startswith('```'):
            cleaned = cleaned.strip('`')
            if cleaned.lower().startswith('json'):
                cleaned = cleaned[4:].strip()
        # extract first JSON object
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
        parsed = json.loads(cleaned)

        service = str(parsed.get('service') or description).strip()[:500]
        try:
            price = float(parsed.get('price', base['price']))
        except (TypeError, ValueError):
            price = base['price']
        if price <= 0 or price > 1_000_000:
            price = base['price']

        currency = str(parsed.get('currency') or 'USD').upper()[:8]
        loc = str(parsed.get('location_type') or base['location_type']).lower()
        if loc not in ('physical', 'remote', 'hybrid'):
            loc = base['location_type']

        try:
            duration_hours = int(parsed.get('duration_hours', base['duration_hours']))
        except (TypeError, ValueError):
            duration_hours = base['duration_hours']
        duration_hours = max(1, min(168, duration_hours))

        address_hint = parsed.get('address_hint')
        if address_hint is not None:
            address_hint = str(address_hint).strip()[:200] or None

        model_name = getattr(config, 'OPENROUTER_MODEL', None)
        return {
            'service': service,
            'price': price,
            'currency': currency,
            'location_type': loc,
            'duration_hours': duration_hours,
            'address_hint': address_hint,
            'confidence': 0.75,
            'model': model_name,
            'source': 'llm',
        }, 200
    except Exception as e:
        logger.warning(f"parse_service_request LLM/parse failed: {e}")
        return base, 200


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
        _emit('account.registered', username=username,
              actor={'username': username, 'user_type': user_type, 'public_id': username, 'handle': username},
              payload={'user_type': user_type},
              idempotency_key=f"account.registered:{username}")
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
        return {
            "access_token": token,
            "username": username,
            "user_type": user_data.get('user_type'),
        }, 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_account_info(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get account information including identity card."""
    try:
        username = data.get('username')

        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404

        avg_rating = 0
        if user_data.get('total_ratings', 0) > 0:
            avg_rating = user_data['stars'] / user_data['total_ratings']

        wallet_address = user_data.get('wallet_address') or None
        seat_status = user_data.get('seat_status_cached') or "no_wallet"
        seat_token_id = user_data.get('seat_token_id')

        if wallet_address:
            result = seat_verification.verify_seat(wallet_address)
            if result["error"]:
                seat_status = "unknown"
            elif result["valid"]:
                seat_status = "valid"
                seat_token_id = result["token_id"]
                user_data['seat_active'] = True
                user_data['seat_token_id'] = seat_token_id
                user_data['seat_status_cached'] = seat_status
                save_account(username, user_data)
            elif result["revoked"]:
                seat_status = "revoked"
                seat_token_id = result["token_id"]
                user_data['seat_active'] = False
                user_data['seat_token_id'] = seat_token_id
                user_data['seat_status_cached'] = seat_status
                save_account(username, user_data)
            else:
                seat_status = "no_seat"
                user_data['seat_active'] = False
                user_data['seat_status_cached'] = seat_status
                save_account(username, user_data)
        else:
            seat_status = "no_wallet"

        agents_meta = user_data.get('agents_meta') or []
        identity = public_actor(username)

        return {
            'username': username,
            'user_type': user_data.get('user_type'),
            'created_on': user_data['created_on'],
            'stars': round(avg_rating, 2),
            'total_ratings': user_data.get('total_ratings', 0),
            'completed_jobs': user_data.get('completed_jobs', 0),
            'reputation_score': round(calculate_reputation_score(user_data), 2),
            'wallet_address': wallet_address,
            'seat_status': seat_status,
            'seat_token_id': seat_token_id,
            'identity': identity,
            'agents_count': len([a for a in agents_meta if not a.get('revoked_at')]),
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
        seat_status = "unknown"
        if not seat_result["error"]:
            user_data['seat_active'] = seat_result["valid"]
            if seat_result["valid"]:
                seat_status = "valid"
                user_data['seat_token_id'] = seat_result["token_id"]
            elif seat_result.get("revoked"):
                seat_status = "revoked"
                user_data['seat_token_id'] = seat_result.get("token_id")
            else:
                seat_status = "no_seat"
                user_data['seat_active'] = False
            user_data['seat_status_cached'] = seat_status
        save_account(username, user_data)

        _emit('wallet.linked', username=username, actor=public_actor(username),
              payload={'wallet_address': address, 'seat_status': seat_status},
              idempotency_key=f"wallet.linked:{username}:{address}")

        logger.info(f"Wallet linked for {username}: {address}")
        return {
            "message": "Wallet address linked",
            "wallet_address": address,
            "seat_status": seat_status,
            "seat_token_id": user_data.get('seat_token_id'),
            "identity": public_actor(username),
        }, 200

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
    user_data.setdefault('auto_bids', [])
    user_data.setdefault('discoverable_by_contacts', False)
    user_data.setdefault('contact_hashes', [])
    user_data.setdefault('privacy_level', privacy_mod.DEFAULT_PUBLIC_PRIVACY)
    user_data.setdefault('privacy_profile_level', privacy_mod.DEFAULT_PUBLIC_PRIVACY)
    user_data.setdefault('privacy_nearby_default', privacy_mod.DEFAULT_PUBLIC_PRIVACY)
    user_data.setdefault('credits', 0)
    user_data.setdefault('cosmetics_owned', {'frames': [], 'backgrounds': [], 'fonts': [], 'text_colors': []})
    user_data.setdefault('cosmetics_equipped', {'frame': None, 'background': None, 'font': None, 'text_color': None})
    return user_data


def _reputation_breakdown(username: str) -> Dict[str, int]:
    """
    Count completed jobs by cooperation type. Attribution counters only —
    does not feed calculate_reputation_score (grab matching).
    """
    solo = supply_party = demand_party = campaign = 0
    for job in get_all_jobs():
        if job.get('status') != 'completed':
            continue
        is_primary = username in (job.get('buyer_username'), job.get('provider_username'))
        supply_member = any(
            p.get('member_username') == username and p.get('status') == 'accepted'
            for p in (job.get('party') or job.get('supply_party') or [])
        )
        demand_member = any(
            p.get('member_username') == username and p.get('status') == 'accepted'
            for p in (job.get('demand_party') or [])
        )
        if not is_primary and not supply_member and not demand_member:
            continue
        if job.get('campaign_id') and is_primary:
            campaign += 1
        elif demand_member and not is_primary:
            demand_party += 1
        elif supply_member and not is_primary:
            supply_party += 1
        elif is_primary and (supply_member or demand_member or
                             any(p.get('status') == 'accepted' for p in (job.get('party') or [])) or
                             any(p.get('status') == 'accepted' for p in (job.get('demand_party') or []))):
            # primary on a party job — count as solo primary with collab context
            solo += 1
        else:
            solo += 1
    return {
        'solo_jobs_completed': solo,
        'party_jobs_completed': supply_party,  # legacy key = supply collab
        'supply_party_jobs_completed': supply_party,
        'demand_party_jobs_completed': demand_party,
        'campaign_jobs_completed': campaign,
    }


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
            'privacy_level': privacy_mod.normalize_privacy_level(
                user_data.get('privacy_level')
            ),
            'privacy_profile_level': privacy_mod.normalize_privacy_level(
                user_data.get('privacy_profile_level') or user_data.get('privacy_level')
            ),
            'privacy_nearby_default': privacy_mod.normalize_privacy_level(
                user_data.get('privacy_nearby_default') or user_data.get('privacy_level')
            ),
            'auto_bids': user_data.get('auto_bids') or [],
            'discoverable_by_contacts': bool(user_data.get('discoverable_by_contacts')),
            'contact_hash_count': len(user_data.get('contact_hashes') or []),
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
        if 'privacy_level' in data:
            user_data['privacy_level'] = privacy_mod.normalize_privacy_level(
                data.get('privacy_level')
            )
        if 'privacy_profile_level' in data:
            user_data['privacy_profile_level'] = privacy_mod.normalize_privacy_level(
                data.get('privacy_profile_level')
            )
        if 'privacy_nearby_default' in data:
            user_data['privacy_nearby_default'] = privacy_mod.normalize_privacy_level(
                data.get('privacy_nearby_default')
            )

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

        plvl = privacy_mod.normalize_privacy_level(
            user_data.get('privacy_profile_level') or user_data.get('privacy_level')
        )
        about = privacy_mod.redact_public_text(user_data.get('about'), plvl)
        location = privacy_mod.project_public_location_field(
            user_data.get('location'), plvl
        )
        return {
            'username': username,
            'display_name': user_data['display_name'],
            'avatar_url': user_data['avatar_url'],
            'location': location,
            'about': about,
            'reputation_score': round(calculate_reputation_score(user_data), 2),
            'stars': user_data.get('stars', 0),
            'total_ratings': user_data.get('total_ratings', 0),
            'robots_owned': user_data['robots_owned'],
            'cosmetics_equipped': user_data['cosmetics_equipped'],
            'follower_count': len(follows['followers']),
            'following_count': len(follows['following']),
            'reputation_breakdown': _reputation_breakdown(username),
            'endorsements': _endorsement_summary(username),
            'privacy_level': plvl,
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
# Auto-bids (recurring demand templates that re-post open requests)
# -----------------------------------------------------------------------------

_AUTO_BID_CADENCES = ("daily", "weekly", "biweekly", "monthly")
_AUTO_BID_MAX_ACTIVE = 5
_CADENCE_SECONDS = {
    "daily": 86400,
    "weekly": 7 * 86400,
    "biweekly": 14 * 86400,
    "monthly": 30 * 86400,
}


def _next_run_at(from_ts: int, cadence: str, preferred_local_hour: int = 8) -> int:
    """Simple cadence advance; preferred hour is a soft UX hint only."""
    step = _CADENCE_SECONDS.get(cadence, 7 * 86400)
    nxt = int(from_ts) + step
    # Snap toward preferred hour UTC as a lightweight default (no tz db required)
    # Users can still re-post sooner via process when due.
    hour = max(0, min(23, int(preferred_local_hour or 8)))
    day = nxt // 86400
    return day * 86400 + hour * 3600


def list_auto_bids(username: str) -> Tuple[Dict[str, Any], int]:
    try:
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
        _profile_defaults(user_data)
        return {
            "auto_bids": user_data.get("auto_bids") or [],
            "limits": {"max_active": _AUTO_BID_MAX_ACTIVE, "cadences": list(_AUTO_BID_CADENCES)},
        }, 200
    except Exception as e:
        logger.error(f"List auto_bids error: {str(e)}")
        return {"error": "Internal server error"}, 500


def create_auto_bid(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Create a recurring auto-request template (max 5 active)."""
    try:
        username = data.get("username")
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
        if user_data.get("user_type") != "demand":
            return {"error": "Only demand accounts can create auto-bids"}, 403
        _profile_defaults(user_data)

        auto_bids = user_data.setdefault("auto_bids", [])
        active = [a for a in auto_bids if a.get("status") == "active"]
        if len(active) >= _AUTO_BID_MAX_ACTIVE:
            return {
                "error": f"At most {_AUTO_BID_MAX_ACTIVE} active auto-requests",
            }, 400

        name = (data.get("name") or "").strip()[:80]
        cadence = (data.get("cadence") or "weekly").strip().lower()
        if cadence not in _AUTO_BID_CADENCES:
            return {"error": f"cadence must be one of {_AUTO_BID_CADENCES}"}, 400

        template_in = data.get("template") or {}
        service = (template_in.get("service") or data.get("service") or "").strip()
        if not service:
            return {"error": "template.service required"}, 400
        try:
            price = float(template_in.get("price") if "price" in template_in else data.get("price"))
        except (TypeError, ValueError):
            return {"error": "template.price must be a number"}, 400
        if price <= 0:
            return {"error": "template.price must be positive"}, 400

        location_type = (
            template_in.get("location_type")
            or data.get("location_type")
            or "physical"
        )
        if location_type not in ("physical", "hybrid", "remote"):
            return {"error": "invalid location_type"}, 400
        address = (template_in.get("address") or data.get("address") or "").strip() or None
        if location_type in ("physical", "hybrid") and not address:
            return {"error": "address required for physical/hybrid auto-bids"}, 400

        expires_in_hours = int(
            template_in.get("expires_in_hours")
            or data.get("expires_in_hours")
            or 24
        )
        expires_in_hours = max(1, min(168, expires_in_hours))
        preferred_hour = int(data.get("preferred_local_hour") or 8)
        preferred_hour = max(0, min(23, preferred_hour))
        now = int(time.time())
        privacy_level = privacy_mod.normalize_privacy_level(
            template_in.get("privacy_level")
            or data.get("privacy_level")
            or user_data.get("privacy_nearby_default")
        )

        if not name:
            name = service[:40] or "Auto request"

        item = {
            "id": str(uuid.uuid4()),
            "name": name,
            "status": "active",
            "cadence": cadence,
            "template": {
                "service": service[:2000],
                "price": price,
                "currency": (template_in.get("currency") or "USD")[:8],
                "payment_method": (
                    template_in.get("payment_method")
                    or data.get("payment_method")
                    or "cash"
                )[:80],
                "location_type": location_type,
                "address": address,
                "expires_in_hours": expires_in_hours,
                "privacy_level": privacy_level,
            },
            "schedule": {
                "preferred_local_hour": preferred_hour,
                "next_run_at": now,  # due immediately so first process posts soon
                "last_run_at": None,
                "last_bid_id": None,
            },
            "limits": {"max_open_from_this": 1},
            "created_on": now,
        }
        auto_bids.append(item)
        save_account(username, user_data)
        return {"auto_bid": item}, 201
    except Exception as e:
        logger.error(f"Create auto_bid error: {str(e)}")
        return {"error": "Internal server error"}, 500


def update_auto_bid(username: str, auto_bid_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    try:
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
        _profile_defaults(user_data)
        auto_bids = user_data.setdefault("auto_bids", [])
        target = next((a for a in auto_bids if a.get("id") == auto_bid_id), None)
        if not target:
            return {"error": "Auto-bid not found"}, 404

        if "status" in data:
            st = str(data.get("status") or "").lower()
            if st not in ("active", "paused", "cancelled"):
                return {"error": "status must be active|paused|cancelled"}, 400
            if st == "active":
                active = [a for a in auto_bids if a.get("status") == "active" and a.get("id") != auto_bid_id]
                if len(active) >= _AUTO_BID_MAX_ACTIVE:
                    return {"error": f"At most {_AUTO_BID_MAX_ACTIVE} active auto-requests"}, 400
            target["status"] = st
        if "name" in data:
            target["name"] = (data.get("name") or target.get("name") or "")[:80]
        if "cadence" in data:
            cad = str(data.get("cadence") or "").lower()
            if cad not in _AUTO_BID_CADENCES:
                return {"error": f"cadence must be one of {_AUTO_BID_CADENCES}"}, 400
            target["cadence"] = cad
        if "template" in data and isinstance(data["template"], dict):
            tpl = target.setdefault("template", {})
            tin = data["template"]
            for key in (
                "service", "price", "currency", "payment_method",
                "location_type", "address", "expires_in_hours", "privacy_level",
            ):
                if key in tin:
                    tpl[key] = tin[key]
            if "privacy_level" in tpl:
                tpl["privacy_level"] = privacy_mod.normalize_privacy_level(tpl["privacy_level"])
        save_account(username, user_data)
        return {"auto_bid": target}, 200
    except Exception as e:
        logger.error(f"Update auto_bid error: {str(e)}")
        return {"error": "Internal server error"}, 500


def process_auto_bids_for_user(username: str) -> Tuple[Dict[str, Any], int]:
    """
    Process due auto-bid templates for one user.
    Skips if a prior open bid from the same template is still live.
    """
    try:
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
        _profile_defaults(user_data)
        auto_bids = user_data.setdefault("auto_bids", [])
        now = int(time.time())
        posted = []
        skipped = []

        for item in auto_bids:
            if item.get("status") != "active":
                continue
            sched = item.setdefault("schedule", {})
            next_run = int(sched.get("next_run_at") or 0)
            if next_run > now:
                skipped.append({"id": item["id"], "reason": "not_due"})
                continue

            last_bid_id = sched.get("last_bid_id")
            if last_bid_id:
                prev = get_bid(last_bid_id)
                if prev and prev.get("end_time", 0) > now:
                    # Still open — push next run without stacking
                    sched["next_run_at"] = _next_run_at(
                        now, item.get("cadence") or "weekly",
                        sched.get("preferred_local_hour", 8),
                    )
                    skipped.append({"id": item["id"], "reason": "open_bid_exists", "bid_id": last_bid_id})
                    continue

            tpl = item.get("template") or {}
            hours = int(tpl.get("expires_in_hours") or 24)
            end_time = now + max(1, min(168, hours)) * 3600
            bid_payload = {
                "username": username,
                "service": tpl.get("service"),
                "price": tpl.get("price"),
                "currency": tpl.get("currency") or "USD",
                "payment_method": tpl.get("payment_method") or "cash",
                "end_time": end_time,
                "location_type": tpl.get("location_type") or "physical",
                "privacy_level": tpl.get("privacy_level"),
            }
            if tpl.get("address"):
                bid_payload["address"] = tpl["address"]

            result, status = submit_bid(bid_payload)
            if status >= 400:
                skipped.append({
                    "id": item["id"],
                    "reason": "submit_failed",
                    "error": result.get("error"),
                })
                # Still advance so a bad template does not tight-loop
                sched["next_run_at"] = _next_run_at(
                    now, item.get("cadence") or "weekly",
                    sched.get("preferred_local_hour", 8),
                )
                continue

            bid_id = result.get("bid_id")
            sched["last_run_at"] = now
            sched["last_bid_id"] = bid_id
            sched["next_run_at"] = _next_run_at(
                now, item.get("cadence") or "weekly",
                sched.get("preferred_local_hour", 8),
            )
            posted.append({"id": item["id"], "bid_id": bid_id})

        save_account(username, user_data)
        return {"posted": posted, "skipped": skipped, "auto_bids": auto_bids}, 200
    except Exception as e:
        logger.error(f"Process auto_bids error: {str(e)}")
        return {"error": "Internal server error"}, 500


# -----------------------------------------------------------------------------
# Contact discovery (opt-in hash match)
# -----------------------------------------------------------------------------

def _contact_pepper() -> str:
    return (
        getattr(config, 'CONTACT_HASH_PEPPER', None)
        or getattr(config, 'RSE_PROOF_SIGNING_KEY', None)
        or 'rse-contact-discovery-v1'
    )


def normalize_phone(raw: str) -> Optional[str]:
    """Strip to digits; keep reasonable phone lengths."""
    if not raw:
        return None
    digits = re.sub(r'\D+', '', str(raw))
    if len(digits) < 7:
        return None
    if len(digits) > 15:
        digits = digits[-15:]
    return digits


def normalize_email(raw: str) -> Optional[str]:
    if not raw:
        return None
    e = str(raw).strip().lower()
    if '@' not in e or '.' not in e.split('@')[-1]:
        return None
    if len(e) > 200:
        return None
    return e


def hash_contact_identifier(kind: str, normalized: str) -> str:
    msg = f"{kind}:{normalized}".encode('utf-8')
    return hmac.new(_contact_pepper().encode('utf-8'), msg, hashlib.sha256).hexdigest()


def _collect_contact_hashes(phones: Optional[List], emails: Optional[List]) -> List[str]:
    hashes: List[str] = []
    seen = set()
    for p in phones or []:
        n = normalize_phone(p)
        if not n:
            continue
        h = hash_contact_identifier('phone', n)
        if h not in seen:
            seen.add(h)
            hashes.append(h)
    for e in emails or []:
        n = normalize_email(e)
        if not n:
            continue
        h = hash_contact_identifier('email', n)
        if h not in seen:
            seen.add(h)
            hashes.append(h)
    return hashes[:200]


def set_contact_discovery(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Opt in/out of contact discovery and register hashed identifiers.
    Never stores raw phone/email — only HMAC digests.
    """
    try:
        username = data.get('username')
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
        _profile_defaults(user_data)

        discoverable = bool(data.get('discoverable', data.get('discoverable_by_contacts', False)))
        phones = data.get('phones') if isinstance(data.get('phones'), list) else []
        emails = data.get('emails') if isinstance(data.get('emails'), list) else []

        old_hashes = list(user_data.get('contact_hashes') or [])
        for h in old_hashes:
            rec = get_contact_hash_record(h)
            if rec and rec.get('username') == username:
                delete_contact_hash_record(h)

        new_hashes: List[str] = []
        if discoverable:
            new_hashes = _collect_contact_hashes(phones, emails)
            if not new_hashes and (phones or emails):
                return {"error": "No valid phone or email identifiers provided"}, 400
            for h in new_hashes:
                existing = get_contact_hash_record(h)
                if existing and existing.get('username') and existing.get('username') != username:
                    continue
                save_contact_hash_record(h, username)

        user_data['discoverable_by_contacts'] = discoverable
        user_data['contact_hashes'] = new_hashes if discoverable else []
        save_account(username, user_data)

        return {
            "discoverable_by_contacts": discoverable,
            "registered_identifiers": len(new_hashes),
            "message": (
                "Discoverable — friends who import contacts can find you."
                if discoverable
                else "Not discoverable — contact hashes cleared."
            ),
        }, 200
    except Exception as e:
        logger.error(f"set_contact_discovery error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_contact_discovery(username: str) -> Tuple[Dict[str, Any], int]:
    try:
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
        _profile_defaults(user_data)
        return {
            "discoverable_by_contacts": bool(user_data.get('discoverable_by_contacts')),
            "registered_identifiers": len(user_data.get('contact_hashes') or []),
        }, 200
    except Exception as e:
        logger.error(f"get_contact_discovery error: {str(e)}")
        return {"error": "Internal server error"}, 500


def match_contacts(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Match imported identifiers against opt-in discoverable users."""
    try:
        username = data.get('username')
        phones = data.get('phones') if isinstance(data.get('phones'), list) else []
        emails = data.get('emails') if isinstance(data.get('emails'), list) else []
        hashes_in = data.get('hashes') if isinstance(data.get('hashes'), list) else []

        hash_list = _collect_contact_hashes(phones, emails)
        for h in hashes_in:
            if isinstance(h, str) and re.fullmatch(r'[0-9a-f]{64}', h.lower()):
                hl = h.lower()
                if hl not in hash_list:
                    hash_list.append(hl)
        hash_list = hash_list[:500]

        matches = []
        seen_users = set()
        for h in hash_list:
            rec = get_contact_hash_record(h)
            if not rec:
                continue
            other = rec.get('username')
            if not other or other == username or other in seen_users:
                continue
            acc = get_account(other)
            if not acc:
                continue
            _profile_defaults(acc)
            if not acc.get('discoverable_by_contacts'):
                continue
            seen_users.add(other)
            matches.append({
                'username': other,
                'display_name': acc.get('display_name'),
                'avatar_url': acc.get('avatar_url'),
                'profile_slug': acc.get('profile_slug'),
                'reputation_score': round(calculate_reputation_score(acc), 2),
            })

        return {
            "matches": matches,
            "checked": len(hash_list),
            "match_count": len(matches),
        }, 200
    except Exception as e:
        logger.error(f"match_contacts error: {str(e)}")
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

def _job_info_for_user(job: Dict[str, Any], username: str) -> Dict[str, Any]:
    """Build job list entry including co-buyer / co-provider roles."""
    job_info = {
        'job_id': job['job_id'],
        'bid_id': job.get('bid_id'),
        'service': job['service'],
        'price': job['price'],
        'currency': job.get('currency', 'USD'),
        'payment_method': job.get('payment_method', 'cash'),
        'location_type': job.get('location_type'),
        'address': job.get('address'),
        'start_address': job.get('start_address'),
        'end_address': job.get('end_address'),
        'accepted_at': job.get('accepted_at'),
        'status': job.get('status'),
        'buyer_username': job.get('buyer_username'),
        'provider_username': job.get('provider_username'),
        'buyer_reputation': job.get('buyer_reputation'),
        'provider_reputation': job.get('provider_reputation'),
        'party': job.get('party', []),
        'supply_party': job.get('party') or job.get('supply_party') or [],
        'demand_party': job.get('demand_party') or [],
        'campaign_id': job.get('campaign_id'),
    }
    if username == job.get('buyer_username'):
        job_info['role'] = 'buyer'
        job_info['counterparty'] = job.get('provider_username')
        job_info['my_rating'] = job.get('buyer_rating')
        job_info['their_rating'] = job.get('provider_rating')
    elif username == job.get('provider_username'):
        job_info['role'] = 'provider'
        job_info['counterparty'] = job.get('buyer_username')
        job_info['my_rating'] = job.get('provider_rating')
        job_info['their_rating'] = job.get('buyer_rating')
    else:
        side = _user_on_job_party(username, job, accepted_only=False) or 'supply'
        job_info['role'] = 'co_buyer' if side == 'demand' else 'co_provider'
        job_info['party_side'] = side
        job_info['counterparty'] = (
            job.get('provider_username') if side == 'demand' else job.get('buyer_username')
        )
        # find share
        roster = (job.get('demand_party') if side == 'demand'
                  else (job.get('party') or job.get('supply_party') or []))
        member = next((p for p in roster if p.get('member_username') == username), None)
        job_info['share'] = member.get('share') if member else None
        job_info['invite_status'] = member.get('status') if member else None
        job_info['my_rating'] = None
        job_info['their_rating'] = None
        job_info['attribution_only'] = side == 'demand'
    return job_info


def get_my_jobs(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Get user's jobs including accepted party memberships, plus pending invites."""
    try:
        username = data.get('username')
        all_jobs = get_all_jobs()
        # Primaries + accepted party members
        user_jobs = []
        for j in all_jobs:
            if j.get('buyer_username') == username or j.get('provider_username') == username:
                user_jobs.append(j)
            elif _user_on_job_party(username, j, accepted_only=True):
                user_jobs.append(j)

        completed_jobs = []
        active_jobs = []
        rejected_jobs = []

        for job in user_jobs:
            job_info = _job_info_for_user(job, username)
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

        # Jobs where this user was invited as party member (supply or demand)
        # but is not primary buyer/provider.
        party_invites = []
        for job in all_jobs:
            if username in (job.get('provider_username'), job.get('buyer_username')):
                continue
            member = None
            side = 'supply'
            for p in job.get('party', []) or []:
                if p.get('member_username') == username:
                    member, side = p, 'supply'
                    break
            if member is None:
                for p in job.get('demand_party', []) or []:
                    if p.get('member_username') == username:
                        member, side = p, 'demand'
                        break
            if not member:
                continue
            party_invites.append({
                'job_id': job['job_id'],
                'service': job['service'],
                'price': job['price'],
                'currency': job.get('currency', 'USD'),
                'primary_provider': job.get('provider_username'),
                'primary_buyer': job.get('buyer_username'),
                'share': member.get('share'),
                'side': side,
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
        _profile_defaults(user_data)
        privacy_level = privacy_mod.normalize_privacy_level(
            data.get('privacy_level')
            or user_data.get('privacy_nearby_default')
            or user_data.get('privacy_level')
        )

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
            'privacy_level': privacy_level,
            # Ridesharing-specific fields (None for non-ridesharing)
            'start_address': start_address,
            'end_address': end_address,
            'start_lat': start_lat,
            'start_lon': start_lon,
            'end_lat': end_lat,
            'end_lon': end_lon
        }
        
        save_bid(bid_id, bid)
        _emit('bid.posted', username=username, actor=public_actor(username),
              payload={'bid_id': bid_id, 'price': price, 'currency': currency},
              idempotency_key=f"bid.posted:{bid_id}")
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
        _emit('bid.cancelled', username=username, actor=public_actor(username),
              payload={'bid_id': bid_id},
              idempotency_key=f"bid.cancelled:{bid_id}")
        logger.info(f"Bid cancelled: {bid_id}")
        
        return {"message": "Bid cancelled"}, 200
        
    except Exception as e:
        logger.error(f"Cancel error: {str(e)}")
        return {"error": "Internal server error"}, 500


def update_bid(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Update an open (not yet accepted) bid owned by the demand user."""
    try:
        username = data.get('username')
        bid_id = data.get('bid_id')
        if not bid_id:
            return {"error": "Bid ID required"}, 400

        bid = get_bid(bid_id)
        if not bid:
            return {"error": "Bid not found"}, 404
        if bid.get('username') != username:
            return {"error": "Not authorized"}, 403

        # If already a job, cannot edit
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

        service = data.get('service', bid.get('service'))
        price = data.get('price', bid.get('price'))
        currency = data.get('currency', bid.get('currency', 'USD'))
        end_time = data.get('end_time', bid.get('end_time'))
        location_type = data.get('location_type', bid.get('location_type', 'physical'))
        payment_method = data.get('payment_method', bid.get('payment_method', 'cash'))

        if not service or price is None or end_time is None:
            return {"error": "Service, price, and end_time required"}, 400
        if location_type not in ('physical', 'hybrid', 'remote'):
            return {"error": "location_type must be 'physical', 'hybrid', or 'remote'"}, 400
        try:
            price = float(price)
        except (TypeError, ValueError):
            return {"error": "Invalid price"}, 400
        if price <= 0:
            return {"error": "Price must be positive"}, 400
        if end_time <= time.time():
            return {"error": "End time must be in the future"}, 400

        lat, lon = bid.get('lat'), bid.get('lon')
        address = bid.get('address')
        if location_type in ('physical', 'hybrid'):
            if 'lat' in data and 'lon' in data:
                lat, lon = data['lat'], data['lon']
            if 'address' in data:
                address = data.get('address')
                if address:
                    glat, glon = simple_geocode(address)
                    if glat is not None:
                        lat, lon = glat, glon
            if not address and lat is None:
                address = 'To be arranged'
        else:
            lat, lon, address = None, None, None

        bid.update({
            'service': service,
            'price': price,
            'currency': currency,
            'payment_method': payment_method,
            'end_time': end_time,
            'location_type': location_type,
            'lat': lat,
            'lon': lon,
            'address': address,
            'updated_at': int(time.time()),
        })
        save_bid(bid_id, bid)
        _emit('bid.updated', username=username, actor=public_actor(username),
              payload={'bid_id': bid_id, 'price': price, 'currency': currency},
              idempotency_key=f"bid.updated:{bid_id}:{bid['updated_at']}")
        logger.info(f"Bid updated: {bid_id}")
        return {"bid_id": bid_id, "message": "Bid updated"}, 200
    except Exception as e:
        logger.error(f"Update bid error: {str(e)}")
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
                return {"error": f"No valid The RSE Seat NFT found for wallet {wallet}. Use /set_wallet to re-sync after acquiring a seat."}, 403

        _GRAB_COOLDOWN = int(getattr(config, 'GRAB_JOB_COOLDOWN_SECONDS', 900) or 900)
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
            'end_lon': best_bid.get('end_lon'),
            'party': [],
            'supply_party': [],
            'demand_party': [],
            'provider_seat_token_id': user_data.get('seat_token_id'),
        }
        
        save_job(job_id, job_record)
        delete_bid(best_bid['bid_id'])

        user_data['last_grab_at'] = int(time.time())
        save_account(username, user_data)

        buyer = job_record.get('buyer_username')
        _emit('job.grabbed', username=username, job_id=job_id,
              actor=public_actor(username),
              payload={'bid_id': best_bid['bid_id'], 'price': best_bid['price']},
              related_usernames=[buyer] if buyer and buyer != username else None,
              idempotency_key=f"job.grabbed:{job_id}")

        ensure_job_channel(
            job_record,
            system_event='job.created',
            system_body=f"Job matched: {job_record.get('service')}",
            system_payload={'price': job_record.get('price'), 'bid_id': best_bid['bid_id']},
        )

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
        
        job = get_job(job_id, force_refresh=True)
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

        ensure_job_channel(
            job,
            system_event='job.rejected',
            system_body=f"Job rejected by provider: {reason}",
            system_payload={'reason': reason},
        )
        buyer = job.get('buyer_username')
        _emit('job.rejected', username=username, job_id=job_id,
              actor=public_actor(username),
              payload={'reason': reason},
              related_usernames=[buyer] if buyer and buyer != username else None,
              idempotency_key=f"job.rejected:{job_id}")

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
        
        # force_refresh: multi-worker cache otherwise loses the other party's signature
        job = get_job(job_id, force_refresh=True)
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
        counterparty_data = get_account(counterparty, force_refresh=True)
        if counterparty_data:
            counterparty_data['stars'] = counterparty_data.get('stars', 0) + star_rating
            counterparty_data['total_ratings'] = counterparty_data.get('total_ratings', 0) + 1
            
            # If both signed, mark complete
            if job.get('buyer_signed') and job.get('provider_signed'):
                counterparty_data['completed_jobs'] = counterparty_data.get('completed_jobs', 0) + 1
                job['status'] = 'completed'
                job['completed_at'] = int(time.time())

                # Update own completed jobs count too
                own_data = get_account(username, force_refresh=True)
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

        role = 'buyer' if is_buyer else 'provider'
        ensure_job_channel(
            job,
            system_event='job.signed',
            system_body=f"{username} signed the job ({role}, rating {star_rating})",
            system_payload={'role': role, 'rating': star_rating},
        )
        if job.get('status') == 'completed':
            ensure_job_channel(
                job,
                system_event='job.completed',
                system_body="Job completed — both parties signed",
                system_payload={},
            )
            related = [u for u in _channel_members_from_job(job) if u != username]
            _emit('job.completed', username=username, job_id=job_id,
                  actor=public_actor(username),
                  payload={},
                  related_usernames=related,
                  idempotency_key=f"job.completed:{job_id}")

        logger.info(f"Job signed: {job_id}")
        
        return {"message": "Job signed successfully"}, 200
        
    except Exception as e:
        logger.error(f"Sign job error: {str(e)}")
        return {"error": "Internal server error"}, 500

def nearby_services(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Find nearby services. Public projections apply per-bid privacy levels."""
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
            if bid.get('location_type') == 'remote':
                continue
            if bid.get('end_time', 0) <= time.time():
                continue
            
            if bid.get('lat') is not None and bid.get('lon') is not None:
                distance = calculate_distance(
                    user_lat, user_lon,
                    bid['lat'], bid['lon']
                )
                
                if distance <= radius:
                    # Match on true coords; publish privacy-projected fields only
                    nearby_bids.append(
                        privacy_mod.project_nearby_service(bid, distance)
                    )
        
        nearby_bids.sort(key=lambda x: x['distance'])
        
        return {
            "services": nearby_bids,
            "privacy_note": (
                "Addresses and coordinates are privacy-projected per the "
                "poster's privacy level (Gaussian geo noise + address coarsening)."
            ),
        }, 200
        
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
    """Get list of conversations for the user (unread via chat read cursors)."""
    try:
        username = data.get('username')
        job_filter = data.get('job_id')
        messages = get_user_messages(username)
        cursors = get_chat_cursors(username).get('by_peer') or {}
        
        conversations = {}
        for msg in messages:
            if job_filter and msg.get('job_id') != job_filter:
                continue
            other_user = msg['recipient'] if msg['sender'] == username else msg['sender']
            
            if other_user not in conversations:
                conversations[other_user] = {
                    'user': other_user,
                    'lastMessage': msg['message'],
                    'timestamp': msg['sent_at'],
                    'unread': False,
                    'conversation_id': other_user,
                    'job_id': msg.get('job_id'),
                }
            else:
                if msg['sent_at'] > conversations[other_user]['timestamp']:
                    conversations[other_user]['lastMessage'] = msg['message']
                    conversations[other_user]['timestamp'] = msg['sent_at']
                    conversations[other_user]['job_id'] = msg.get('job_id')
            
            # Cursor-based unread: inbound messages after peer cursor
            peer_cursor = int(cursors.get(other_user) or 0)
            if msg.get('recipient') == username and int(msg.get('sent_at') or 0) > peer_cursor:
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
# Job channels (Stage B)
# -----------------------------------------------------------------------------

def _channel_members_from_job(job: Dict[str, Any]) -> List[str]:
    """Primaries + accepted party members both sides (not pending invitees)."""
    members = set()
    if job.get('buyer_username'):
        members.add(job['buyer_username'])
    if job.get('provider_username'):
        members.add(job['provider_username'])
    for p in (job.get('party') or []) + (job.get('supply_party') or []) + (job.get('demand_party') or []):
        if p.get('status') == 'accepted' and p.get('member_username'):
            members.add(p['member_username'])
    return sorted(members)


def _channel_state_for_job(job: Dict[str, Any]) -> str:
    status = job.get('status')
    if status == 'accepted':
        return 'active'
    if status in ('completed', 'rejected'):
        return 'read_only'
    return 'read_only'


def _rate_limit_ok(key: str, limit: int, window: float = 60.0) -> bool:
    now = time.time()
    start, count = _rate_buckets.get(key, (now, 0))
    if now - start >= window:
        _rate_buckets[key] = (now, 1)
        return True
    if count >= limit:
        return False
    _rate_buckets[key] = (start, count + 1)
    return True


def ensure_job_channel(job: Dict[str, Any], *, system_event: Optional[str] = None,
                       system_body: Optional[str] = None,
                       system_payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Create or refresh channel membership from job; optional system message."""
    job_id = job.get('job_id')
    if not job_id:
        return None
    members = _channel_members_from_job(job)
    state = _channel_state_for_job(job)
    ch = get_channel(job_id)
    now = int(time.time())
    if not ch:
        ch = {
            'job_id': job_id,
            'channel_type': 'job',
            'state': state,
            'members': members,
            'created_at': now,
            'updated_at': now,
            'read_cursors': {},
            'message_count': 0,
        }
    else:
        ch['members'] = members
        ch['state'] = state
        ch['updated_at'] = now
        ch.setdefault('read_cursors', {})
        ch.setdefault('message_count', 0)
    save_channel(job_id, ch)
    if system_event:
        _post_system_message(job_id, system_event, system_body or system_event,
                             payload=system_payload or {})
        ch = get_channel(job_id) or ch
    return ch


def _post_system_message(job_id: str, event: str, body: str,
                         payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Server-only system message. Never callable as client message_type=system."""
    try:
        message_id = str(uuid.uuid4())
        now = int(time.time())
        msg = {
            'message_id': message_id,
            'job_id': job_id,
            'channel_type': 'job',
            'message_type': 'system',
            'sender': 'system',
            'agent_id': None,
            'robot_id': None,
            'body': (body or event)[:_CHANNEL_BODY_MAX],
            'payload': dict(payload or {}, event=event),
            'sent_at': now,
            'client_message_id': None,
        }
        if not save_channel_message(job_id, message_id, msg):
            return None
        ch = get_channel(job_id)
        if ch:
            ch['message_count'] = int(ch.get('message_count') or 0) + 1
            ch['updated_at'] = now
            ch['last_message_at'] = now
            save_channel(job_id, ch)
        _emit('message.posted', job_id=job_id,
              payload={'message_type': 'system', 'event': event, 'message_id': message_id},
              idempotency_key=f"msg.system:{job_id}:{event}:{message_id}")
        return msg
    except Exception as e:
        logger.warning(f"system message failed {job_id}: {e}")
        return None


def _user_in_channel(username: str, ch: Dict[str, Any]) -> bool:
    return username in (ch.get('members') or [])


def get_job_channel(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """GET channel meta for a job (members must be accepted participants)."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        ch = get_channel(job_id)
        if not ch:
            # lazy create for jobs that predate Stage B
            ch = ensure_job_channel(job)
        if not ch or not _user_in_channel(username, ch):
            return {"error": "Not a channel member"}, 403
        # refresh membership from job
        ch = ensure_job_channel(job) or ch
        if not _user_in_channel(username, ch):
            return {"error": "Not a channel member"}, 403
        return {
            'job_id': job_id,
            'channel_type': 'job',
            'state': ch.get('state'),
            'members': ch.get('members') or [],
            'created_at': ch.get('created_at'),
            'updated_at': ch.get('updated_at'),
            'message_count': ch.get('message_count', 0),
            'last_message_at': ch.get('last_message_at'),
            'my_read_ts': (ch.get('read_cursors') or {}).get(username, 0),
        }, 200
    except Exception as e:
        logger.error(f"Get job channel error: {e}")
        return {"error": "Internal server error"}, 500


def post_job_channel_message(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """POST a message to a job channel (user / agent_structured / status)."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        body = (data.get('body') or data.get('message') or '').strip()
        message_type = (data.get('message_type') or 'user').strip().lower()
        payload = data.get('payload') if isinstance(data.get('payload'), dict) else {}
        client_message_id = data.get('client_message_id')

        if message_type == 'system':
            return {"error": "Clients cannot send system messages"}, 400
        if message_type not in ('user', 'agent_structured', 'status'):
            return {"error": "message_type must be user, agent_structured, or status"}, 400
        if not body:
            return {"error": "body required"}, 400
        if len(body) > _CHANNEL_BODY_MAX:
            return {"error": f"body max {_CHANNEL_BODY_MAX} characters"}, 400
        try:
            payload_bytes = len(json.dumps(payload).encode())
        except (TypeError, ValueError):
            return {"error": "payload must be JSON-serializable object"}, 400
        if payload_bytes > _CHANNEL_PAYLOAD_MAX_BYTES:
            return {"error": "payload exceeds 8KB"}, 400

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        ch = get_channel(job_id) or ensure_job_channel(job)
        if not ch or not _user_in_channel(username, ch):
            return {"error": "Not a channel member"}, 403
        # refresh state
        ch = ensure_job_channel(job) or ch
        if ch.get('state') == 'read_only':
            return {"error": "Channel is read-only (job completed or rejected)"}, 403

        # Rate limits
        if not _rate_limit_ok(f"channel:{username}", _CHANNEL_POST_LIMIT_PER_MIN):
            return {"error": "Rate limit: channel posts max 30/min"}, 429
        agent_id = None
        robot_id = None
        try:
            import flask
            actor = getattr(flask.g, 'actor', None) or {}
            if actor.get('is_agent'):
                agent_id = actor.get('agent_id')
                robot_id = actor.get('robot_id')
                if message_type == 'agent_structured':
                    if not _rate_limit_ok(f"agent_struct:{agent_id}", _AGENT_STRUCTURED_LIMIT_PER_MIN):
                        return {"error": "Rate limit: agent_structured max 10/min"}, 429
        except Exception:
            pass

        if client_message_id:
            existing = find_channel_message_by_client_id(job_id, username, str(client_message_id))
            if existing:
                return existing, 200

        message_id = str(uuid.uuid4())
        now = int(time.time())
        msg = {
            'message_id': message_id,
            'job_id': job_id,
            'channel_type': 'job',
            'message_type': message_type,
            'sender': username,
            'agent_id': agent_id,
            'robot_id': robot_id,
            'body': body,
            'payload': payload,
            'sent_at': now,
            'client_message_id': str(client_message_id) if client_message_id else None,
        }
        if not save_channel_message(job_id, message_id, msg):
            return {"error": "Failed to save message"}, 500
        ch['message_count'] = int(ch.get('message_count') or 0) + 1
        ch['updated_at'] = now
        ch['last_message_at'] = now
        save_channel(job_id, ch)

        _emit('message.posted', username=username, job_id=job_id,
              actor=public_actor(username, agent={'agent_id': agent_id, 'robot_id': robot_id} if agent_id else None),
              payload={'message_type': message_type, 'message_id': message_id},
              idempotency_key=f"msg:{job_id}:{message_id}")

        return msg, 201
    except Exception as e:
        logger.error(f"Post channel message error: {e}")
        return {"error": "Internal server error"}, 500


def get_job_channel_messages(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """List/paginate job channel messages (since_ts + after_id + limit)."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        after_id = data.get('after_id')
        try:
            limit = min(int(data.get('limit') or 50), 100)
        except (TypeError, ValueError):
            return {"error": "limit must be integer"}, 400

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        ch = get_channel(job_id) or ensure_job_channel(job)
        if not ch or not _user_in_channel(username, ch):
            return {"error": "Not a channel member"}, 403

        all_msgs = list_channel_messages(job_id)
        since_raw = data.get('since_ts')
        if since_raw is not None and since_raw != '':
            try:
                since_ts = int(since_raw)
            except (TypeError, ValueError):
                return {"error": "since_ts must be integer"}, 400
            filtered = []
            for m in all_msgs:
                ts = m.get('sent_at', 0)
                mid = m.get('message_id') or ''
                if ts > since_ts:
                    filtered.append(m)
                elif ts == since_ts:
                    if after_id:
                        if mid > after_id:
                            filtered.append(m)
                    else:
                        filtered.append(m)
            all_msgs = filtered

        page = all_msgs[:limit]
        has_more = len(all_msgs) > limit
        next_since_ts = page[-1]['sent_at'] if page and has_more else None
        next_after_id = page[-1]['message_id'] if page and has_more else None
        my_read = (ch.get('read_cursors') or {}).get(username, 0)
        return {
            'job_id': job_id,
            'messages': page,
            'has_more': has_more,
            'next_since_ts': next_since_ts,
            'next_after_id': next_after_id,
            'my_read_ts': my_read,
        }, 200
    except Exception as e:
        logger.error(f"Get channel messages error: {e}")
        return {"error": "Internal server error"}, 500


def mark_job_channel_read(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Cursor-based mark-as-read for a job channel."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        last_read_ts = data.get('last_read_ts')
        if last_read_ts is None:
            return {"error": "last_read_ts required"}, 400
        try:
            last_read_ts = int(last_read_ts)
        except (TypeError, ValueError):
            return {"error": "last_read_ts must be integer"}, 400

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        ch = get_channel(job_id) or ensure_job_channel(job)
        if not ch or not _user_in_channel(username, ch):
            return {"error": "Not a channel member"}, 403
        cursors = ch.setdefault('read_cursors', {})
        prev = int(cursors.get(username) or 0)
        cursors[username] = max(prev, last_read_ts)
        ch['updated_at'] = int(time.time())
        save_channel(job_id, ch)
        return {'job_id': job_id, 'last_read_ts': cursors[username]}, 200
    except Exception as e:
        logger.error(f"Mark channel read error: {e}")
        return {"error": "Internal server error"}, 500


def mark_chat_read(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Cursor-based mark-as-read for 1:1 DM conversations."""
    try:
        username = data.get('username')
        peer = (data.get('conversation_id') or data.get('peer') or '').strip()
        last_read_ts = data.get('last_read_ts')
        if not peer:
            return {"error": "conversation_id required"}, 400
        if last_read_ts is None:
            return {"error": "last_read_ts required"}, 400
        try:
            last_read_ts = int(last_read_ts)
        except (TypeError, ValueError):
            return {"error": "last_read_ts must be integer"}, 400
        cursors = get_chat_cursors(username)
        by_peer = cursors.setdefault('by_peer', {})
        prev = int(by_peer.get(peer) or 0)
        by_peer[peer] = max(prev, last_read_ts)
        save_chat_cursors(username, cursors)
        return {'conversation_id': peer, 'last_read_ts': by_peer[peer]}, 200
    except Exception as e:
        logger.error(f"Mark chat read error: {e}")
        return {"error": "Internal server error"}, 500


# -----------------------------------------------------------------------------
# Job Party (ad-hoc per-job coalitions — supply and demand sides)
# -----------------------------------------------------------------------------
# Primary provider invites supply co-providers; primary buyer invites demand
# co-buyers when DEMAND_PARTY_ENABLED. Share is UX/attribution; demand party
# does not receive matching-reputation stars (attribution-only).

_PARTY_MIN_PROVIDER_SHARE = 0.05  # primary provider always keeps at least 5%
_PARTY_MIN_BUYER_SHARE = 0.05
_PARTY_MAX_DEMAND_ACCEPTED = 5
_PARTY_MAX_INVITES_PER_SIDE = 10


def _party_list_for_side(job, side):
    if side == 'demand':
        return job.setdefault('demand_party', [])
    party = job.setdefault('party', [])
    job['supply_party'] = party
    return party


def invite_job_party(data):
    """Invite a co-provider (side=supply) or co-buyer (side=demand) onto a job party."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        member_username = (data.get('member_username') or '').strip()
        share = data.get('share')
        side = (data.get('side') or 'supply').strip().lower()

        if side not in ('supply', 'demand'):
            return {"error": "side must be 'supply' or 'demand'"}, 400
        if side == 'demand' and not getattr(config, 'DEMAND_PARTY_ENABLED', True):
            return {"error": "Demand-side parties are disabled"}, 403

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

        job = get_job(job_id, force_refresh=True)
        if not job:
            return {"error": "Job not found"}, 404
        if job.get('status') != 'accepted':
            return {"error": "Job must be in accepted state to form a party"}, 400

        if side == 'supply':
            if job['provider_username'] != username:
                return {"error": "Only the primary provider can invite supply party members"}, 403
            required_type = 'supply'
            min_primary = _PARTY_MIN_PROVIDER_SHARE
        else:
            if job['buyer_username'] != username:
                return {"error": "Only the primary buyer can invite demand party members"}, 403
            required_type = 'demand'
            min_primary = _PARTY_MIN_BUYER_SHARE

        member_account = get_account(member_username)
        if not member_account:
            return {"error": "member_username not found"}, 404
        if member_account.get('user_type') != required_type:
            return {"error": f"Only {required_type}-type accounts can join a {side} party"}, 400

        party = _party_list_for_side(job, side)
        if any(p['member_username'] == member_username for p in party):
            return {"error": "Already invited"}, 400
        if len(party) >= _PARTY_MAX_INVITES_PER_SIDE:
            return {"error": f"Max {_PARTY_MAX_INVITES_PER_SIDE} invites per side"}, 400

        committed = sum(
            float(p['share']) for p in party
            if p.get('status') in ('invited', 'accepted') and p.get('share') is not None
        )
        available = round(1 - min_primary - committed, 4)
        if share > available:
            return {"error": f"Share exceeds available capacity (max additional share: {max(available, 0)})"}, 400

        if side == 'demand':
            accepted_count = sum(1 for p in party if p.get('status') == 'accepted')
            if accepted_count >= _PARTY_MAX_DEMAND_ACCEPTED:
                return {"error": f"Max {_PARTY_MAX_DEMAND_ACCEPTED} accepted demand party members"}, 400

        invite = {
            'member_username': member_username,
            'share': share,
            'status': 'invited',
            'side': side,
            'source': 'invite',
            'invited_at': int(time.time()),
            'responded_at': None,
        }
        party.append(invite)
        if side == 'supply':
            job['supply_party'] = party
            job['party'] = party
        save_job(job_id, job)

        related = [member_username]
        if job.get('buyer_username') and job['buyer_username'] != username:
            related.append(job['buyer_username'])
        if job.get('provider_username') and job['provider_username'] != username:
            related.append(job['provider_username'])
        _emit('party.invited', username=username, job_id=job_id,
              actor=public_actor(username),
              payload={'member_username': member_username, 'side': side, 'share': share},
              related_usernames=related,
              idempotency_key=f"party.invited:{job_id}:{side}:{member_username}")

        # System note on channel for members; invitee gets a DM (pending invitees are not channel members)
        ensure_job_channel(
            job,
            system_event='party.invited',
            system_body=f"{username} invited {member_username} to the {side} party",
            system_payload={'member_username': member_username, 'side': side, 'share': share},
        )
        try:
            send_chat_message({
                'username': username,
                'recipient': member_username,
                'message': f"You were invited to join job {job_id} as a {side} party member (share={share}). Respond via POST /jobs/{job_id}/party/respond.",
                'job_id': job_id,
            })
        except Exception:
            pass

        logger.info(f"Job party invite ({side}): {job_id} {username} -> {member_username} ({share})")
        return {
            "job_id": job_id,
            "side": side,
            "party": job.get('party', []),
            "supply_party": job.get('party', []),
            "demand_party": job.get('demand_party', []),
        }, 201
    except Exception as e:
        logger.error(f"Invite job party error: {str(e)}")
        return {"error": "Internal server error"}, 500


def respond_job_party(data):
    """Accept or decline a pending job-party invitation (supply or demand)."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        action = (data.get('action') or '').strip().lower()

        if not job_id or action not in ('accept', 'decline'):
            return {"error": "job_id and action ('accept' or 'decline') required"}, 400

        job = get_job(job_id, force_refresh=True)
        if not job:
            return {"error": "Job not found"}, 404

        invite = None
        side = 'supply'
        party = job.setdefault('party', [])
        invite = next((p for p in party if p.get('member_username') == username), None)
        if invite is None:
            dparty = job.setdefault('demand_party', [])
            invite = next((p for p in dparty if p.get('member_username') == username), None)
            if invite is not None:
                side = 'demand'
                party = dparty
        else:
            side = invite.get('side') or 'supply'

        if not invite:
            return {"error": "No invitation found for this job"}, 404
        if invite['status'] != 'invited':
            return {"error": f"Invitation already {invite['status']}"}, 400
        if job.get('status') != 'accepted':
            return {"error": f"Cannot respond to an invitation on a job with status '{job.get('status')}'"}, 400

        if side == 'demand' and action == 'accept':
            accepted_count = sum(1 for p in party if p.get('status') == 'accepted')
            if accepted_count >= _PARTY_MAX_DEMAND_ACCEPTED:
                return {"error": f"Max {_PARTY_MAX_DEMAND_ACCEPTED} accepted demand party members"}, 400

        invite['status'] = 'accepted' if action == 'accept' else 'declined'
        invite['responded_at'] = int(time.time())
        invite['side'] = side
        if side == 'supply':
            job['supply_party'] = party
            job['party'] = party
        save_job(job_id, job)

        related = [u for u in (job.get('buyer_username'), job.get('provider_username')) if u and u != username]
        _emit(f'party.{invite["status"]}', username=username, job_id=job_id,
              actor=public_actor(username),
              payload={'side': side, 'share': invite.get('share')},
              related_usernames=related,
              idempotency_key=f"party.{invite['status']}:{job_id}:{username}")

        if invite['status'] == 'accepted':
            ensure_job_channel(
                job,
                system_event='party.accepted',
                system_body=f"{username} joined the {side} party",
                system_payload={'member_username': username, 'side': side, 'share': invite.get('share')},
            )
        else:
            ensure_job_channel(
                job,
                system_event='party.declined',
                system_body=f"{username} declined the {side} party invite",
                system_payload={'member_username': username, 'side': side},
            )

        return {"job_id": job_id, "status": invite['status'], "side": side}, 200
    except Exception as e:
        logger.error(f"Respond job party error: {str(e)}")
        return {"error": "Internal server error"}, 500


def get_job_party(data):
    """View the party roster for a job (both supply and demand sides)."""
    try:
        username = data.get('username')
        job_id = data.get('job_id')

        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404

        supply_party = job.get('party') or job.get('supply_party') or []
        demand_party = job.get('demand_party') or []
        if not user_is_job_participant(username, job):
            return {"error": "Not authorized"}, 403

        def _share_sum(members):
            return sum(
                float(p['share']) for p in members
                if p.get('status') == 'accepted' and p.get('share') is not None
            )

        return {
            "job_id": job_id,
            "provider_username": job.get('provider_username'),
            "provider_share": round(1 - _share_sum(supply_party), 4),
            "buyer_username": job.get('buyer_username'),
            "buyer_share": round(1 - _share_sum(demand_party), 4),
            "party": supply_party,
            "supply_party": supply_party,
            "demand_party": demand_party,
        }, 200
    except Exception as e:
        logger.error(f"Get job party error: {str(e)}")
        return {"error": "Internal server error"}, 500


# -----------------------------------------------------------------------------
# Agent tokens (robot/operator scoped bearer auth)
# -----------------------------------------------------------------------------

def create_agent(data):
    """Create an agent token under the authenticated operator account."""
    try:
        if not getattr(config, 'AGENT_TOKENS_ENABLED', True):
            return {"error": "Agent tokens disabled"}, 403
        username = data.get('username')
        label = (data.get('label') or '').strip() or 'agent'
        robot_id = data.get('robot_id')
        scopes = data.get('scopes') or list(_DEFAULT_AGENT_SCOPES)
        expires_at = data.get('expires_at')

        if not isinstance(scopes, list) or not scopes:
            return {"error": "scopes must be a non-empty list"}, 400
        bad = [s for s in scopes if s not in _ALL_AGENT_SCOPES]
        if bad:
            return {"error": f"Invalid scopes: {bad}"}, 400

        user_data = get_account(username, force_refresh=True)
        if not user_data:
            return {"error": "User not found"}, 404

        if robot_id:
            robots = user_data.get('robots_owned') or []
            if not any(r.get('id') == robot_id for r in robots):
                return {"error": "robot_id must match an existing robots_owned[].id"}, 400

        meta = user_data.setdefault('agents_meta', [])
        active = [a for a in meta if not a.get('revoked_at')]
        if len(active) >= _MAX_AGENTS_PER_ACCOUNT:
            return {"error": f"Max {_MAX_AGENTS_PER_ACCOUNT} agents per account"}, 400

        agent_id = str(uuid.uuid4())
        secret = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(secret.encode()).hexdigest()
        now = int(time.time())
        # Default expiry when not provided (security: no infinite agent tokens)
        if expires_at is None:
            default_days = int(getattr(config, 'AGENT_TOKEN_DEFAULT_EXPIRY_DAYS', 90) or 0)
            if default_days > 0:
                expires_at = now + default_days * 86400
        record = {
            'agent_id': agent_id,
            'username': username,
            'scopes': scopes,
            'robot_id': robot_id,
            'expires_at': expires_at,
            'revoked': False,
            'created_at': now,
            'label': label,
        }
        if not save_agent_token_record(token_hash, record):
            return {"error": "Failed to store agent token"}, 500

        meta.append({
            'agent_id': agent_id,
            'label': label,
            'robot_id': robot_id,
            'scopes': scopes,
            'created_at': now,
            'expires_at': expires_at,
            'revoked_at': None,
            'token_hash': token_hash,
        })
        save_account(username, user_data)

        _emit('agent.created', username=username, actor=public_actor(username, agent=record),
              payload={'agent_id': agent_id, 'scopes': scopes},
              idempotency_key=f"agent.created:{agent_id}")

        return {
            'agent_id': agent_id,
            'agent_token': secret,
            'scopes': scopes,
            'robot_id': robot_id,
            'label': label,
            'created_at': now,
            'expires_at': expires_at,
        }, 201
    except Exception as e:
        logger.error(f"Create agent error: {str(e)}")
        return {"error": "Internal server error"}, 500


def list_agents(data):
    try:
        username = data.get('username')
        # force_refresh: multi-worker cache otherwise returns stale empty agents_meta
        user_data = get_account(username, force_refresh=True)
        if not user_data:
            return {"error": "User not found"}, 404
        agents = []
        for a in user_data.get('agents_meta') or []:
            agents.append({
                'agent_id': a.get('agent_id'),
                'label': a.get('label'),
                'robot_id': a.get('robot_id'),
                'scopes': a.get('scopes'),
                'created_at': a.get('created_at'),
                'expires_at': a.get('expires_at'),
                'revoked_at': a.get('revoked_at'),
            })
        return {'agents': agents}, 200
    except Exception as e:
        logger.error(f"List agents error: {str(e)}")
        return {"error": "Internal server error"}, 500


def revoke_agent(data):
    try:
        username = data.get('username')
        agent_id = data.get('agent_id')
        user_data = get_account(username, force_refresh=True)
        if not user_data:
            return {"error": "User not found"}, 404
        meta = user_data.get('agents_meta') or []
        row = next((a for a in meta if a.get('agent_id') == agent_id), None)
        if not row:
            return {"error": "Agent not found"}, 404
        th = row.get('token_hash')
        if th:
            rec = get_agent_token_record(th)
            if rec:
                rec['revoked'] = True
                save_agent_token_record(th, rec)
        row['revoked_at'] = int(time.time())
        save_account(username, user_data)
        return {'agent_id': agent_id, 'revoked': True}, 200
    except Exception as e:
        logger.error(f"Revoke agent error: {str(e)}")
        return {"error": "Internal server error"}, 500


def rotate_agent(data):
    try:
        username = data.get('username')
        agent_id = data.get('agent_id')
        user_data = get_account(username, force_refresh=True)
        if not user_data:
            return {"error": "User not found"}, 404
        meta = user_data.get('agents_meta') or []
        row = next((a for a in meta if a.get('agent_id') == agent_id), None)
        if not row or row.get('revoked_at'):
            return {"error": "Agent not found or revoked"}, 404
        old_hash = row.get('token_hash')
        if old_hash:
            delete_agent_token_record(old_hash)
        secret = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(secret.encode()).hexdigest()
        record = {
            'agent_id': agent_id,
            'username': username,
            'scopes': row.get('scopes') or list(_DEFAULT_AGENT_SCOPES),
            'robot_id': row.get('robot_id'),
            'expires_at': row.get('expires_at'),
            'revoked': False,
            'created_at': row.get('created_at'),
            'label': row.get('label'),
            'rotated_at': int(time.time()),
        }
        save_agent_token_record(token_hash, record)
        row['token_hash'] = token_hash
        save_account(username, user_data)
        return {'agent_id': agent_id, 'agent_token': secret, 'scopes': record['scopes']}, 200
    except Exception as e:
        logger.error(f"Rotate agent error: {str(e)}")
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

        campaign = get_campaign(campaign_id, force_refresh=True)
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

        campaign = get_campaign(campaign_id, force_refresh=True)
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
            'party': [],
            'supply_party': [],
            'demand_party': [],
            'provider_seat_token_id': (provider_data or {}).get('seat_token_id'),
        }
        _copy_sponsors_to_demand_party(job_record, campaign)
        save_job(job_id, job_record)
        ensure_job_channel(
            job_record,
            system_event='campaign.commitment_accepted',
            system_body=f"Campaign commitment accepted — job opened ({commitment['units']} units)",
            system_payload={
                'campaign_id': campaign_id,
                'commitment_id': commitment_id,
                'units': commitment['units'],
            },
        )

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

        supply_collab: Dict[str, int] = {}
        demand_collab: Dict[str, int] = {}
        for j in completed_jobs:
            supply_members = [p for p in (j.get('party') or j.get('supply_party') or []) if p.get('status') == 'accepted']
            demand_members = [p for p in (j.get('demand_party') or []) if p.get('status') == 'accepted']
            for member in supply_members:
                u = member.get('member_username')
                if u:
                    supply_collab[u] = supply_collab.get(u, 0) + 1
            if supply_members and j.get('provider_username'):
                pu = j['provider_username']
                supply_collab[pu] = supply_collab.get(pu, 0) + 1
            for member in demand_members:
                u = member.get('member_username')
                if u:
                    demand_collab[u] = demand_collab.get(u, 0) + 1
            if demand_members and j.get('buyer_username'):
                bu = j['buyer_username']
                demand_collab[bu] = demand_collab.get(bu, 0) + 1
        top_collaborators = [
            {'username': u, 'party_jobs_completed': n}
            for u, n in sorted(supply_collab.items(), key=lambda kv: kv[1], reverse=True)
        ]
        top_demand_collaborators = [
            {'username': u, 'demand_party_jobs_completed': n}
            for u, n in sorted(demand_collab.items(), key=lambda kv: kv[1], reverse=True)
        ]

        return {
            "top_reputation": rep_ranked[:10],
            "top_campaign_fulfillers": top_campaign_fulfillers[:10],
            "top_collaborators": top_collaborators[:10],
            "top_demand_collaborators": top_demand_collaborators[:10],
        }, 200
    except Exception as e:
        logger.error(f"Get leaderboard error: {str(e)}")
        return {"error": "Internal server error"}, 500



# -----------------------------------------------------------------------------
# Stage C — Activity read, portfolio, export, proofs
# -----------------------------------------------------------------------------

def get_activity_me(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Authenticated activity feed (index with canonical scan fallback)."""
    try:
        username = data.get('username')
        limit = min(int(data.get('limit') or 50), 100)
        since = data.get('since')
        since_i = int(since) if since not in (None, '') else None
        events = list_activity_for_user(username, limit=limit, since=since_i)
        return {
            'events': events,
            'count': len(events),
            'note': 'Activity is append-only telemetry; marketplace job/bid records remain source of truth.',
        }, 200
    except Exception as e:
        logger.error(f"get_activity_me error: {e}")
        return {"error": "Internal server error"}, 500


def get_activity_for_job(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Activity events for a job — participants only."""
    try:
        from utils import _s3_list, _s3_get, ACTIVITY_JOB_INDEX_PREFIX
        username = data.get('username')
        job_id = data.get('job_id')
        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        if not user_is_job_participant(username, job):
            return {"error": "Not authorized"}, 403
        limit = min(int(data.get('limit') or 50), 100)
        prefix = f"{ACTIVITY_JOB_INDEX_PREFIX}/{job_id}/"
        keys = sorted(_s3_list(prefix), reverse=True)[:limit * 2]
        events = []
        for key in keys:
            if not key.endswith('.json'):
                continue
            idx = _s3_get(key)
            if not idx:
                continue
            path = idx.get('path')
            ev = _s3_get(path) if path else None
            if ev:
                events.append(ev)
            if len(events) >= limit:
                break
        return {'job_id': job_id, 'events': events}, 200
    except Exception as e:
        logger.error(f"get_activity_for_job error: {e}")
        return {"error": "Internal server error"}, 500


def _public_completion_cards(username: str, limit: int = 20) -> List[Dict[str, Any]]:
    jobs = get_user_jobs(username, include_party=True)
    cards = []
    for job in jobs:
        if job.get('status') != 'completed':
            continue
        if username == job.get('buyer_username'):
            counter = job.get('provider_username')
            role = 'buyer'
            rating = job.get('provider_rating')  # rating they received from provider
        elif username == job.get('provider_username'):
            counter = job.get('buyer_username')
            role = 'provider'
            rating = job.get('buyer_rating')
        else:
            side = _user_on_job_party(username, job, accepted_only=True)
            if not side:
                continue
            role = 'co_buyer' if side == 'demand' else 'co_provider'
            counter = job.get('provider_username') if side == 'demand' else job.get('buyer_username')
            rating = None  # attribution-only for demand; supply co-providers may have stars on account
        counter_actor = public_actor(counter) if counter else {}
        cards.append({
            'job_id': job.get('job_id'),
            'service': job.get('service'),
            'price': job.get('price'),
            'currency': job.get('currency', 'USD'),
            'completed_at': job.get('completed_at'),
            'role': role,
            'counterparty_public_id': counter_actor.get('public_id'),
            'counterparty_username': counter,
            'supply_party_size': len([p for p in (job.get('party') or job.get('supply_party') or []) if p.get('status') == 'accepted']),
            'demand_party_size': len([p for p in (job.get('demand_party') or []) if p.get('status') == 'accepted']),
            'rating_received': rating,
            'attribution_only': role == 'co_buyer',
        })
    cards.sort(key=lambda c: c.get('completed_at') or 0, reverse=True)
    return cards[:limit]


def get_portfolio(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Public portfolio by username (or authenticated self)."""
    try:
        if not getattr(config, 'PUBLIC_PORTFOLIO_ENABLED', True):
            # Still allow authenticated owner to view own portfolio when flag false
            pass
        target = (data.get('target_username') or data.get('username') or '').strip()
        viewer = data.get('viewer')
        if not target:
            return {"error": "username required"}, 400
        acc = get_account(target)
        if not acc:
            return {"error": "User not found"}, 404
        identity = public_actor(target)
        breakdown = _reputation_breakdown(target)
        cards = _public_completion_cards(target)
        endo = get_endorsements(target) or {}
        # endorsements structure varies - normalize lightly
        skills = []
        if isinstance(endo, dict):
            skills = endo.get('skills') or endo.get('top_skills') or []
        resp = {
            'username': target,
            'identity': identity,
            'user_type': acc.get('user_type'),
            'reputation_score': round(calculate_reputation_score(acc), 2),
            'total_ratings': acc.get('total_ratings', 0),
            'completed_jobs': acc.get('completed_jobs', 0),
            'reputation_breakdown': breakdown,
            'completions': cards,
            'endorsements_summary': skills[:10] if isinstance(skills, list) else [],
            'display_name': acc.get('display_name'),
            'about': acc.get('about'),
            'location': acc.get('location'),
            'profile_slug': acc.get('profile_slug'),
        }
        if identity.get('seat_token_id') is not None and identity.get('public_id', '').startswith('seat:'):
            resp['canonical_portfolio'] = f"/portfolio/seat/{identity['seat_token_id']}"
        return resp, 200
    except Exception as e:
        logger.error(f"get_portfolio error: {e}")
        return {"error": "Internal server error"}, 500


def get_portfolio_by_seat(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Public portfolio by seat token id."""
    try:
        token_id = data.get('token_id')
        try:
            token_id = int(token_id)
        except (TypeError, ValueError):
            return {"error": "token_id must be integer"}, 400
        # Scan accounts for matching seat_token_id (acceptable for Stage C scale)
        owner = None
        for uname, acc in get_all_accounts():
            if acc.get('seat_token_id') == token_id:
                owner = uname
                break
        if not owner:
            return {"error": "Seat portfolio not found"}, 404
        resp, status = get_portfolio({'target_username': owner})
        if status == 200:
            resp['seat_token_id'] = token_id
            resp['canonical'] = True
        return resp, status
    except Exception as e:
        logger.error(f"get_portfolio_by_seat error: {e}")
        return {"error": "Internal server error"}, 500


def export_history(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Authenticated private history export (bids + jobs + activity sample)."""
    try:
        username = data.get('username')
        bids = get_user_bids(username)
        jobs = get_user_jobs(username)
        act, _ = get_activity_me({'username': username, 'limit': 100})
        export = {
            'exported_at': int(time.time()),
            'username': username,
            'identity': public_actor(username),
            'bids': bids,
            'jobs': jobs,
            'activity': (act or {}).get('events', []),
            'schema_version': 1,
        }
        return export, 200
    except Exception as e:
        logger.error(f"export_history error: {e}")
        return {"error": "Internal server error"}, 500


def export_job_proof(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Participant-only completion/participation proof for a job."""
    try:
        import hashlib as _hashlib
        username = data.get('username')
        job_id = data.get('job_id')
        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        if not user_is_job_participant(username, job):
            return {"error": "Not authorized"}, 403

        def _member_cards(members, side):
            out = []
            for m in members or []:
                if m.get('status') != 'accepted':
                    continue
                actor = public_actor(m['member_username'])
                out.append({
                    'username': m['member_username'],
                    'public_id': actor.get('public_id'),
                    'share': m.get('share'),
                    'side': side,
                })
            return out

        body = {
            'job_id': job_id,
            'status': job.get('status'),
            'service': job.get('service'),
            'price': job.get('price'),
            'currency': job.get('currency', 'USD'),
            'buyer': public_actor(job.get('buyer_username') or ''),
            'provider': public_actor(job.get('provider_username') or ''),
            'provider_seat_token_id': job.get('provider_seat_token_id'),
            'accepted_at': job.get('accepted_at'),
            'completed_at': job.get('completed_at'),
            'ratings': {
                'buyer': job.get('buyer_rating'),
                'provider': job.get('provider_rating'),
            },
            'supply_party': _member_cards(job.get('party') or job.get('supply_party'), 'supply'),
            'demand_party': _member_cards(job.get('demand_party'), 'demand'),
            'campaign_id': job.get('campaign_id'),
            'schema_version': 1,
            'issued_at': int(time.time()),
            'issued_to': username,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        content_hash = _hashlib.sha256(canonical.encode()).hexdigest()
        body['integrity'] = {
            'schema_version': 1,
            'content_hash': f'sha256:{content_hash}',
        }
        # Optional HMAC if configured
        key = getattr(config, 'RSE_PROOF_SIGNING_KEY', None) or ''
        if key:
            import hmac as _hmac
            sig = _hmac.new(key.encode(), content_hash.encode(), _hashlib.sha256).hexdigest()
            body['integrity']['hmac_sha256'] = sig
        return body, 200
    except Exception as e:
        logger.error(f"export_job_proof error: {e}")
        return {"error": "Internal server error"}, 500



# -----------------------------------------------------------------------------
# Campaign sponsors (multi-buyer demand on campaigns → demand_party on jobs)
# -----------------------------------------------------------------------------

def invite_campaign_sponsor(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Campaign owner invites another demand account as co-sponsor."""
    try:
        if not getattr(config, 'CAMPAIGN_SPONSORS_ENABLED', True):
            return {"error": "Campaign sponsors are disabled"}, 403
        username = data.get('username')
        campaign_id = data.get('campaign_id')
        member_username = (data.get('member_username') or '').strip()
        if not campaign_id or not member_username:
            return {"error": "campaign_id and member_username required"}, 400
        if member_username == username:
            return {"error": "Cannot invite yourself"}, 400
        campaign = get_campaign(campaign_id, force_refresh=True)
        if not campaign:
            return {"error": "Campaign not found"}, 404
        if campaign.get('owner_username') != username:
            return {"error": "Only the campaign owner can invite sponsors"}, 403
        member = get_account(member_username)
        if not member or member.get('user_type') != 'demand':
            return {"error": "Sponsors must be demand-type accounts"}, 400
        sponsors = campaign.setdefault('sponsors', [])
        if any(s.get('member_username') == member_username for s in sponsors):
            return {"error": "Already invited"}, 400
        if len(sponsors) >= 20:
            return {"error": "Max 20 sponsor invites"}, 400
        row = {
            'member_username': member_username,
            'status': 'invited',
            'invited_at': int(time.time()),
            'responded_at': None,
            'share': None,
        }
        sponsors.append(row)
        save_campaign(campaign_id, campaign)
        _emit('campaign.sponsor_invited', username=username,
              actor=public_actor(username),
              payload={'campaign_id': campaign_id, 'member_username': member_username},
              related_usernames=[member_username],
              idempotency_key=f"campaign.sponsor_invited:{campaign_id}:{member_username}")
        try:
            send_chat_message({
                'username': username,
                'recipient': member_username,
                'message': f"You were invited as co-sponsor on campaign {campaign_id} ({campaign.get('title')}). Respond via POST /campaigns/{campaign_id}/sponsors/respond.",
            })
        except Exception:
            pass
        return {'campaign_id': campaign_id, 'sponsors': sponsors}, 201
    except Exception as e:
        logger.error(f"invite_campaign_sponsor: {e}")
        return {"error": "Internal server error"}, 500


def respond_campaign_sponsor(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Accept or decline a campaign co-sponsor invite."""
    try:
        if not getattr(config, 'CAMPAIGN_SPONSORS_ENABLED', True):
            return {"error": "Campaign sponsors are disabled"}, 403
        username = data.get('username')
        campaign_id = data.get('campaign_id')
        action = (data.get('action') or '').strip().lower()
        if action not in ('accept', 'decline'):
            return {"error": "action must be accept or decline"}, 400
        campaign = get_campaign(campaign_id, force_refresh=True)
        if not campaign:
            return {"error": "Campaign not found"}, 404
        sponsors = campaign.setdefault('sponsors', [])
        row = next((s for s in sponsors if s.get('member_username') == username), None)
        if not row:
            return {"error": "No sponsor invitation found"}, 404
        if row.get('status') != 'invited':
            return {"error": f"Invitation already {row.get('status')}"}, 400
        row['status'] = 'accepted' if action == 'accept' else 'declined'
        row['responded_at'] = int(time.time())
        save_campaign(campaign_id, campaign)
        _emit(f'campaign.sponsor_{row["status"]}', username=username,
              actor=public_actor(username),
              payload={'campaign_id': campaign_id},
              related_usernames=[campaign.get('owner_username')],
              idempotency_key=f"campaign.sponsor_{row['status']}:{campaign_id}:{username}")
        return {'campaign_id': campaign_id, 'status': row['status']}, 200
    except Exception as e:
        logger.error(f"respond_campaign_sponsor: {e}")
        return {"error": "Internal server error"}, 500


def get_campaign_sponsors(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """List sponsors for a campaign (public on open campaigns; owner always)."""
    try:
        campaign_id = data.get('campaign_id')
        campaign = get_campaign(campaign_id, force_refresh=True)
        if not campaign:
            return {"error": "Campaign not found"}, 404
        return {
            'campaign_id': campaign_id,
            'owner_username': campaign.get('owner_username'),
            'sponsors': campaign.get('sponsors') or [],
        }, 200
    except Exception as e:
        logger.error(f"get_campaign_sponsors: {e}")
        return {"error": "Internal server error"}, 500


def _copy_sponsors_to_demand_party(job_record: Dict[str, Any], campaign: Dict[str, Any]) -> None:
    """KD-7: copy up to 5 accepted sponsors onto job demand_party with share=null."""
    sponsors = [s for s in (campaign.get('sponsors') or []) if s.get('status') == 'accepted']
    sponsors.sort(key=lambda s: (s.get('responded_at') or 0, s.get('member_username') or ''))
    chosen = sponsors[:5]
    if len(sponsors) > 5:
        logger.info(f"campaign_sponsor_job_copy_truncated count={len(sponsors)-5}")
    demand = job_record.setdefault('demand_party', [])
    now = int(time.time())
    for s in chosen:
        uname = s.get('member_username')
        if not uname or any(p.get('member_username') == uname for p in demand):
            continue
        demand.append({
            'member_username': uname,
            'share': None,
            'status': 'accepted',
            'side': 'demand',
            'source': 'campaign_sponsor',
            'invited_at': s.get('invited_at') or now,
            'responded_at': s.get('responded_at') or now,
        })
    job_record['demand_party'] = demand


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

        ensure_job_channel(
            job,
            system_event='dispute.filed',
            system_body=f"Dispute filed by {username}: {reason[:200]}",
            system_payload={'dispute_id': dispute['dispute_id'], 'filed_by': username},
        )
        _emit('dispute.filed', username=username, job_id=job_id,
              actor=public_actor(username),
              payload={'dispute_id': dispute['dispute_id']},
              idempotency_key=f"dispute.filed:{dispute['dispute_id']}")

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

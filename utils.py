"""
Utility functions for Service Exchange - Digital Ocean Spaces Storage
----------------------------------------------------------------------
Handles Digital Ocean Spaces-based persistence for the application.
All data stored in Digital Ocean Spaces (S3-compatible) for durability and scalability.
"""

import json
import time
import logging
import boto3
from botocore.exceptions import ClientError
from typing import Dict, List, Optional, Any, Tuple
import config

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# In-memory TTL Cache
# -----------------------------------------------------------------------------

_mem_cache: Dict[str, Any] = {}
_mem_cache_ts: Dict[str, float] = {}

# TTL per key prefix (seconds)
_TTL_ACCOUNTS = 60
_TTL_TOKENS = 300
_TTL_BIDS = 30
_TTL_JOBS = 30
_TTL_STATS = 30


def _cache_ttl_for(key: str) -> float:
    if '/accounts/' in key:
        return _TTL_ACCOUNTS
    if '/tokens/' in key:
        return _TTL_TOKENS
    if '/bids/' in key:
        return _TTL_BIDS
    if '/jobs/' in key:
        return _TTL_JOBS
    return _TTL_STATS


def _cache_get(key: str) -> Optional[Any]:
    ts = _mem_cache_ts.get(key, 0)
    if time.time() - ts < _cache_ttl_for(key):
        return _mem_cache.get(key)
    return None


def _cache_set(key: str, value: Any) -> None:
    _mem_cache[key] = value
    _mem_cache_ts[key] = time.time()


def _cache_delete(key: str) -> None:
    _mem_cache.pop(key, None)
    _mem_cache_ts.pop(key, None)

# Parse Digital Ocean Spaces URL to extract bucket and region
# Format: https://{bucket}.{region}.digitaloceanspaces.com
def _parse_do_url(url: str):
    """Extract bucket name and region from Digital Ocean Spaces URL."""
    url = url.replace('https://', '').replace('http://', '')
    parts = url.split('.')
    if len(parts) >= 3 and 'digitaloceanspaces' in url:
        bucket = parts[0]
        region = parts[1]
        return bucket, region
    raise ValueError(f"Invalid Digital Ocean Spaces URL: {url}")

DO_BUCKET, DO_REGION = _parse_do_url(config.DO_SPACES_URL)
DO_ENDPOINT = f"https://{DO_REGION}.digitaloceanspaces.com"

# Initialize Digital Ocean Spaces client (S3-compatible)
try:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=config.DO_SPACES_KEY,
        aws_secret_access_key=config.DO_SPACES_SECRET,
        endpoint_url=DO_ENDPOINT,
        region_name=DO_REGION
    )
    logger.info(f"Digital Ocean Spaces client initialized: bucket={DO_BUCKET}, region={DO_REGION}, prefix={config.S3_PREFIX}")
except Exception as e:
    logger.error(f"Failed to initialize Digital Ocean Spaces client: {e}")
    raise

# S3 path prefixes (keeping S3 naming for compatibility)
S3_BUCKET = DO_BUCKET
S3_PREFIX = config.S3_PREFIX
ACCOUNTS_PREFIX = f"{S3_PREFIX}/accounts"
TOKENS_PREFIX = f"{S3_PREFIX}/tokens"
BIDS_PREFIX = f"{S3_PREFIX}/bids"
JOBS_PREFIX = f"{S3_PREFIX}/jobs"
MESSAGES_PREFIX = f"{S3_PREFIX}/messages"
BULLETINS_PREFIX = f"{S3_PREFIX}/bulletins"
FEEDBACK_KEY = f"{S3_PREFIX}/feedback/posts.json"
FINANCING_KEY = f"{S3_PREFIX}/financing/applications.json"
FOLLOWS_PREFIX = f"{S3_PREFIX}/follows"
SLUGS_PREFIX = f"{S3_PREFIX}/slugs"
AVATARS_PREFIX = f"{S3_PREFIX}/avatars"
SHOP_ORDERS_KEY = f"{S3_PREFIX}/shop/orders.json"
CAMPAIGNS_PREFIX = f"{S3_PREFIX}/campaigns"
ENDORSEMENTS_PREFIX = f"{S3_PREFIX}/endorsements"
DISPUTES_KEY = f"{S3_PREFIX}/disputes/list.json"
AGENT_TOKENS_PREFIX = f"{S3_PREFIX}/agent_tokens"
ACTIVITY_PREFIX = f"{S3_PREFIX}/activity"
ACTIVITY_USER_INDEX_PREFIX = f"{S3_PREFIX}/activity_index/users"
ACTIVITY_JOB_INDEX_PREFIX = f"{S3_PREFIX}/activity_index/jobs"
CHANNELS_PREFIX = f"{S3_PREFIX}/channels"
CHANNEL_MESSAGES_PREFIX = f"{S3_PREFIX}/channel_messages"
CHAT_CURSORS_PREFIX = f"{S3_PREFIX}/chat_cursors"

# -----------------------------------------------------------------------------
# S3 Helper Functions
# -----------------------------------------------------------------------------

def _s3_put(key: str, data: Dict[str, Any]) -> bool:
    """Save JSON data to S3 and update cache."""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        _cache_set(key, data)
        return True
    except ClientError as e:
        logger.error(f"S3 PUT error for {key}: {e}")
        return False

def _s3_put_binary(key: str, body: bytes, content_type: str) -> bool:
    """Save raw binary data to S3 (e.g. uploaded images), publicly readable."""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=body,
            ContentType=content_type,
            ACL='public-read'
        )
        return True
    except ClientError as e:
        logger.error(f"S3 binary PUT error for {key}: {e}")
        return False

def _s3_get(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve JSON data from S3, with in-memory TTL cache."""
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(response['Body'].read().decode('utf-8'))
        _cache_set(key, data)
        return data
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return None
        logger.error(f"S3 GET error for {key}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {key}: {e}")
        return None

def _s3_exists(key: str) -> bool:
    """Check if an object exists in S3 (cache-aware)."""
    if _cache_get(key) is not None:
        return True
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError:
        return False

def _s3_delete(key: str) -> bool:
    """Delete an object from S3 and evict cache."""
    try:
        s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
        _cache_delete(key)
        return True
    except ClientError as e:
        logger.error(f"S3 DELETE error for {key}: {e}")
        return False

def _s3_list(prefix: str) -> List[str]:
    """List all objects with a given prefix."""
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix)
        
        keys = []
        for page in pages:
            if 'Contents' in page:
                keys.extend([obj['Key'] for obj in page['Contents']])
        return keys
    except ClientError as e:
        logger.error(f"S3 LIST error for prefix {prefix}: {e}")
        return []

# -----------------------------------------------------------------------------
# Account Management
# -----------------------------------------------------------------------------

def save_account(username: str, data: Dict[str, Any]) -> None:
    """Save account data to S3."""
    key = f"{ACCOUNTS_PREFIX}/{username}.json"
    if not _s3_put(key, data):
        logger.error(f"Failed to save account {username}")

def get_account(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve account data from S3."""
    key = f"{ACCOUNTS_PREFIX}/{username}.json"
    return _s3_get(key)

def account_exists(username: str) -> bool:
    """Check if an account exists in S3."""
    key = f"{ACCOUNTS_PREFIX}/{username}.json"
    return _s3_exists(key)

def get_all_accounts() -> List[Tuple[str, Dict[str, Any]]]:
    """Retrieve all accounts as (username, data) pairs from S3. Full scan — used for admin/leaderboard views."""
    accounts = []
    try:
        keys = _s3_list(ACCOUNTS_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                data = _s3_get(key)
                if data:
                    username = key.rsplit('/', 1)[-1][:-5]
                    accounts.append((username, data))
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
    return accounts

def get_signup_stats() -> Dict[str, int]:
    """Get counts of demand and supply signups from S3."""
    stats = {'demand': 0, 'supply': 0, 'total': 0}
    try:
        keys = _s3_list(ACCOUNTS_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                account = _s3_get(key)
                if account:
                    user_type = account.get('user_type', '')
                    if user_type == 'demand':
                        stats['demand'] += 1
                    elif user_type == 'supply':
                        stats['supply'] += 1
                    stats['total'] += 1
    except Exception as e:
        logger.error(f"Error getting signup stats: {e}")
    return stats

# -----------------------------------------------------------------------------
# Token Management
# -----------------------------------------------------------------------------

def save_token(token: str, username: str, expiry: int) -> None:
    """Save authentication token to S3."""
    key = f"{TOKENS_PREFIX}/{token}.json"
    if not _s3_put(key, {'username': username, 'expiry': expiry}):
        logger.error(f"Failed to save token")

def get_token_username(token: str) -> Optional[str]:
    """Retrieve username from valid token in S3."""
    key = f"{TOKENS_PREFIX}/{token}.json"
    data = _s3_get(key)
    if data and data.get('expiry', 0) > time.time():
        return data.get('username')
    return None

# -----------------------------------------------------------------------------
# Agent tokens (sha256 lookup; secrets never stored)
# -----------------------------------------------------------------------------

def save_agent_token_record(token_hash: str, record: Dict[str, Any]) -> bool:
    """Persist agent auth record keyed by sha256 hex of the bearer secret."""
    key = f"{AGENT_TOKENS_PREFIX}/{token_hash}.json"
    return _s3_put(key, record)

def get_agent_token_record(token_hash: str) -> Optional[Dict[str, Any]]:
    key = f"{AGENT_TOKENS_PREFIX}/{token_hash}.json"
    return _s3_get(key)

def delete_agent_token_record(token_hash: str) -> bool:
    key = f"{AGENT_TOKENS_PREFIX}/{token_hash}.json"
    return _s3_delete(key)

# -----------------------------------------------------------------------------
# Activity events (append-only; best-effort relative to marketplace)
# -----------------------------------------------------------------------------

def append_activity_event(
    event_type: str,
    *,
    username: Optional[str] = None,
    job_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    actor: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Optional[str]:
    """
    Best-effort append of an activity event. Returns event_id or None on failure.
    Marketplace callers must not fail the parent action if this returns None.
    """
    if not getattr(config, 'ACTIVITY_LOG_ENABLED', True):
        return None
    try:
        import uuid as _uuid
        if idempotency_key:
            event_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"rse:{idempotency_key}"))
        else:
            event_id = str(_uuid.uuid4())
        now = int(time.time())
        ts = time.gmtime(now)
        yyyy, mm = time.strftime('%Y', ts), time.strftime('%m', ts)
        body = {
            'event_id': event_id,
            'event_type': event_type,
            'created_at': now,
            'username': username,
            'job_id': job_id,
            'actor': actor,
            'payload': payload or {},
            'idempotency_key': idempotency_key,
        }
        body_key = f"{ACTIVITY_PREFIX}/{yyyy}/{mm}/{event_id}.json"
        if not _s3_put(body_key, body):
            logger.error(f"activity_append_fail body {event_type}")
            return None
        # Secondary indexes (best-effort)
        try:
            if username:
                idx_key = f"{ACTIVITY_USER_INDEX_PREFIX}/{username}/{now}_{event_id}.json"
                _s3_put(idx_key, {'event_id': event_id, 'event_type': event_type, 'created_at': now, 'path': body_key})
            if job_id:
                jidx = f"{ACTIVITY_JOB_INDEX_PREFIX}/{job_id}/{now}_{event_id}.json"
                _s3_put(jidx, {'event_id': event_id, 'event_type': event_type, 'created_at': now, 'path': body_key})
        except Exception as idx_err:
            logger.warning(f"activity index put failed: {idx_err}")
        return event_id
    except Exception as e:
        logger.error(f"activity_append_fail {event_type}: {e}")
        return None

# -----------------------------------------------------------------------------
# Bid Management
# -----------------------------------------------------------------------------

def save_bid(bid_id: str, data: Dict[str, Any]) -> None:
    """Save bid data to S3."""
    key = f"{BIDS_PREFIX}/{bid_id}.json"
    if not _s3_put(key, data):
        logger.error(f"Failed to save bid {bid_id}")

def get_bid(bid_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve bid data from S3."""
    key = f"{BIDS_PREFIX}/{bid_id}.json"
    return _s3_get(key)

def delete_bid(bid_id: str) -> None:
    """Delete a bid from S3."""
    key = f"{BIDS_PREFIX}/{bid_id}.json"
    if not _s3_delete(key):
        logger.error(f"Failed to delete bid {bid_id}")

def get_all_bids() -> List[Dict[str, Any]]:
    """Retrieve all active bids from S3."""
    bids = []
    try:
        keys = _s3_list(BIDS_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                bid = _s3_get(key)
                if bid:
                    bids.append(bid)
    except Exception as e:
        logger.error(f"Error loading bids: {e}")
    return bids

def get_user_bids(username: str) -> List[Dict[str, Any]]:
    """Retrieve all bids for a specific user from S3."""
    return [bid for bid in get_all_bids() if bid.get('username') == username]

# -----------------------------------------------------------------------------
# Job Management
# -----------------------------------------------------------------------------

def save_job(job_id: str, data: Dict[str, Any]) -> None:
    """Save job data to S3."""
    key = f"{JOBS_PREFIX}/{job_id}.json"
    if not _s3_put(key, data):
        logger.error(f"Failed to save job {job_id}")

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve job data from S3."""
    key = f"{JOBS_PREFIX}/{job_id}.json"
    return _s3_get(key)

def get_all_jobs() -> List[Dict[str, Any]]:
    """Retrieve all jobs from S3."""
    jobs = []
    try:
        keys = _s3_list(JOBS_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                job = _s3_get(key)
                if job:
                    jobs.append(job)
    except Exception as e:
        logger.error(f"Error loading jobs: {e}")
    return jobs

def get_user_jobs(username: str) -> List[Dict[str, Any]]:
    """Retrieve jobs for a user (as buyer or provider) from S3."""
    return [
        job for job in get_all_jobs() 
        if job.get('buyer_username') == username or job.get('provider_username') == username
    ]

def delete_job(job_id: str) -> None:
    """Delete a job from S3."""
    key = f"{JOBS_PREFIX}/{job_id}.json"
    if not _s3_delete(key):
        logger.error(f"Failed to delete job {job_id}")

# -----------------------------------------------------------------------------
# Message Management
# -----------------------------------------------------------------------------

def save_message(message_id: str, data: Dict[str, Any]) -> None:
    """Save a message to S3."""
    key = f"{MESSAGES_PREFIX}/{message_id}.json"
    if not _s3_put(key, data):
        logger.error(f"Failed to save message {message_id}")

def get_user_messages(username: str) -> List[Dict[str, Any]]:
    """Retrieve messages for a user from S3."""
    messages = []
    seen_ids: set = set()
    try:
        keys = _s3_list(MESSAGES_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                msg = _s3_get(key)
                if msg and (msg.get('sender') == username or msg.get('recipient') == username):
                    msg_id = msg.get('message_id')
                    if msg_id not in seen_ids:
                        seen_ids.add(msg_id)
                        messages.append(msg)
    except Exception as e:
        logger.error(f"Error loading messages: {e}")
    return messages

# -----------------------------------------------------------------------------
# Job channels
# -----------------------------------------------------------------------------

def save_channel(job_id: str, data: Dict[str, Any]) -> bool:
    key = f"{CHANNELS_PREFIX}/{job_id}.json"
    return _s3_put(key, data)

def get_channel(job_id: str) -> Optional[Dict[str, Any]]:
    key = f"{CHANNELS_PREFIX}/{job_id}.json"
    return _s3_get(key)

def save_channel_message(job_id: str, message_id: str, data: Dict[str, Any]) -> bool:
    key = f"{CHANNEL_MESSAGES_PREFIX}/{job_id}/{message_id}.json"
    return _s3_put(key, data)

def get_channel_message(job_id: str, message_id: str) -> Optional[Dict[str, Any]]:
    key = f"{CHANNEL_MESSAGES_PREFIX}/{job_id}/{message_id}.json"
    return _s3_get(key)

def list_channel_messages(job_id: str) -> List[Dict[str, Any]]:
    """Load all messages for a job channel (caller paginates/filters)."""
    messages = []
    prefix = f"{CHANNEL_MESSAGES_PREFIX}/{job_id}/"
    try:
        for key in _s3_list(prefix):
            if key.endswith('.json'):
                msg = _s3_get(key)
                if msg:
                    messages.append(msg)
    except Exception as e:
        logger.error(f"Error listing channel messages for {job_id}: {e}")
    messages.sort(key=lambda m: (m.get('sent_at', 0), m.get('message_id', '')))
    return messages

def find_channel_message_by_client_id(job_id: str, sender: str, client_message_id: str) -> Optional[Dict[str, Any]]:
    if not client_message_id:
        return None
    for msg in list_channel_messages(job_id):
        if msg.get('sender') == sender and msg.get('client_message_id') == client_message_id:
            return msg
    return None

# -----------------------------------------------------------------------------
# Chat read cursors (DM mark-as-read; not dual-write mutation)
# -----------------------------------------------------------------------------

def get_chat_cursors(username: str) -> Dict[str, Any]:
    key = f"{CHAT_CURSORS_PREFIX}/{username}.json"
    data = _s3_get(key)
    if not data:
        return {'by_peer': {}}
    data.setdefault('by_peer', {})
    return data

def save_chat_cursors(username: str, data: Dict[str, Any]) -> bool:
    key = f"{CHAT_CURSORS_PREFIX}/{username}.json"
    return _s3_put(key, data)

# -----------------------------------------------------------------------------
# Bulletin Management
# -----------------------------------------------------------------------------

def save_bulletin(post_id: str, data: Dict[str, Any]) -> None:
    """Save a bulletin post to S3."""
    key = f"{BULLETINS_PREFIX}/{post_id}.json"
    if not _s3_put(key, data):
        logger.error(f"Failed to save bulletin {post_id}")

def get_all_bulletins() -> List[Dict[str, Any]]:
    """Retrieve all bulletin posts from S3."""
    bulletins = []
    try:
        keys = _s3_list(BULLETINS_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                bulletin = _s3_get(key)
                if bulletin:
                    bulletins.append(bulletin)
    except Exception as e:
        logger.error(f"Error loading bulletins: {e}")

    return sorted(bulletins, key=lambda x: x.get('posted_at', 0), reverse=True)

# -----------------------------------------------------------------------------
# Feedback Management
# -----------------------------------------------------------------------------

def get_feedback() -> List[Dict[str, Any]]:
    """Retrieve all feedback posts from S3."""
    data = _s3_get(FEEDBACK_KEY)
    if isinstance(data, dict):
        return data.get('posts', [])
    return []

def save_feedback(posts: List[Dict[str, Any]]) -> None:
    """Persist feedback posts list to S3."""
    if not _s3_put(FEEDBACK_KEY, {'posts': posts}):
        logger.error("Failed to save feedback posts")

def get_financing_applications() -> List[Dict[str, Any]]:
    """Retrieve all financing applications from S3."""
    data = _s3_get(FINANCING_KEY)
    if isinstance(data, dict):
        return data.get('applications', [])
    return []

def save_financing_applications(applications: List[Dict[str, Any]]) -> None:
    """Persist financing applications list to S3."""
    if not _s3_put(FINANCING_KEY, {'applications': applications}):
        logger.error("Failed to save financing applications")

# -----------------------------------------------------------------------------
# Follows Management
# -----------------------------------------------------------------------------

def get_follows(username: str) -> Dict[str, List[str]]:
    """Retrieve a user's followers/following lists from S3."""
    key = f"{FOLLOWS_PREFIX}/{username}.json"
    data = _s3_get(key)
    if isinstance(data, dict):
        return {'following': data.get('following', []), 'followers': data.get('followers', [])}
    return {'following': [], 'followers': []}

def save_follows(username: str, data: Dict[str, List[str]]) -> None:
    """Persist a user's followers/following lists to S3."""
    key = f"{FOLLOWS_PREFIX}/{username}.json"
    if not _s3_put(key, data):
        logger.error(f"Failed to save follows for {username}")

# -----------------------------------------------------------------------------
# Profile Slug Management
# -----------------------------------------------------------------------------

def get_username_by_slug(slug: str) -> Optional[str]:
    """Resolve a public profile slug to a username."""
    key = f"{SLUGS_PREFIX}/{slug}.json"
    data = _s3_get(key)
    if isinstance(data, dict):
        return data.get('username')
    return None

def save_slug_mapping(slug: str, username: str) -> None:
    """Persist a slug -> username mapping to S3."""
    key = f"{SLUGS_PREFIX}/{slug}.json"
    if not _s3_put(key, {'username': username}):
        logger.error(f"Failed to save slug mapping for {slug}")

# -----------------------------------------------------------------------------
# Avatar Storage
# -----------------------------------------------------------------------------

def save_avatar(username: str, ext: str, body: bytes, content_type: str) -> Optional[str]:
    """Upload an avatar image to S3 and return its public URL."""
    key = f"{AVATARS_PREFIX}/{username}.{ext}"
    if not _s3_put_binary(key, body, content_type):
        return None
    return f"{config.DO_SPACES_URL}/{key}"

# -----------------------------------------------------------------------------
# Cosmetics Shop Orders
# -----------------------------------------------------------------------------

def get_shop_orders() -> List[Dict[str, Any]]:
    """Retrieve all cosmetics shop orders from S3."""
    data = _s3_get(SHOP_ORDERS_KEY)
    if isinstance(data, dict):
        return data.get('orders', [])
    return []

def save_shop_orders(orders: List[Dict[str, Any]]) -> None:
    """Persist cosmetics shop orders list to S3."""
    if not _s3_put(SHOP_ORDERS_KEY, {'orders': orders}):
        logger.error("Failed to save shop orders")

# -----------------------------------------------------------------------------
# Campaigns (multi-unit demand-side initiatives)
# -----------------------------------------------------------------------------

def save_campaign(campaign_id: str, data: Dict[str, Any]) -> None:
    """Save campaign data to S3."""
    key = f"{CAMPAIGNS_PREFIX}/{campaign_id}.json"
    if not _s3_put(key, data):
        logger.error(f"Failed to save campaign {campaign_id}")

def get_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve campaign data from S3."""
    key = f"{CAMPAIGNS_PREFIX}/{campaign_id}.json"
    return _s3_get(key)

def get_all_campaigns() -> List[Dict[str, Any]]:
    """Retrieve all campaigns from S3."""
    campaigns = []
    try:
        keys = _s3_list(CAMPAIGNS_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                campaign = _s3_get(key)
                if campaign:
                    campaigns.append(campaign)
    except Exception as e:
        logger.error(f"Error loading campaigns: {e}")
    return campaigns

# -----------------------------------------------------------------------------
# Endorsements (peer skill endorsements)
# -----------------------------------------------------------------------------

def get_endorsements(username: str) -> List[Dict[str, Any]]:
    """Retrieve all endorsements received by a user from S3."""
    key = f"{ENDORSEMENTS_PREFIX}/{username}.json"
    data = _s3_get(key)
    if isinstance(data, dict):
        return data.get('endorsements', [])
    return []

def save_endorsements(username: str, endorsements: List[Dict[str, Any]]) -> None:
    """Persist a user's received endorsements list to S3."""
    key = f"{ENDORSEMENTS_PREFIX}/{username}.json"
    if not _s3_put(key, {'endorsements': endorsements}):
        logger.error(f"Failed to save endorsements for {username}")

# -----------------------------------------------------------------------------
# Disputes (flagged jobs, admin review queue)
# -----------------------------------------------------------------------------

def get_disputes() -> List[Dict[str, Any]]:
    """Retrieve all filed disputes from S3."""
    data = _s3_get(DISPUTES_KEY)
    if isinstance(data, dict):
        return data.get('disputes', [])
    return []

def save_disputes(disputes: List[Dict[str, Any]]) -> None:
    """Persist disputes list to S3."""
    if not _s3_put(DISPUTES_KEY, {'disputes': disputes}):
        logger.error("Failed to save disputes")

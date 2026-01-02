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
from typing import Dict, List, Optional, Any
import config

logger = logging.getLogger(__name__)

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

# -----------------------------------------------------------------------------
# S3 Helper Functions
# -----------------------------------------------------------------------------

def _s3_put(key: str, data: Dict[str, Any]) -> bool:
    """Save JSON data to S3."""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        return True
    except ClientError as e:
        logger.error(f"S3 PUT error for {key}: {e}")
        return False

def _s3_get(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve JSON data from S3."""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(response['Body'].read().decode('utf-8'))
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
    """Check if an object exists in S3."""
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError:
        return False

def _s3_delete(key: str) -> bool:
    """Delete an object from S3."""
    try:
        s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
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
    try:
        keys = _s3_list(MESSAGES_PREFIX)
        for key in keys:
            if key.endswith('.json'):
                msg = _s3_get(key)
                if msg and (msg.get('sender') == username or msg.get('recipient') == username):
                    messages.append(msg)
    except Exception as e:
        logger.error(f"Error loading messages: {e}")
    return messages

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

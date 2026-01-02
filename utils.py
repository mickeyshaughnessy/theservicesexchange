"""
Utility functions for Service Exchange - Enhanced Storage
-------------------------------------------------------
Handles file-based persistence for the application....
Includes management for accounts, tokens, bids, jobs, messages, and bulletins.
"""

import json
import time
import logging
import os
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Storage directories
STORAGE_DIR = 'data'
ACCOUNTS_DIR = os.path.join(STORAGE_DIR, 'accounts')
TOKENS_DIR = os.path.join(STORAGE_DIR, 'tokens')
BIDS_DIR = os.path.join(STORAGE_DIR, 'bids')
JOBS_DIR = os.path.join(STORAGE_DIR, 'jobs')
MESSAGES_DIR = os.path.join(STORAGE_DIR, 'messages')
BULLETINS_DIR = os.path.join(STORAGE_DIR, 'bulletins')

# Create directories if they don't exist
for directory in [STORAGE_DIR, ACCOUNTS_DIR, TOKENS_DIR, BIDS_DIR, JOBS_DIR, MESSAGES_DIR, BULLETINS_DIR]:
    os.makedirs(directory, exist_ok=True)

# -----------------------------------------------------------------------------
# Account Management
# -----------------------------------------------------------------------------

def save_account(username: str, data: Dict[str, Any]) -> None:
    """Save account data to JSON file."""
    filepath = os.path.join(ACCOUNTS_DIR, f"{username}.json")
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f)
    except IOError as e:
        logger.error(f"Error saving account {username}: {e}")

def get_account(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve account data."""
    filepath = os.path.join(ACCOUNTS_DIR, f"{username}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading account {username}: {e}")
    return None

def account_exists(username: str) -> bool:
    """Check if an account exists."""
    filepath = os.path.join(ACCOUNTS_DIR, f"{username}.json")
    return os.path.exists(filepath)

def get_signup_stats() -> Dict[str, int]:
    """Get counts of demand and supply signups."""
    stats = {'demand': 0, 'supply': 0, 'total': 0}
    try:
        for filename in os.listdir(ACCOUNTS_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(ACCOUNTS_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        account = json.load(f)
                        user_type = account.get('user_type', '')
                        if user_type == 'demand':
                            stats['demand'] += 1
                        elif user_type == 'supply':
                            stats['supply'] += 1
                        stats['total'] += 1
                except (IOError, json.JSONDecodeError):
                    continue
    except Exception as e:
        logger.error(f"Error getting signup stats: {e}")
    return stats

# -----------------------------------------------------------------------------
# Token Management
# -----------------------------------------------------------------------------

def save_token(token: str, username: str, expiry: int) -> None:
    """Save authentication token."""
    filepath = os.path.join(TOKENS_DIR, f"{token}.json")
    try:
        with open(filepath, 'w') as f:
            json.dump({'username': username, 'expiry': expiry}, f)
    except IOError as e:
        logger.error(f"Error saving token: {e}")

def get_token_username(token: str) -> Optional[str]:
    """Retrieve username from valid token."""
    filepath = os.path.join(TOKENS_DIR, f"{token}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                if data['expiry'] > time.time():
                    return data['username']
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error validating token: {e}")
    return None

# -----------------------------------------------------------------------------
# Bid Management
# -----------------------------------------------------------------------------

def save_bid(bid_id: str, data: Dict[str, Any]) -> None:
    """Save bid data."""
    filepath = os.path.join(BIDS_DIR, f"{bid_id}.json")
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f)
    except IOError as e:
        logger.error(f"Error saving bid {bid_id}: {e}")

def get_bid(bid_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve bid data."""
    filepath = os.path.join(BIDS_DIR, f"{bid_id}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading bid {bid_id}: {e}")
    return None

def delete_bid(bid_id: str) -> None:
    """Delete a bid."""
    filepath = os.path.join(BIDS_DIR, f"{bid_id}.json")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError as e:
            logger.error(f"Error deleting bid {bid_id}: {e}")

def get_all_bids() -> List[Dict[str, Any]]:
    """Retrieve all active bids."""
    bids = []
    try:
        for filename in os.listdir(BIDS_DIR):
            if filename.endswith('.json'):
                with open(os.path.join(BIDS_DIR, filename), 'r') as f:
                    bids.append(json.load(f))
    except Exception as e:
        logger.error(f"Error loading bids: {e}")
    return bids

def get_user_bids(username: str) -> List[Dict[str, Any]]:
    """Retrieve all bids for a specific user."""
    return [bid for bid in get_all_bids() if bid.get('username') == username]

# -----------------------------------------------------------------------------
# Job Management
# -----------------------------------------------------------------------------

def save_job(job_id: str, data: Dict[str, Any]) -> None:
    """Save job data."""
    filepath = os.path.join(JOBS_DIR, f"{job_id}.json")
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f)
    except IOError as e:
        logger.error(f"Error saving job {job_id}: {e}")

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve job data."""
    filepath = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading job {job_id}: {e}")
    return None

def get_all_jobs() -> List[Dict[str, Any]]:
    """Retrieve all jobs."""
    jobs = []
    try:
        for filename in os.listdir(JOBS_DIR):
            if filename.endswith('.json'):
                with open(os.path.join(JOBS_DIR, filename), 'r') as f:
                    jobs.append(json.load(f))
    except Exception as e:
        logger.error(f"Error loading jobs: {e}")
    return jobs

def get_user_jobs(username: str) -> List[Dict[str, Any]]:
    """Retrieve jobs for a user (as buyer or provider)."""
    return [
        job for job in get_all_jobs() 
        if job.get('buyer_username') == username or job.get('provider_username') == username
    ]

def delete_job(job_id: str) -> None:
    """Delete a job."""
    filepath = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError as e:
            logger.error(f"Error deleting job {job_id}: {e}")

# -----------------------------------------------------------------------------
# Message Management
# -----------------------------------------------------------------------------

def save_message(message_id: str, data: Dict[str, Any]) -> None:
    """Save a message."""
    filepath = os.path.join(MESSAGES_DIR, f"{message_id}.json")
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f)
    except IOError as e:
        logger.error(f"Error saving message {message_id}: {e}")

def get_user_messages(username: str) -> List[Dict[str, Any]]:
    """Retrieve messages for a user."""
    messages = []
    try:
        for filename in os.listdir(MESSAGES_DIR):
            if filename.endswith('.json'):
                with open(os.path.join(MESSAGES_DIR, filename), 'r') as f:
                    msg = json.load(f)
                    if msg.get('sender') == username or msg.get('recipient') == username:
                        messages.append(msg)
    except Exception as e:
        logger.error(f"Error loading messages: {e}")
    return messages

# -----------------------------------------------------------------------------
# Bulletin Management
# -----------------------------------------------------------------------------

def save_bulletin(post_id: str, data: Dict[str, Any]) -> None:
    """Save a bulletin post."""
    filepath = os.path.join(BULLETINS_DIR, f"{post_id}.json")
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f)
    except IOError as e:
        logger.error(f"Error saving bulletin {post_id}: {e}")

def get_all_bulletins() -> List[Dict[str, Any]]:
    """Retrieve all bulletin posts."""
    bulletins = []
    try:
        for filename in os.listdir(BULLETINS_DIR):
            if filename.endswith('.json'):
                with open(os.path.join(BULLETINS_DIR, filename), 'r') as f:
                    bulletins.append(json.load(f))
    except Exception as e:
        logger.error(f"Error loading bulletins: {e}")
    
    return sorted(bulletins, key=lambda x: x.get('posted_at', 0), reverse=True)

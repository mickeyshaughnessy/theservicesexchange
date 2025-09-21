"""
Utility functions for Service Exchange - Enhanced Storage
"""

import json
import time
import logging
import os

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

# Account management
def save_account(username, data):
    """Save account data"""
    filepath = os.path.join(ACCOUNTS_DIR, f"{username}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f)

def get_account(username):
    """Get account data"""
    filepath = os.path.join(ACCOUNTS_DIR, f"{username}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return None

def account_exists(username):
    """Check if account exists"""
    filepath = os.path.join(ACCOUNTS_DIR, f"{username}.json")
    return os.path.exists(filepath)

# Token management
def save_token(token, username, expiry):
    """Save authentication token"""
    filepath = os.path.join(TOKENS_DIR, f"{token}.json")
    with open(filepath, 'w') as f:
        json.dump({'username': username, 'expiry': expiry}, f)

def get_token_username(token):
    """Get username from token"""
    filepath = os.path.join(TOKENS_DIR, f"{token}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
            if data['expiry'] > time.time():
                return data['username']
    return None

# Bid management
def save_bid(bid_id, data):
    """Save bid data"""
    filepath = os.path.join(BIDS_DIR, f"{bid_id}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f)

def get_bid(bid_id):
    """Get bid data"""
    filepath = os.path.join(BIDS_DIR, f"{bid_id}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return None

def delete_bid(bid_id):
    """Delete bid"""
    filepath = os.path.join(BIDS_DIR, f"{bid_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)

def get_all_bids():
    """Get all active bids"""
    bids = []
    for filename in os.listdir(BIDS_DIR):
        if filename.endswith('.json'):
            with open(os.path.join(BIDS_DIR, filename), 'r') as f:
                bids.append(json.load(f))
    return bids

def get_user_bids(username):
    """Get bids for a specific user"""
    user_bids = []
    for bid in get_all_bids():
        if bid['username'] == username:
            user_bids.append(bid)
    return user_bids

# Job management
def save_job(job_id, data):
    """Save job data"""
    filepath = os.path.join(JOBS_DIR, f"{job_id}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f)

def get_job(job_id):
    """Get job data"""
    filepath = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return None

def get_all_jobs():
    """Get all jobs"""
    jobs = []
    for filename in os.listdir(JOBS_DIR):
        if filename.endswith('.json'):
            with open(os.path.join(JOBS_DIR, filename), 'r') as f:
                jobs.append(json.load(f))
    return jobs

def get_user_jobs(username):
    """Get jobs for a specific user (as buyer or provider)"""
    user_jobs = []
    for job in get_all_jobs():
        if job['buyer_username'] == username or job['provider_username'] == username:
            user_jobs.append(job)
    return user_jobs

def delete_job(job_id):
    """Delete a job"""
    filepath = os.path.join(JOBS_DIR, f"{job_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)

# Message management
def save_message(message_id, data):
    """Save a message"""
    filepath = os.path.join(MESSAGES_DIR, f"{message_id}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f)

def get_user_messages(username):
    """Get messages for a user"""
    messages = []
    for filename in os.listdir(MESSAGES_DIR):
        if filename.endswith('.json'):
            with open(os.path.join(MESSAGES_DIR, filename), 'r') as f:
                msg = json.load(f)
                if msg['sender'] == username or msg['recipient'] == username:
                    messages.append(msg)
    return messages

# Bulletin management
def save_bulletin(post_id, data):
    """Save a bulletin post"""
    filepath = os.path.join(BULLETINS_DIR, f"{post_id}.json")
    with open(filepath, 'w') as f:
        json.dump(data, f)

def get_all_bulletins():
    """Get all bulletin posts"""
    bulletins = []
    for filename in os.listdir(BULLETINS_DIR):
        if filename.endswith('.json'):
            with open(os.path.join(BULLETINS_DIR, filename), 'r') as f:
                bulletins.append(json.load(f))
    return sorted(bulletins, key=lambda x: x.get('posted_at', 0), reverse=True)
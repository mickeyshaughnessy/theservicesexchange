"""
S3 Storage Utilities for Service Exchange
"""

import json
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

# S3 Configuration
S3_BUCKET = "mithrilmedia"
S3_PREFIX = "theservicesexchange"

# Initialize S3 client
s3_client = boto3.client('s3')

def s3_key(path):
    """Generate S3 key from path"""
    return f"{S3_PREFIX}/{path}"

def s3_put_json(path, data):
    """Store JSON data in S3"""
    try:
        key = s3_key(path)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        return True
    except Exception as e:
        logger.error(f"S3 put error: {str(e)}")
        return False

def s3_get_json(path):
    """Retrieve JSON data from S3"""
    try:
        key = s3_key(path)
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(response['Body'].read())
        return data
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return None
        logger.error(f"S3 get error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"S3 get error: {str(e)}")
        return None

def s3_delete(path):
    """Delete object from S3"""
    try:
        key = s3_key(path)
        s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
        return True
    except Exception as e:
        logger.error(f"S3 delete error: {str(e)}")
        return False

def s3_list_keys(prefix):
    """List all keys with given prefix"""
    try:
        full_prefix = s3_key(prefix)
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=full_prefix
        )
        
        if 'Contents' not in response:
            return []
        
        keys = []
        for obj in response['Contents']:
            # Remove the base prefix to get relative path
            relative_key = obj['Key'].replace(f"{S3_PREFIX}/", "")
            keys.append(relative_key)
        
        return keys
    except Exception as e:
        logger.error(f"S3 list error: {str(e)}")
        return []

def s3_exists(path):
    """Check if object exists in S3"""
    try:
        key = s3_key(path)
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        logger.error(f"S3 exists error: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"S3 exists error: {str(e)}")
        return False

def s3_list_json_objects(prefix):
    """List and load all JSON objects with given prefix"""
    try:
        keys = s3_list_keys(prefix)
        objects = []
        
        for key in keys:
            if key.endswith('.json'):
                data = s3_get_json(key)
                if data:
                    objects.append(data)
        
        return objects
    except Exception as e:
        logger.error(f"S3 list objects error: {str(e)}")
        return []

# Account management functions
def get_account(username):
    """Get account data"""
    return s3_get_json(f"accounts/{username}.json")

def save_account(username, account_data):
    """Save account data"""
    return s3_put_json(f"accounts/{username}.json", account_data)

def account_exists(username):
    """Check if account exists"""
    return s3_exists(f"accounts/{username}.json")

# Token management
def save_token(token, username, expiry_time):
    """Save authentication token"""
    token_data = {
        'username': username,
        'expires_at': expiry_time
    }
    return s3_put_json(f"tokens/{token}.json", token_data)

def get_token_username(token):
    """Get username from token"""
    token_data = s3_get_json(f"tokens/{token}.json")
    if token_data:
        import time
        if token_data.get('expires_at', 0) > time.time():
            return token_data.get('username')
    return None

def delete_token(token):
    """Delete authentication token"""
    return s3_delete(f"tokens/{token}.json")

# Bid management
def save_bid(bid_id, bid_data):
    """Save bid data"""
    return s3_put_json(f"bids/{bid_id}.json", bid_data)

def get_bid(bid_id):
    """Get bid data"""
    return s3_get_json(f"bids/{bid_id}.json")

def delete_bid(bid_id):
    """Delete bid"""
    return s3_delete(f"bids/{bid_id}.json")

def get_all_bids():
    """Get all active bids"""
    return s3_list_json_objects("bids")

# Job management
def save_job(job_id, job_data):
    """Save job data"""
    return s3_put_json(f"jobs/{job_id}.json", job_data)

def get_job(job_id):
    """Get job data"""
    return s3_get_json(f"jobs/{job_id}.json")

def get_all_jobs():
    """Get all jobs"""
    return s3_list_json_objects("jobs")

# Message management
def save_message(username, message_id, message_data):
    """Save message for user"""
    return s3_put_json(f"messages/{username}/{message_id}.json", message_data)

def get_user_messages(username):
    """Get all messages for user"""
    return s3_list_json_objects(f"messages/{username}")

# Bulletin management
def save_bulletin(bulletin_id, bulletin_data):
    """Save bulletin"""
    return s3_put_json(f"bulletins/{bulletin_id}.json", bulletin_data)

def get_all_bulletins():
    """Get all bulletins"""
    return s3_list_json_objects("bulletins")

# Cleanup expired data
def cleanup_expired_tokens():
    """Remove expired tokens"""
    import time
    current_time = time.time()
    
    token_keys = s3_list_keys("tokens")
    for key in token_keys:
        token_data = s3_get_json(key)
        if token_data and token_data.get('expires_at', 0) < current_time:
            s3_delete(key)
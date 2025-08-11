"""
Service Exchange (SEX) Business Logic Handlers
"""

import uuid
import json
import time
import math
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from anthropic import Anthropic
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import redis
import config

# Initialize services
redis_client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, db=config.REDIS_DB)
anthropic_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
geolocator = Nominatim(user_agent="service-exchange")
logger = logging.getLogger(__name__)

# Redis hash keys
REDHASH_ACCOUNTS = 'sex:accounts'
REDHASH_LIVE_BIDS = 'sex:live_bids'
REDHASH_COMPLETED_JOBS = 'sex:completed_jobs'
REDHASH_BULLETINS = 'sex:bulletins'
REDHASH_MESSAGES = 'sex:messages'

def calculate_distance(point1, point2):
    """Calculate distance between two geographic points"""
    return geodesic(point1, point2).miles

def geocode_address(address):
    """Convert address to coordinates"""
    try:
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        return None, None
    except Exception as e:
        logger.error(f"Geocoding error: {str(e)}")
        return None, None

def match_service_with_capabilities(service_description, provider_capabilities):
    """Use LLM to determine if provider capabilities match service requirements"""
    try:
        prompt = f"""Determine if a service provider can fulfill a service request.

Service Requested: {service_description}
Provider Capabilities: {provider_capabilities}

Respond with only 'YES' if the provider can definitely fulfill this request, or 'NO' if they cannot or if it's unclear.
Consider partial matches as NO. The provider must be able to fully complete the requested service.

Answer:"""

        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=10,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        answer = response.content[0].text.strip().upper()
        return answer == "YES"
        
    except Exception as e:
        logger.error(f"LLM matching error: {str(e)}")
        # Fallback to simple keyword matching
        service_words = set(service_description.lower().split())
        capability_words = set(provider_capabilities.lower().split())
        return len(service_words & capability_words) >= 2

def calculate_reputation_score(user_data):
    """Calculate user reputation score from ratings"""
    stars = user_data.get('stars', 0)
    total_ratings = user_data.get('total_ratings', 0)
    
    if total_ratings == 0:
        return 2.5  # New users start at middle reputation
    
    # Weighted average that considers number of ratings
    confidence_factor = min(total_ratings / 10, 1.0)  # More ratings = more confidence
    return (stars * confidence_factor) + (2.5 * (1 - confidence_factor))

def register_user(data):
    """Register a new user account"""
    try:
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        # Validate input
        if not username or not password:
            return {"error": "Username and password required"}, 400
            
        if len(username) < 3 or len(username) > 20:
            return {"error": "Username must be 3-20 characters"}, 400
            
        if len(password) < 8:
            return {"error": "Password must be at least 8 characters"}, 400
        
        # Check if user exists
        if redis_client.hexists(REDHASH_ACCOUNTS, username):
            return {"error": "Username already exists"}, 400
        
        # Create account
        user_data = {
            'username': username,
            'password': generate_password_hash(password),
            'created_on': int(time.time()),
            'stars': 0,
            'total_ratings': 0,
            'completed_jobs': 0,
            'cancelled_jobs': 0
        }
        
        redis_client.hset(REDHASH_ACCOUNTS, username, json.dumps(user_data))
        logger.info(f"User registered: {username}")
        
        return {"message": "Registration successful"}, 201
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return {"error": "Internal server error"}, 500

def login_user(data):
    """Authenticate user and return access token"""
    try:
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return {"error": "Username and password required"}, 400
        
        # Get user data
        user_json = redis_client.hget(REDHASH_ACCOUNTS, username)
        if not user_json:
            return {"error": "Invalid credentials"}, 401
        
        user_data = json.loads(user_json)
        
        # Verify password
        if not check_password_hash(user_data['password'], password):
            return {"error": "Invalid credentials"}, 401
        
        # Generate token
        token = str(uuid.uuid4())
        redis_client.setex(
            f"auth_token:{token}",
            86400,  # 24 hour expiry
            username
        )
        
        logger.info(f"User logged in: {username}")
        return {"access_token": token, "username": username}, 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_account(data):
    """Get account information"""
    try:
        username = data.get('username')
        
        user_json = redis_client.hget(REDHASH_ACCOUNTS, username)
        if not user_json:
            return {"error": "User not found"}, 404
        
        user_data = json.loads(user_json)
        
        # Calculate average rating
        avg_rating = 0
        if user_data['total_ratings'] > 0:
            avg_rating = user_data['stars'] / user_data['total_ratings']
        
        account_info = {
            'username': username,
            'created_on': user_data['created_on'],
            'stars': round(avg_rating, 2),
            'total_ratings': user_data['total_ratings'],
            'completed_jobs': user_data.get('completed_jobs', 0),
            'reputation_score': calculate_reputation_score(user_data)
        }
        
        return account_info, 200
        
    except Exception as e:
        logger.error(f"Account retrieval error: {str(e)}")
        return {"error": "Internal server error"}, 500

def submit_bid(data):
    """Submit a service request bid"""
    try:
        username = data.get('username')
        service = data.get('service', '').strip()
        price = data.get('price')
        end_time = data.get('end_time')
        location_type = data.get('location_type', 'physical')  # physical, remote, or hybrid
        
        # Validate required fields
        if not service or price is None or end_time is None:
            return {"error": "Service, price, and end_time required"}, 400
        
        if price <= 0:
            return {"error": "Price must be positive"}, 400
        
        if end_time <= time.time():
            return {"error": "End time must be in the future"}, 400
        
        # Handle location based on type
        lat, lon = None, None
        address = None
        
        if location_type in ['physical', 'hybrid']:
            if 'lat' in data and 'lon' in data:
                lat = data['lat']
                lon = data['lon']
            elif 'address' in data:
                address = data['address']
                lat, lon = geocode_address(address)
                if lat is None:
                    return {"error": "Could not geocode address"}, 400
            else:
                return {"error": "Location required for physical services"}, 400
        
        # Get user reputation
        user_json = redis_client.hget(REDHASH_ACCOUNTS, username)
        user_data = json.loads(user_json)
        reputation = calculate_reputation_score(user_data)
        
        # Create bid
        bid_id = str(uuid.uuid4())
        bid = {
            'bid_id': bid_id,
            'username': username,
            'service': service,
            'price': price,
            'end_time': end_time,
            'location_type': location_type,
            'lat': lat,
            'lon': lon,
            'address': address,
            'created_at': int(time.time()),
            'buyer_reputation': reputation,
            'status': 'pending'
        }
        
        redis_client.hset(REDHASH_LIVE_BIDS, bid_id, json.dumps(bid))
        logger.info(f"Bid created: {bid_id} by {username}")
        
        return {"bid_id": bid_id}, 200
        
    except Exception as e:
        logger.error(f"Bid submission error: {str(e)}")
        return {"error": "Internal server error"}, 500

def cancel_bid(data):
    """Cancel a pending bid"""
    try:
        username = data.get('username')
        bid_id = data.get('bid_id')
        
        if not bid_id:
            return {"error": "Bid ID required"}, 400
        
        # Get bid
        bid_json = redis_client.hget(REDHASH_LIVE_BIDS, bid_id)
        if not bid_json:
            return {"error": "Bid not found"}, 404
        
        bid = json.loads(bid_json)
        
        # Verify ownership
        if bid['username'] != username:
            return {"error": "Not authorized to cancel this bid"}, 403
        
        # Remove bid
        redis_client.hdel(REDHASH_LIVE_BIDS, bid_id)
        logger.info(f"Bid cancelled: {bid_id}")
        
        return {"message": "Bid cancelled successfully"}, 200
        
    except Exception as e:
        logger.error(f"Bid cancellation error: {str(e)}")
        return {"error": "Internal server error"}, 500

def grab_job(data):
    """Match provider with highest-paying compatible job"""
    try:
        username = data.get('username')
        capabilities = data.get('capabilities', '').strip()
        location_type = data.get('location_type', 'physical')
        
        if not capabilities:
            return {"error": "Capabilities required"}, 400
        
        # Get provider reputation
        user_json = redis_client.hget(REDHASH_ACCOUNTS, username)
        user_data = json.loads(user_json)
        provider_reputation = calculate_reputation_score(user_data)
        
        # Handle location for physical services
        provider_lat, provider_lon = None, None
        max_distance = 10  # Default max distance in miles
        
        if location_type in ['physical', 'hybrid']:
            if 'lat' in data and 'lon' in data:
                provider_lat = data['lat']
                provider_lon = data['lon']
            elif 'address' in data:
                provider_lat, provider_lon = geocode_address(data['address'])
                if provider_lat is None:
                    return {"error": "Could not geocode address"}, 400
            else:
                return {"error": "Location required for physical services"}, 400
            
            max_distance = data.get('max_distance', 10)
        
        # Find matching bids
        matched_bids = []
        
        for bid_id, bid_json in redis_client.hscan_iter(REDHASH_LIVE_BIDS):
            try:
                bid = json.loads(bid_json)
                
                # Check if bid is still valid
                if bid['end_time'] <= time.time():
                    continue
                
                # Check location compatibility
                if location_type == 'remote' and bid['location_type'] == 'physical':
                    continue
                if location_type == 'physical' and bid['location_type'] == 'remote':
                    continue
                
                # For physical services, check distance
                if bid['location_type'] in ['physical', 'hybrid'] and location_type in ['physical', 'hybrid']:
                    if bid['lat'] and bid['lon'] and provider_lat and provider_lon:
                        distance = calculate_distance(
                            (bid['lat'], bid['lon']),
                            (provider_lat, provider_lon)
                        )
                        if distance > max_distance:
                            continue
                
                # Check capability match using LLM
                if match_service_with_capabilities(bid['service'], capabilities):
                    # Calculate match score based on reputation alignment
                    reputation_diff = abs(provider_reputation - bid['buyer_reputation'])
                    reputation_bonus = max(0, 5 - reputation_diff) * 0.1  # Up to 50% bonus
                    
                    adjusted_price = bid['price'] * (1 + reputation_bonus)
                    matched_bids.append((adjusted_price, bid_id.decode(), bid))
                    
            except Exception as e:
                logger.error(f"Error processing bid {bid_id}: {str(e)}")
                continue
        
        if not matched_bids:
            return {"message": "No matching jobs available"}, 204
        
        # Select highest-paying job (after reputation adjustment)
        _, bid_id, job = max(matched_bids, key=lambda x: x[0])
        
        # Create job record
        job_id = str(uuid.uuid4())
        job_record = {
            'job_id': job_id,
            'bid_id': bid_id,
            'status': 'accepted',
            'service': job['service'],
            'price': job['price'],
            'location_type': job['location_type'],
            'lat': job.get('lat'),
            'lon': job.get('lon'),
            'address': job.get('address'),
            'buyer_username': job['username'],
            'provider_username': username,
            'accepted_at': int(time.time()),
            'buyer_reputation': job['buyer_reputation'],
            'provider_reputation': provider_reputation
        }
        
        # Move bid to completed jobs
        redis_client.hset(REDHASH_COMPLETED_JOBS, job_id, json.dumps(job_record))
        redis_client.hdel(REDHASH_LIVE_BIDS, bid_id)
        
        logger.info(f"Job matched: {job_id} - Provider: {username}, Buyer: {job['username']}")
        
        return job_record, 200
        
    except Exception as e:
        logger.error(f"Job matching error: {str(e)}")
        return {"error": "Internal server error"}, 500

def sign_job(data):
    """Complete and rate a job"""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        star_rating = data.get('star_rating')
        
        if not job_id or star_rating is None:
            return {"error": "Job ID and star rating required"}, 400
        
        if star_rating < 1 or star_rating > 5:
            return {"error": "Star rating must be between 1 and 5"}, 400
        
        # Get job
        job_json = redis_client.hget(REDHASH_COMPLETED_JOBS, job_id)
        if not job_json:
            return {"error": "Job not found"}, 404
        
        job = json.loads(job_json)
        
        # Determine user role
        is_buyer = username == job['buyer_username']
        is_provider = username == job['provider_username']
        
        if not (is_buyer or is_provider):
            return {"error": "Not authorized to sign this job"}, 403
        
        # Check if already signed
        sign_field = 'buyer_signed' if is_buyer else 'provider_signed'
        if job.get(sign_field):
            return {"error": "Already signed by this user"}, 400
        
        # Update job
        job[sign_field] = True
        job[f"{'buyer' if is_buyer else 'provider'}_rating"] = star_rating
        
        # Update counterparty's reputation
        counterparty = job['provider_username'] if is_buyer else job['buyer_username']
        counterparty_json = redis_client.hget(REDHASH_ACCOUNTS, counterparty)
        if counterparty_json:
            counterparty_data = json.loads(counterparty_json)
            counterparty_data['stars'] = counterparty_data.get('stars', 0) + star_rating
            counterparty_data['total_ratings'] = counterparty_data.get('total_ratings', 0) + 1
            
            # If both parties have signed, increment completed jobs
            if job.get('buyer_signed') and job.get('provider_signed'):
                counterparty_data['completed_jobs'] = counterparty_data.get('completed_jobs', 0) + 1
                job['status'] = 'completed'
                job['completed_at'] = int(time.time())
            
            redis_client.hset(REDHASH_ACCOUNTS, counterparty, json.dumps(counterparty_data))
        
        redis_client.hset(REDHASH_COMPLETED_JOBS, job_id, json.dumps(job))
        
        logger.info(f"Job signed: {job_id} by {username} with rating {star_rating}")
        
        return {"message": "Job signed successfully"}, 200
        
    except Exception as e:
        logger.error(f"Job signing error: {str(e)}")
        return {"error": "Internal server error"}, 500

def nearby_services(data):
    """Find services near a location"""
    try:
        # Get location
        if 'lat' in data and 'lon' in data:
            user_lat = data['lat']
            user_lon = data['lon']
        elif 'address' in data:
            user_lat, user_lon = geocode_address(data['address'])
            if user_lat is None:
                return {"error": "Could not geocode address"}, 400
        else:
            return {"error": "Location required"}, 400
        
        radius = data.get('radius', 10)  # Default 10 miles
        
        nearby_bids = []
        
        for bid_id, bid_json in redis_client.hscan_iter(REDHASH_LIVE_BIDS):
            try:
                bid = json.loads(bid_json)
                
                # Skip non-physical services
                if bid['location_type'] == 'remote':
                    continue
                
                # Skip expired bids
                if bid['end_time'] <= time.time():
                    continue
                
                # Check distance
                if bid.get('lat') and bid.get('lon'):
                    distance = calculate_distance(
                        (user_lat, user_lon),
                        (bid['lat'], bid['lon'])
                    )
                    
                    if distance <= radius:
                        bid['distance'] = round(distance, 2)
                        nearby_bids.append(bid)
                        
            except Exception as e:
                logger.error(f"Error processing bid: {str(e)}")
                continue
        
        # Sort by distance
        nearby_bids.sort(key=lambda x: x['distance'])
        
        return {"services": nearby_bids}, 200
        
    except Exception as e:
        logger.error(f"Nearby services error: {str(e)}")
        return {"error": "Internal server error"}, 500

def send_message(data):
    """Send a message to another user"""
    try:
        sender = data.get('username')
        recipient = data.get('recipient')
        message = data.get('message', '').strip()
        
        if not recipient or not message:
            return {"error": "Recipient and message required"}, 400
        
        if len(message) > 1000:
            return {"error": "Message too long (max 1000 characters)"}, 400
        
        # Verify recipient exists
        if not redis_client.hexists(REDHASH_ACCOUNTS, recipient):
            return {"error": "Recipient not found"}, 404
        
        # Create message
        msg_id = str(uuid.uuid4())
        msg_data = {
            'id': msg_id,
            'sender': sender,
            'recipient': recipient,
            'message': message,
            'timestamp': int(time.time()),
            'read': False
        }
        
        # Store for both users
        redis_client.hset(f"{REDHASH_MESSAGES}:{sender}", msg_id, json.dumps(msg_data))
        redis_client.hset(f"{REDHASH_MESSAGES}:{recipient}", msg_id, json.dumps(msg_data))
        
        logger.info(f"Message sent from {sender} to {recipient}")
        
        return {"message_id": msg_id}, 200
        
    except Exception as e:
        logger.error(f"Message send error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_messages(data):
    """Get user's messages"""
    try:
        username = data.get('username')
        
        messages = []
        for _, msg_json in redis_client.hscan_iter(f"{REDHASH_MESSAGES}:{username}"):
            try:
                msg = json.loads(msg_json)
                messages.append(msg)
            except:
                continue
        
        # Sort by timestamp
        messages.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return {"messages": messages}, 200
        
    except Exception as e:
        logger.error(f"Message retrieval error: {str(e)}")
        return {"error": "Internal server error"}, 500

def post_bulletin(data):
    """Post to bulletin board"""
    try:
        username = data.get('username')
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        category = data.get('category', 'general')
        
        if not title or not content:
            return {"error": "Title and content required"}, 400
        
        if len(title) > 100:
            return {"error": "Title too long (max 100 characters)"}, 400
        
        if len(content) > 2000:
            return {"error": "Content too long (max 2000 characters)"}, 400
        
        # Create bulletin
        bulletin_id = str(uuid.uuid4())
        bulletin = {
            'id': bulletin_id,
            'author': username,
            'title': title,
            'content': content,
            'category': category,
            'timestamp': int(time.time())
        }
        
        redis_client.hset(REDHASH_BULLETINS, bulletin_id, json.dumps(bulletin))
        
        logger.info(f"Bulletin posted: {bulletin_id} by {username}")
        
        return {"bulletin_id": bulletin_id}, 200
        
    except Exception as e:
        logger.error(f"Bulletin post error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_bulletins(data):
    """Get bulletin board posts"""
    try:
        category = data.get('category')
        limit = min(int(data.get('limit', 20)), 100)
        
        bulletins = []
        for _, bulletin_json in redis_client.hscan_iter(REDHASH_BULLETINS):
            try:
                bulletin = json.loads(bulletin_json)
                if category and bulletin['category'] != category:
                    continue
                bulletins.append(bulletin)
            except:
                continue
        
        # Sort by timestamp
        bulletins.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return {"bulletins": bulletins[:limit]}, 200
        
    except Exception as e:
        logger.error(f"Bulletin retrieval error: {str(e)}")
        return {"error": "Internal server error"}, 500
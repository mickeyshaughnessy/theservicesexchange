"""
Service Exchange Business Logic with Seat Verification - Fixed for localhost
"""

import uuid
import json
import time
import logging
import hashlib
import requests
import math
from werkzeug.security import generate_password_hash, check_password_hash
import config
from utils import (
    get_account, save_account, account_exists,
    save_token, get_token_username,
    save_bid, get_bid, delete_bid, get_all_bids, get_user_bids,
    save_job, get_job, get_user_jobs
)

logger = logging.getLogger(__name__)

# Load Golden seats data at module level
golden_seats = {}
try:
    with open('seats.dat', 'r') as f:
        for line in f:
            seat_data = json.loads(line.strip())
            golden_seats[seat_data['id']] = seat_data
except Exception as e:
    logger.error(f"Error loading golden seats data: {str(e)}")

# Load Silver seats data at module level
silver_seats = {}
try:
    with open('silver_seats.dat', 'r') as f:
        for line in f:
            seat_data = json.loads(line.strip())
            silver_seats[seat_data['id']] = seat_data
except Exception as e:
    logger.error(f"Error loading silver seats data: {str(e)}")

def md5(text):
    """Generate MD5 hash of text"""
    return hashlib.md5(text.encode()).hexdigest()

def verify_seat_credentials(seat_data):
    """Verify seat credentials for both Golden and Silver seats"""
    if not seat_data or 'id' not in seat_data:
        return False, "Missing seat ID"
    
    seat_id = seat_data['id']
    seat_owner = seat_data.get('owner')
    seat_secret = seat_data.get('secret')
    
    if not all([seat_id, seat_owner, seat_secret]):
        return False, "Missing seat credentials"
    
    # Check Golden seats first (permanent)
    if seat_id in golden_seats:
        stored_seat = golden_seats[seat_id]
        if (seat_owner == stored_seat['owner'] and 
            seat_secret == md5(stored_seat['phrase'])):
            return True, "Golden seat verified"
        else:
            return False, "Invalid golden seat credentials"
    
    # Check Silver seats (time-limited)
    if seat_id in silver_seats:
        stored_seat = silver_seats[seat_id]
        
        # Verify owner and secret
        if (seat_owner != stored_seat['owner'] or 
            seat_secret != md5(stored_seat['phrase'])):
            return False, "Invalid silver seat credentials"
        
        # Check if seat has expired (1 year = 365 * 24 * 3600 seconds)
        assigned_time = stored_seat.get('assigned', 0)
        current_time = int(time.time())
        one_year_seconds = 365 * 24 * 3600
        
        if current_time > assigned_time + one_year_seconds:
            return False, "Silver seat has expired"
        
        return True, "Silver seat verified"
    
    return False, "Seat ID not found"

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two geographic points using Haversine formula"""
    if not all([lat1, lon1, lat2, lon2]):
        return float('inf')
    
    # Radius of Earth in miles
    R = 3959
    
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

def simple_geocode(address):
    """Simple geocoding for common test addresses - no external API calls"""
    # Mock geocoding for testing - maps common addresses to coordinates
    address_map = {
        # Denver area coordinates for testing
        "123 main st, denver, co 80202": (39.7392, -104.9903),
        "456 oak ave, denver, co 80203": (39.7431, -104.9792),
        "789 pine st, denver, co 80204": (39.7391, -105.0178),
        "downtown denver, co": (39.7392, -104.9903),
        "denver, co": (39.7392, -104.9903),
        "colorado": (39.5501, -105.7821),
        # Default coordinates for unknown addresses
        "unknown": (39.7392, -104.9903)
    }
    
    address_lower = address.lower().strip()
    
    # Try exact match first
    if address_lower in address_map:
        return address_map[address_lower]
    
    # Try partial matches
    for key, coords in address_map.items():
        if key in address_lower or address_lower in key:
            return coords
    
    # Default to Denver coordinates
    logger.warning(f"Using default coordinates for address: {address}")
    print('here')
    return address_map["unknown"]

def match_service_with_capabilities(service_description, provider_capabilities):
    """Use OpenRouter to determine if provider can fulfill service, with fallback"""
    try:
        if not hasattr(config, 'OPENROUTER_API_KEY') or not config.OPENROUTER_API_KEY:
            # Fallback to keyword matching if no API key
            return keyword_match_service(service_description, provider_capabilities)
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""Determine if a service provider can fulfill a service request.

Service Requested: {service_description}
Provider Capabilities: {provider_capabilities}

Respond with only 'YES' if the provider can definitely fulfill this request, or 'NO' if they cannot.

Answer:"""

        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 10
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=5
        )
        
        if response.status_code == 200:
            answer = response.json()['choices'][0]['message']['content'].strip().upper()
            return answer == "YES"
        
    except Exception as e:
        logger.error(f"LLM matching error: {str(e)}")
    
    # Fallback to keyword matching
    return keyword_match_service(service_description, provider_capabilities)

def keyword_match_service(service_description, provider_capabilities):
    """Fallback keyword matching"""
    service_words = set(service_description.lower().split())
    capability_words = set(provider_capabilities.lower().split())
    common_words = service_words & capability_words
    return len(common_words) >= 1  # More lenient for testing

def calculate_reputation_score(user_data):
    """Calculate user reputation score"""
    stars = user_data.get('stars', 0)
    total_ratings = user_data.get('total_ratings', 0)
    
    if total_ratings == 0:
        return 2.5
    
    avg_rating = stars / total_ratings
    confidence_factor = min(total_ratings / 10, 1.0)
    return (avg_rating * confidence_factor) + (2.5 * (1 - confidence_factor))

def register_user(data):
    """Register a new user"""
    try:
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return {"error": "Username and password required"}, 400
            
        if len(username) < 3 or len(username) > 20:
            return {"error": "Username must be 3-20 characters"}, 400
            
        if len(password) < 8:
            return {"error": "Password must be at least 8 characters"}, 400
        
        if account_exists(username):
            return {"error": "Username already exists"}, 400
        
        user_data = {
            'username': username,
            'password': generate_password_hash(password),
            'created_on': int(time.time()),
            'stars': 0,
            'total_ratings': 0,
            'completed_jobs': 0
        }
        
        save_account(username, user_data)
        logger.info(f"User registered: {username}")
        
        return {"message": "Registration successful"}, 201
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return {"error": "Internal server error"}, 500

def login_user(data):
    """Authenticate user"""
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
        expiry_time = int(time.time()) + 86400
        save_token(token, username, expiry_time)
        
        logger.info(f"User logged in: {username}")
        return {"access_token": token, "username": username}, 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_account_info(data):
    """Get account information"""
    try:
        username = data.get('username')
        
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
        
        avg_rating = 0
        if user_data['total_ratings'] > 0:
            avg_rating = user_data['stars'] / user_data['total_ratings']
        
        return {
            'username': username,
            'created_on': user_data['created_on'],
            'stars': round(avg_rating, 2),
            'total_ratings': user_data['total_ratings'],
            'completed_jobs': user_data.get('completed_jobs', 0),
            'reputation_score': calculate_reputation_score(user_data)
        }, 200
        
    except Exception as e:
        logger.error(f"Account error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_my_bids(data):
    """Get user's outstanding bids"""
    try:
        username = data.get('username')
        
        user_bids = get_user_bids(username)
        current_time = int(time.time())
        
        # Filter out expired bids and add status info
        outstanding_bids = []
        for bid in user_bids:
            if bid['end_time'] > current_time:
                outstanding_bids.append({
                    'bid_id': bid['bid_id'],
                    'service': bid['service'],
                    'price': bid['price'],
                    'end_time': bid['end_time'],
                    'location_type': bid['location_type'],
                    'address': bid.get('address'),
                    'created_at': bid['created_at'],
                    'status': 'active'
                })
        
        # Sort by creation time (newest first)
        outstanding_bids.sort(key=lambda x: x['created_at'], reverse=True)
        
        logger.info(f"Retrieved {len(outstanding_bids)} outstanding bids for {username}")
        
        return {"bids": outstanding_bids}, 200
        
    except Exception as e:
        logger.error(f"Get my bids error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_my_jobs(data):
    """Get user's completed and active jobs"""
    try:
        username = data.get('username')
        
        user_jobs = get_user_jobs(username)
        
        # Separate completed and active jobs
        completed_jobs = []
        active_jobs = []
        
        for job in user_jobs:
            job_info = {
                'job_id': job['job_id'],
                'service': job['service'],
                'price': job['price'],
                'location_type': job['location_type'],
                'address': job.get('address'),
                'accepted_at': job['accepted_at'],
                'status': job['status'],
                'buyer_username': job['buyer_username'],
                'provider_username': job['provider_username']
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
            else:
                active_jobs.append(job_info)
        
        # Sort by time (newest first)
        completed_jobs.sort(key=lambda x: x.get('completed_at', 0), reverse=True)
        active_jobs.sort(key=lambda x: x['accepted_at'], reverse=True)
        
        logger.info(f"Retrieved {len(completed_jobs)} completed and {len(active_jobs)} active jobs for {username}")
        
        return {
            "completed_jobs": completed_jobs[:10],  # Limit to last 10 completed jobs
            "active_jobs": active_jobs
        }, 200
        
    except Exception as e:
        logger.error(f"Get my jobs error: {str(e)}")
        return {"error": "Internal server error"}, 500

def submit_bid(data):
    """Submit a service request"""
    try:
        username = data.get('username')
        service = data.get('service', '').strip()
        price = data.get('price')
        end_time = data.get('end_time')
        location_type = data.get('location_type', 'physical')
        
        if not service or price is None or end_time is None:
            return {"error": "Service, price, and end_time required"}, 400
        
        if price <= 0:
            return {"error": "Price must be positive"}, 400
        
        if end_time <= time.time():
            return {"error": "End time must be in the future"}, 400
        
        lat, lon = None, None
        address = None
        
        if location_type in ['physical', 'hybrid']:
            if 'lat' in data and 'lon' in data:
                lat = data['lat']
                lon = data['lon']
            elif 'address' in data:
                address = data['address']
                lat, lon = simple_geocode(address)
            else:
                return {"error": "Location required for physical services"}, 400
        
        user_data = get_account(username)
        reputation = calculate_reputation_score(user_data)
        
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
            'buyer_reputation': reputation
        }
        
        save_bid(bid_id, bid)
        logger.info(f"Bid created: {bid_id}")
        
        return {"bid_id": bid_id}, 200
        
    except Exception as e:
        logger.error(f"Bid error: {str(e)}")
        return {"error": "Internal server error"}, 500

def cancel_bid(data):
    """Cancel a bid"""
    try:
        username = data.get('username')
        bid_id = data.get('bid_id')
        
        if not bid_id:
            return {"error": "Bid ID required"}, 400
        
        bid = get_bid(bid_id)
        if not bid:
            return {"error": "Bid not found"}, 404
        
        if bid['username'] != username:
            return {"error": "Not authorized"}, 403
        
        delete_bid(bid_id)
        logger.info(f"Bid cancelled: {bid_id}")
        
        return {"message": "Bid cancelled"}, 200
        
    except Exception as e:
        logger.error(f"Cancel error: {str(e)}")
        return {"error": "Internal server error"}, 500

def grab_job(data):
    """Match provider with best job using prioritized matching - REQUIRES SEAT CREDENTIALS"""
    try:
        logger.info(f"grab_job called with data: {json.dumps(data, indent=2)}")
        
        # SEAT VERIFICATION - Must happen first
        seat_data = data.get('seat')
        is_valid, message = verify_seat_credentials(seat_data)
        if not is_valid:
            logger.warning(f"Seat verification failed: {message}")
            return {"error": f"Seat verification failed: {message}"}, 403
        
        logger.info(f"Seat verification successful: {message}")
        
        username = data.get('username')
        capabilities = data.get('capabilities', '').strip()
        location_type = data.get('location_type', 'physical')
        
        if not capabilities:
            return {"error": "Capabilities required"}, 400
        
        user_data = get_account(username)
        if not user_data:
            return {"error": "User not found"}, 404
            
        provider_reputation = calculate_reputation_score(user_data)
        
        provider_lat, provider_lon = None, None
        max_distance = 10
        
        if location_type in ['physical', 'hybrid']:
            if 'lat' in data and 'lon' in data:
                provider_lat = data['lat']
                provider_lon = data['lon']
            elif 'address' in data:
                provider_lat, provider_lon = simple_geocode(data['address'])
            else:
                return {"error": "Location required for physical services"}, 400
            
            max_distance = data.get('max_distance', 10)
        
        all_bids = get_all_bids()
        
        # Step 1: Location filtering
        location_filtered = []
        for bid in all_bids:
            if bid['end_time'] <= time.time():
                continue
            
            if location_type == 'remote' and bid['location_type'] == 'physical':
                continue
            if location_type == 'physical' and bid['location_type'] == 'remote':
                continue
            
            if bid['location_type'] in ['physical', 'hybrid'] and location_type in ['physical', 'hybrid']:
                if bid['lat'] and bid['lon'] and provider_lat and provider_lon:
                    distance = calculate_distance(
                        bid['lat'], bid['lon'],
                        provider_lat, provider_lon
                    )
                    if distance > max_distance:
                        continue
            
            location_filtered.append(bid)
        
        if not location_filtered:
            return {"message": "No jobs in your area"}, 204
        
        # Step 2: Capability matching
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
            'location_type': best_bid['location_type'],
            'lat': best_bid.get('lat'),
            'lon': best_bid.get('lon'),
            'address': best_bid.get('address'),
            'buyer_username': best_bid['username'],
            'provider_username': username,
            'accepted_at': int(time.time()),
            'buyer_reputation': best_bid['buyer_reputation'],
            'provider_reputation': provider_reputation
        }
        
        save_job(job_id, job_record)
        delete_bid(best_bid['bid_id'])
        
        logger.info(f"Job matched: {job_id}")
        
        return job_record, 200
        
    except Exception as e:
        logger.error(f"Job grab error: {str(e)}")
        return {"error": "Internal server error"}, 500

def sign_job(data):
    """Complete and rate a job"""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        star_rating = data.get('star_rating')
        
        if not job_id or star_rating is None:
            return {"error": "Job ID and rating required"}, 400
        
        if star_rating < 1 or star_rating > 5:
            return {"error": "Rating must be 1-5"}, 400
        
        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        
        is_buyer = username == job['buyer_username']
        is_provider = username == job['provider_username']
        
        if not (is_buyer or is_provider):
            return {"error": "Not authorized"}, 403
        
        sign_field = 'buyer_signed' if is_buyer else 'provider_signed'
        if job.get(sign_field):
            return {"error": "Already signed"}, 400
        
        job[sign_field] = True
        job[f"{'buyer' if is_buyer else 'provider'}_rating"] = star_rating
        
        counterparty = job['provider_username'] if is_buyer else job['buyer_username']
        counterparty_data = get_account(counterparty)
        if counterparty_data:
            counterparty_data['stars'] = counterparty_data.get('stars', 0) + star_rating
            counterparty_data['total_ratings'] = counterparty_data.get('total_ratings', 0) + 1
            
            if job.get('buyer_signed') and job.get('provider_signed'):
                counterparty_data['completed_jobs'] = counterparty_data.get('completed_jobs', 0) + 1
                job['status'] = 'completed'
                job['completed_at'] = int(time.time())
            
            save_account(counterparty, counterparty_data)
        
        save_job(job_id, job)
        
        logger.info(f"Job signed: {job_id}")
        
        return {"message": "Job signed successfully"}, 200
        
    except Exception as e:
        logger.error(f"Sign job error: {str(e)}")
        return {"error": "Internal server error"}, 500

def nearby_services(data):
    """Find nearby services"""
    try:
        if 'lat' in data and 'lon' in data:
            user_lat = data['lat']
            user_lon = data['lon']
        elif 'address' in data:
            user_lat, user_lon = simple_geocode(data['address'])
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
                    bid['distance'] = round(distance, 2)
                    nearby_bids.append(bid)
        
        nearby_bids.sort(key=lambda x: x['distance'])
        
        return {"services": nearby_bids}, 200
        
    except Exception as e:
        logger.error(f"Nearby error: {str(e)}")
        return {"error": "Internal server error"}, 500
"""
Service Exchange Business Logic with Seat Verification
"""

import uuid
import json
import time
import logging
import hashlib
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import config
from utils import (
    get_account, save_account, account_exists,
    save_token, get_token_username,
    save_bid, get_bid, delete_bid, get_all_bids,
    save_job, get_job
)

geolocator = Nominatim(user_agent="service-exchange")
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
    """Use OpenRouter to determine if provider can fulfill service"""
    try:
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
            json=data
        )
        
        if response.status_code == 200:
            answer = response.json()['choices'][0]['message']['content'].strip().upper()
            return answer == "YES"
        
    except Exception as e:
        logger.error(f"LLM matching error: {str(e)}")
    
    # Fallback to keyword matching
    service_words = set(service_description.lower().split())
    capability_words = set(provider_capabilities.lower().split())
    return len(service_words & capability_words) >= 2

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
                lat, lon = geocode_address(address)
                if lat is None:
                    return {"error": "Could not geocode address"}, 400
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
                provider_lat, provider_lon = geocode_address(data['address'])
                if provider_lat is None:
                    return {"error": "Could not geocode address"}, 400
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
                        (bid['lat'], bid['lon']),
                        (provider_lat, provider_lon)
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
            user_lat, user_lon = geocode_address(data['address'])
            if user_lat is None:
                return {"error": "Could not geocode address"}, 400
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
                    (user_lat, user_lon),
                    (bid['lat'], bid['lon'])
                )
                
                if distance <= radius:
                    bid['distance'] = round(distance, 2)
                    nearby_bids.append(bid)
        
        nearby_bids.sort(key=lambda x: x['distance'])
        
        return {"services": nearby_bids}, 200
        
    except Exception as e:
        logger.error(f"Nearby error: {str(e)}")
        return {"error": "Internal server error"}, 500
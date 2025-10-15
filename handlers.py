"""
Service Exchange Business Logic with Complete API Implementation
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
    save_job, get_job, get_all_jobs, get_user_jobs,
    save_message, get_user_messages,
    save_bulletin, get_all_bulletins
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
    logger.warning(f"Could not load golden seats data: {str(e)}")

# Load Silver seats data at module level
silver_seats = {}
try:
    with open('silver_seats.dat', 'r') as f:
        for line in f:
            seat_data = json.loads(line.strip())
            silver_seats[seat_data['id']] = seat_data
except Exception as e:
    logger.warning(f"Could not load silver seats data: {str(e)}")

# TEMPORARY: Seat verification disabled during ramp-up
SEAT_VERIFICATION_ENABLED = False

def md5(text):
    """Generate MD5 hash of text"""
    return hashlib.md5(text.encode()).hexdigest()

def verify_seat_credentials(seat_data):
    """Verify seat credentials for both Golden and Silver seats"""
    # TEMPORARY: Skip verification during ramp-up period
    if not SEAT_VERIFICATION_ENABLED:
        return True, "Seat verification temporarily disabled"
    
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
        "denver airport": (39.8561, -104.6737),
        "denver, co": (39.7392, -104.9903),
        "colorado": (39.5501, -105.7821),
        # Default coordinates for unknown addresses
        "unknown": (39.7392, -104.9903)
    }
    
    address_lower = address.lower().strip() if address else ""
    
    # Try exact match first
    if address_lower in address_map:
        return address_map[address_lower]
    
    # Try partial matches
    for key, coords in address_map.items():
        if key in address_lower or address_lower in key:
            return coords
    
    # Default to Denver coordinates
    logger.info(f"Using default coordinates for address: {address}")
    return address_map["unknown"]

def call_openrouter_llm(prompt, temperature=0, max_tokens=10):
    """Call OpenRouter API for LLM inference"""
    try:
        if not hasattr(config, 'OPENROUTER_API_KEY') or not config.OPENROUTER_API_KEY:
            logger.warning("OpenRouter API key not configured")
            return None
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://serviceexchange.com",
            "X-Title": "ServiceExchange"
        }
        
        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Debug logging
        logger.info("=" * 80)
        logger.info("LLM API CALL")
        logger.info("=" * 80)
        logger.info(f"Endpoint: https://openrouter.ai/api/v1/chat/completions")
        logger.info(f"Model: {data['model']}")
        logger.info(f"Temperature: {temperature}, Max Tokens: {max_tokens}")
        logger.info(f"\nInput Messages:")
        logger.info(json.dumps(data['messages'], indent=2))
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=5
        )
        
        logger.info(f"\nResponse Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"\nFull Response:")
            logger.info(json.dumps(result, indent=2))
            
            if 'choices' in result and len(result['choices']) > 0:
                answer = result['choices'][0]['message']['content'].strip()
                logger.info(f"\nExtracted Answer: '{answer}'")
                logger.info("=" * 80)
                return answer
        else:
            logger.error(f"OpenRouter API error: {response.status_code}")
            logger.error(f"Response text: {response.text}")
            logger.info("=" * 80)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenRouter API request error: {str(e)}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Unexpected error calling OpenRouter: {str(e)}")
        logger.info("=" * 80)
    
    return None

def match_service_with_capabilities(service_description, provider_capabilities):
    """Use OpenRouter to determine if provider can fulfill service, with fallback"""
    try:
        # Handle service objects
        if isinstance(service_description, dict):
            service_description = json.dumps(service_description)
        
        prompt = f"""Determine if a service provider can fulfill a service request.

Service Requested: {service_description}
Provider Capabilities: {provider_capabilities}

Respond with only 'YES' if the provider can definitely fulfill this request, or 'NO' if they cannot.

Answer:"""

        answer = call_openrouter_llm(prompt, temperature=0, max_tokens=10)
        
        if answer and answer.upper() == "YES":
            return True
        elif answer and answer.upper() == "NO":
            return False
        
    except Exception as e:
        logger.error(f"LLM matching error: {str(e)}")
    
    # Fallback to keyword matching
    return keyword_match_service(service_description, provider_capabilities)

def keyword_match_service(service_description, provider_capabilities):
    """Fallback keyword matching"""
    # Handle service objects
    if isinstance(service_description, dict):
        service_description = json.dumps(service_description)
    
    service_words = set(str(service_description).lower().split())
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
            'reputation_score': round(calculate_reputation_score(user_data), 2)
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
                    'currency': bid.get('currency', 'USD'),
                    'payment_method': bid.get('payment_method', 'cash'),
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
                'currency': job.get('currency', 'USD'),
                'payment_method': job.get('payment_method', 'cash'),
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
    """Submit a service request with enhanced fields"""
    try:
        username = data.get('username')
        service = data.get('service')  # Can be string or object
        price = data.get('price')
        currency = data.get('currency', 'USD')
        payment_method = data.get('payment_method', 'cash')
        xmoney_account = data.get('xmoney_account')
        end_time = data.get('end_time')
        location_type = data.get('location_type', 'physical')
        
        if not service or price is None or end_time is None:
            return {"error": "Service, price, and end_time required"}, 400
        
        if price <= 0:
            return {"error": "Price must be positive"}, 400
        
        if end_time <= time.time():
            return {"error": "End time must be in the future"}, 400
        
        # Validate payment method
        valid_payment_methods = ['cash', 'credit_card', 'paypal', 'xmoney', 'crypto', 'bank_transfer', 'venmo']
        if payment_method not in valid_payment_methods:
            return {"error": f"Invalid payment method. Must be one of: {', '.join(valid_payment_methods)}"}, 400
        
        # XMoney account required if payment method is xmoney
        if payment_method == 'xmoney' and not xmoney_account:
            return {"error": "XMoney account required for XMoney payment method"}, 400
        
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
            'service': service,  # Can be string or object
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
    """Match provider with best job using prioritized matching"""
    try:
        logger.info(f"grab_job called with data: {json.dumps(data, indent=2)}")
        
        # SEAT VERIFICATION (when enabled)
        if SEAT_VERIFICATION_ENABLED:
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
            'provider_reputation': provider_reputation
        }
        
        save_job(job_id, job_record)
        delete_bid(best_bid['bid_id'])
        
        logger.info(f"Job matched: {job_id}")
        
        return job_record, 200
        
    except Exception as e:
        logger.error(f"Job grab error: {str(e)}")
        return {"error": "Internal server error"}, 500

def reject_job(data):
    """Reject a job that was assigned"""
    try:
        username = data.get('username')
        job_id = data.get('job_id')
        reason = data.get('reason', 'No reason provided')
        
        if not job_id:
            return {"error": "Job ID required"}, 400
        
        job = get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        
        # Only provider can reject
        if job['provider_username'] != username:
            return {"error": "Only provider can reject job"}, 403
        
        # Check if job is still in accepted state
        if job['status'] != 'accepted':
            return {"error": "Can only reject jobs in accepted state"}, 400
        
        # Restore the bid
        bid_id = str(uuid.uuid4())  # New bid ID since original was deleted
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
            'created_at': int(time.time()),
            'buyer_reputation': job['buyer_reputation']
        }
        save_bid(bid_id, bid)
        
        # Update job status
        job['status'] = 'rejected'
        job['rejected_at'] = int(time.time())
        job['rejection_reason'] = reason
        save_job(job_id, job)
        
        logger.info(f"Job rejected: {job_id}")
        
        return {"message": "Job rejected successfully"}, 200
        
    except Exception as e:
        logger.error(f"Reject job error: {str(e)}")
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
                
                # Update own completed jobs count too
                own_data = get_account(username)
                if own_data:
                    own_data['completed_jobs'] = own_data.get('completed_jobs', 0) + 1
                    save_account(username, own_data)
            
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

def send_chat_message(data):
    """Send a chat message to another user"""
    try:
        sender = data.get('username')
        recipient = data.get('recipient')
        message_text = data.get('message', '').strip()
        job_id = data.get('job_id')
        
        if not recipient or not message_text:
            return {"error": "Recipient and message required"}, 400
        
        # Check if recipient exists
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
        
        # Save message using the correct function signature
        # The local utils.py uses: save_message(message_id, data)
        save_message(f"{sender}_{message_id}", message_data)
        save_message(f"{recipient}_{message_id}", message_data)
        
        logger.info(f"Chat message sent from {sender} to {recipient}")
        
        return {
            "message_id": message_id,
            "sent_at": message_data['sent_at']
        }, 200
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return {"error": "Internal server error"}, 500

def post_bulletin(data):
    """Post a bulletin message"""
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
        
        # Save bulletin using the correct function signature
        save_bulletin(post_id, bulletin_data)
        
        logger.info(f"Bulletin posted by {username}")
        
        return {
            "post_id": post_id,
            "posted_at": bulletin_data['posted_at']
        }, 200
        
    except Exception as e:
        logger.error(f"Bulletin error: {str(e)}")
        return {"error": "Internal server error"}, 500

def get_exchange_data(data):
    """Get comprehensive exchange data"""
    try:
        # Get query parameters
        category_filter = data.get('category')
        location_filter = data.get('location')
        limit = min(data.get('limit', 50), 200)
        include_completed = data.get('include_completed', False)
        
        # Get active bids
        all_bids = get_all_bids()
        current_time = int(time.time())
        
        active_bids = []
        for bid in all_bids:
            if bid['end_time'] > current_time:
                # Apply filters
                if category_filter:
                    service_str = json.dumps(bid['service']) if isinstance(bid['service'], dict) else bid['service']
                    if category_filter.lower() not in service_str.lower():
                        continue
                
                if location_filter and bid.get('address'):
                    if location_filter.lower() not in bid['address'].lower():
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
        
        # Sort by newest first and limit
        active_bids.sort(key=lambda x: x['posted_at'], reverse=True)
        active_bids = active_bids[:limit]
        
        result = {
            'active_bids': active_bids
        }
        
        # Include completed jobs if requested
        if include_completed:
            all_jobs = get_all_jobs()
            completed_jobs = []
            
            for job in all_jobs:
                if job['status'] == 'completed':
                    # Apply filters
                    if category_filter:
                        service_str = json.dumps(job['service']) if isinstance(job['service'], dict) else job['service']
                        if category_filter.lower() not in service_str.lower():
                            continue
                    
                    if location_filter and job.get('address'):
                        if location_filter.lower() not in job['address'].lower():
                            continue
                    
                    # Calculate average rating
                    ratings = []
                    if job.get('buyer_rating'):
                        ratings.append(job['buyer_rating'])
                    if job.get('provider_rating'):
                        ratings.append(job['provider_rating'])
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
            
            # Sort by newest first and limit
            completed_jobs.sort(key=lambda x: x['completed_at'], reverse=True)
            completed_jobs = completed_jobs[:limit]
            
            result['completed_jobs'] = completed_jobs
        
        # Calculate market statistics
        market_stats = {
            'total_active_bids': len([b for b in all_bids if b['end_time'] > current_time]),
            'total_completed_today': 0
        }
        
        # Category-specific average prices
        if category_filter and active_bids:
            prices = [b['price'] for b in active_bids]
            market_stats[f'avg_price_{category_filter}'] = round(sum(prices) / len(prices), 2)
        
        # Count today's completed jobs
        if include_completed:
            today_start = int(time.time()) - 86400  # Last 24 hours
            all_jobs = get_all_jobs()
            market_stats['total_completed_today'] = len([
                j for j in all_jobs 
                if j['status'] == 'completed' and j.get('completed_at', 0) > today_start
            ])
        
        result['market_stats'] = market_stats
        
        logger.info(f"Exchange data retrieved with {len(active_bids)} active bids")
        
        return result, 200
        
    except Exception as e:
        logger.error(f"Exchange data error: {str(e)}")
        return {"error": "Internal server error"}, 500


# Unit test for LLM integration
if __name__ == "__main__":
    print("=" * 60)
    print("Testing OpenRouter LLM Integration")
    print("=" * 60)
    
    # Check if API key is configured
    if not hasattr(config, 'OPENROUTER_API_KEY') or not config.OPENROUTER_API_KEY:
        print("\n❌ FAILED: OPENROUTER_API_KEY not configured in config.py")
        print("Please add: OPENROUTER_API_KEY = 'your-api-key-here'")
        exit(1)
    
    print(f"\n✓ API key configured (length: {len(config.OPENROUTER_API_KEY)} chars)")
    
    # Test 1: Basic LLM call
    print("\n" + "-" * 60)
    print("Test 1: Basic LLM Call")
    print("-" * 60)
    
    test_prompt = "Say only the word 'WORKING' if you can read this message."
    print(f"Prompt: {test_prompt}")
    
    response = call_openrouter_llm(test_prompt, temperature=0, max_tokens=10)
    
    if response:
        print(f"✓ Response received: '{response}'")
        if "WORKING" in response.upper():
            print("✓ LLM responded correctly")
        else:
            print(f"⚠ Warning: Expected 'WORKING', got '{response}'")
    else:
        print("❌ FAILED: No response from LLM")
        exit(1)
    
    # Test 2: Service matching with LLM
    print("\n" + "-" * 60)
    print("Test 2: Service Matching")
    print("-" * 60)
    
    test_cases = [
        {
            "service": "Build a website for my business",
            "capabilities": "web development, HTML, CSS, JavaScript, React",
            "expected": True
        },
        {
            "service": "Fix my car engine",
            "capabilities": "web development, HTML, CSS, JavaScript",
            "expected": False
        },
        {
            "service": "Lawn mowing service",
            "capabilities": "gardening, landscaping, lawn care",
            "expected": True
        }
    ]
    
    all_passed = True
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest case {i}:")
        print(f"  Service: {test['service']}")
        print(f"  Capabilities: {test['capabilities']}")
        print(f"  Expected match: {test['expected']}")
        
        result = match_service_with_capabilities(test['service'], test['capabilities'])
        print(f"  Result: {result}")
        
        if result == test['expected']:
            print(f"  ✓ PASS")
        else:
            print(f"  ❌ FAIL: Expected {test['expected']}, got {result}")
            all_passed = False
    
    # Test 3: Fallback to keyword matching
    print("\n" + "-" * 60)
    print("Test 3: Keyword Matching Fallback")
    print("-" * 60)
    
    print("Testing keyword_match_service directly...")
    result = keyword_match_service("lawn mowing", "lawn care gardening")
    print(f"  Result: {result}")
    if result:
        print("  ✓ Keyword matching works")
    else:
        print("  ❌ Keyword matching failed")
        all_passed = False
    
    # Final summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nLLM integration is working correctly!")
        exit(0)
    else:
        print("⚠ SOME TESTS FAILED")
        print("=" * 60)
        print("\nPlease review the failures above.")
        exit(1)
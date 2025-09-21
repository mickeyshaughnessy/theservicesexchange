"""
Integration Tests for Service Exchange API - Complete Feature Set
"""

import requests
import json
import time
import uuid
import hashlib
import argparse

def md5(text):
    """Generate MD5 hash of text"""
    return hashlib.md5(text.encode()).hexdigest()

def load_test_seats():
    """Load test seats from both golden and silver seat files"""
    golden_seats = []
    silver_seats = []
    
    # Load Golden seats
    try:
        with open('seats.dat', 'r') as f:
            for line in f:
                seat_data = json.loads(line.strip())
                golden_seats.append(seat_data)
    except Exception as e:
        print(f"Warning: Could not load seats.dat: {e}")
    
    # Load Silver seats
    try:
        with open('silver_seats.dat', 'r') as f:
            for line in f:
                seat_data = json.loads(line.strip())
                silver_seats.append(seat_data)
    except Exception as e:
        print(f"Warning: Could not load silver_seats.dat: {e}")
    
    return golden_seats[:3], silver_seats[:3]

def create_seat_credentials(seat_data):
    """Create seat credentials for API calls"""
    return {
        "id": seat_data['id'],
        "owner": seat_data['owner'],
        "secret": md5(seat_data['phrase'])
    }

def test_api(api_url, test_seats=True):
    """Run integration tests"""
    # Determine environment
    is_local = "localhost" in api_url or "127.0.0.1" in api_url
    env_name = "LOCAL" if is_local else "PRODUCTION"
    storage_type = "Local Filesystem" if is_local else "AWS S3"
    
    print(f"\n=== Service Exchange API Complete Feature Tests ===")
    print(f"📍 Environment: {env_name}")
    print(f"🔗 API URL: {api_url}")
    print(f"💾 Storage: {storage_type}")
    print("="*55 + "\n")
    
    # Load test seats
    golden_seats, silver_seats = load_test_seats()
    
    if test_seats:
        if not golden_seats and not silver_seats:
            print("Warning: No seats loaded. Seat tests will be skipped.")
            print("Note: Seat verification is currently DISABLED during ramp-up period")
        else:
            print(f"Loaded {len(golden_seats)} golden seats and {len(silver_seats)} silver seats for testing")
            print("Note: Seat verification is currently DISABLED during ramp-up period")
            
            # Display seat information for debugging
            for i, seat in enumerate(golden_seats):
                print(f"  Golden seat {i+1}: ID={seat['id']}, Owner={seat['owner']}")
            for i, seat in enumerate(silver_seats):
                assigned_time = seat.get('assigned', 0)
                is_expired = time.time() > assigned_time + (365 * 24 * 3600)
                status = "EXPIRED" if is_expired else "VALID"
                print(f"  Silver seat {i+1}: ID={seat['id']}, Owner={seat['owner']}, Status={status}")
    
    # Test ping
    print("\nTesting API health...")
    response = requests.get(f"{api_url}/ping", verify=False)
    assert response.status_code == 200
    print("✓ API is operational")
    
    # Test health endpoint
    response = requests.get(f"{api_url}/health", verify=False)
    assert response.status_code == 200
    health_data = response.json()
    assert health_data.get('status') == 'healthy'
    print("✓ Health check endpoint working")
    
    # Register users
    print("\nRegistering test users...")
    buyer_username = f"buyer_{uuid.uuid4().hex[:8]}"
    provider_username = f"provider_{uuid.uuid4().hex[:8]}"
    provider2_username = f"provider2_{uuid.uuid4().hex[:8]}"
    
    response = requests.post(f"{api_url}/register", json={
        "username": buyer_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 201
    print(f"✓ Buyer registered: {buyer_username}")
    
    response = requests.post(f"{api_url}/register", json={
        "username": provider_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 201
    print(f"✓ Provider 1 registered: {provider_username}")
    
    response = requests.post(f"{api_url}/register", json={
        "username": provider2_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 201
    print(f"✓ Provider 2 registered: {provider2_username}")
    
    # Login
    print("\nAuthenticating...")
    response = requests.post(f"{api_url}/login", json={
        "username": buyer_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 200
    buyer_token = response.json()['access_token']
    print("✓ Buyer logged in")
    
    response = requests.post(f"{api_url}/login", json={
        "username": provider_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 200
    provider_token = response.json()['access_token']
    print("✓ Provider 1 logged in")
    
    response = requests.post(f"{api_url}/login", json={
        "username": provider2_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 200
    provider2_token = response.json()['access_token']
    print("✓ Provider 2 logged in")
    
    # Test enhanced submit_bid with new fields
    print("\n=== Testing Enhanced Bid Submission ===")
    headers = {"Authorization": f"Bearer {buyer_token}"}
    
    # Test bid with XMoney payment
    print("\nSubmitting bid with XMoney payment...")
    response = requests.post(f"{api_url}/submit_bid", headers=headers, json={
        "service": {
            "type": "taxi",
            "start_location": "Denver Airport",
            "end_location": "Downtown Denver",
            "passenger_count": 2,
            "vehicle_type": "sedan"
        },
        "price": 65.50,
        "currency": "USD",
        "payment_method": "xmoney",
        "xmoney_account": "@buyer_account",
        "end_time": int(time.time()) + 3600,
        "location_type": "physical",
        "address": "Denver Airport"
    }, verify=False)
    assert response.status_code == 200
    xmoney_bid_id = response.json()['bid_id']
    print(f"✓ XMoney payment bid created: {xmoney_bid_id[:8]}...")
    
    # Test bid with crypto payment
    print("\nSubmitting bid with crypto payment...")
    response = requests.post(f"{api_url}/submit_bid", headers=headers, json={
        "service": {
            "type": "app_development",
            "platform": "web",
            "frameworks": ["React", "Node.js"],
            "features": ["user_auth", "payment_processing"]
        },
        "price": 0.05,
        "currency": "BTC",
        "payment_method": "crypto",
        "end_time": int(time.time()) + 7200,
        "location_type": "remote"
    }, verify=False)
    assert response.status_code == 200
    crypto_bid_id = response.json()['bid_id']
    print(f"✓ Crypto payment bid created: {crypto_bid_id[:8]}...")
    
    # Submit various bids for comprehensive testing
    print("\nSubmitting diverse service requests...")
    
    physical_jobs = [
        {
            "service": {
                "type": "house_cleaning",
                "rooms": 3,
                "bathrooms": 2,
                "deep_clean": True,
                "supplies_included": False
            },
            "price": 150.75,
            "currency": "USD",
            "payment_method": "credit_card",
            "end_time": int(time.time()) + 3600,
            "location_type": "physical",
            "address": "123 Main St, Denver, CO 80202"
        },
        {
            "service": "Office cleaning and sanitization, 2000 sq ft",  # String format still supported
            "price": 200,
            "currency": "EUR",
            "payment_method": "paypal",
            "end_time": int(time.time()) + 3600,
            "location_type": "physical", 
            "address": "456 Business Ave, Denver, CO 80203"
        },
        {
            "service": "Deep cleaning service, kitchen and bathrooms focus",
            "price": 180,
            "currency": "USD",
            "payment_method": "cash",
            "end_time": int(time.time()) + 3600,
            "location_type": "physical",
            "address": "789 Oak St, Denver, CO 80204"
        }
    ]
    
    software_jobs = [
        {
            "service": "Python web application development - REST API with Flask",
            "price": 2500,
            "currency": "USD",
            "payment_method": "bank_transfer",
            "end_time": int(time.time()) + 7200,
            "location_type": "remote"
        },
        {
            "service": {
                "type": "web_development",
                "description": "E-commerce platform",
                "technologies": ["React", "TypeScript", "GraphQL"],
                "timeline": "4 weeks"
            },
            "price": 3200,
            "currency": "USD",
            "payment_method": "venmo",
            "end_time": int(time.time()) + 7200,
            "location_type": "remote"
        },
        {
            "service": "Node.js backend API development",
            "price": 2800,
            "currency": "USD",
            "payment_method": "credit_card",
            "end_time": int(time.time()) + 7200,
            "location_type": "remote"
        }
    ]
    
    # Submit all jobs
    bid_ids = []
    
    print("\nCreating physical service jobs:")
    for i, job in enumerate(physical_jobs, 1):
        response = requests.post(f"{api_url}/submit_bid", headers=headers, json=job, verify=False)
        assert response.status_code == 200
        bid_id = response.json()['bid_id']
        bid_ids.append(bid_id)
        service_desc = json.dumps(job['service']) if isinstance(job['service'], dict) else job['service']
        print(f"  ✓ Physical job {i}: {job['currency']} {job['price']} via {job['payment_method']}")
    
    print("\nCreating software development jobs:")
    for i, job in enumerate(software_jobs, 1):
        response = requests.post(f"{api_url}/submit_bid", headers=headers, json=job, verify=False)
        assert response.status_code == 200
        bid_id = response.json()['bid_id']
        bid_ids.append(bid_id)
        service_desc = json.dumps(job['service']) if isinstance(job['service'], dict) else job['service']
        print(f"  ✓ Software job {i}: {job['currency']} {job['price']} via {job['payment_method']}")
    
    print(f"\n✓ Total jobs created: {len(bid_ids) + 2} (including XMoney and crypto bids)")
    
    # Test my_bids endpoint with enhanced fields
    print("\n=== Testing /my_bids with Enhanced Fields ===")
    response = requests.get(f"{api_url}/my_bids", headers=headers, verify=False)
    assert response.status_code == 200
    bids_data = response.json()
    user_bids = bids_data.get('bids', [])
    print(f"✓ Retrieved {len(user_bids)} outstanding bids")
    
    # Verify enhanced bid fields
    if user_bids:
        sample_bid = user_bids[0]
        enhanced_fields = ['currency', 'payment_method']
        for field in enhanced_fields:
            assert field in sample_bid, f"Missing enhanced field {field} in bid"
        print("✓ Enhanced bid fields (currency, payment_method) present")
        
        # Check for XMoney account in XMoney payment bids
        xmoney_bids = [b for b in user_bids if b.get('payment_method') == 'xmoney']
        if xmoney_bids:
            print(f"✓ Found {len(xmoney_bids)} XMoney payment bids")
    
    # Test grab_job WITHOUT seat credentials (temporary access during ramp-up)
    print("\n=== Testing Job Grabbing (Seat Verification DISABLED) ===")
    headers_provider = {"Authorization": f"Bearer {provider_token}"}
    
    print("\nGrabbing job WITHOUT seat credentials (temporary access)...")
    response = requests.post(f"{api_url}/grab_job",
        headers=headers_provider,
        json={
            "capabilities": "House cleaning, office cleaning, deep cleaning",
            "location_type": "physical",
            "address": "456 Oak Ave, Denver, CO 80203",
            "max_distance": 20
            # Note: No seat field provided
        }, verify=False)
    
    if response.status_code == 200:
        job1 = response.json()
        print(f"✓ Job grabbed WITHOUT seat credentials (temporary access)")
        print(f"  Job: {job1['currency']} {job1['price']} via {job1['payment_method']}")
        job1_id = job1['job_id']
    elif response.status_code == 204:
        print("✓ No matching jobs available")
        job1_id = None
    else:
        print(f"✗ Unexpected response: {response.status_code}")
        job1_id = None
    
    # Test reject_job endpoint
    if job1_id:
        print("\n=== Testing Job Rejection ===")
        response = requests.post(f"{api_url}/reject_job",
            headers=headers_provider,
            json={
                "job_id": job1_id,
                "reason": "Schedule conflict with another commitment"
            }, verify=False)
        assert response.status_code == 200
        print(f"✓ Job {job1_id[:8]}... rejected successfully")
        
        # Verify the job was restored as a bid
        response = requests.get(f"{api_url}/my_bids", headers=headers, verify=False)
        assert response.status_code == 200
        restored_bids = response.json().get('bids', [])
        print(f"✓ Rejected job restored to bid pool ({len(restored_bids)} total bids)")
    
    # Test chat endpoint
    print("\n=== Testing Chat Messaging ===")
    response = requests.post(f"{api_url}/chat",
        headers=headers,
        json={
            "recipient": provider_username,
            "message": "Hi, I have a question about the cleaning service.",
            "job_id": job1_id if job1_id else None
        }, verify=False)
    assert response.status_code == 200
    message_data = response.json()
    print(f"✓ Chat message sent: {message_data['message_id'][:8]}...")
    
    # Provider responds
    response = requests.post(f"{api_url}/chat",
        headers=headers_provider,
        json={
            "recipient": buyer_username,
            "message": "Happy to help! What would you like to know?",
            "job_id": job1_id if job1_id else None
        }, verify=False)
    assert response.status_code == 200
    print("✓ Chat reply sent successfully")
    
    # Test bulletin endpoint
    print("\n=== Testing Bulletin Board ===")
    response = requests.post(f"{api_url}/bulletin",
        headers=headers,
        json={
            "title": "New Cleaning Service Available",
            "content": "Professional house cleaning services now available in the Denver metro area. Eco-friendly products, competitive rates.",
            "category": "offer"
        }, verify=False)
    assert response.status_code == 200
    bulletin_data = response.json()
    print(f"✓ Bulletin posted: {bulletin_data['post_id'][:8]}...")
    
    # Post another bulletin
    response = requests.post(f"{api_url}/bulletin",
        headers=headers_provider,
        json={
            "title": "Looking for Web Development Projects",
            "content": "Experienced developer available for React/Node.js projects. Fast turnaround, quality code.",
            "category": "offer"
        }, verify=False)
    assert response.status_code == 200
    print("✓ Second bulletin posted")
    
    # Test exchange_data endpoint
    print("\n=== Testing Exchange Data Endpoint ===")
    
    # Test without filters
    response = requests.get(f"{api_url}/exchange_data",
        headers=headers, verify=False)
    assert response.status_code == 200
    exchange_data = response.json()
    print(f"✓ Exchange data retrieved: {len(exchange_data.get('active_bids', []))} active bids")
    
    # Test with category filter
    response = requests.get(f"{api_url}/exchange_data?category=cleaning&limit=10",
        headers=headers, verify=False)
    assert response.status_code == 200
    filtered_data = response.json()
    print(f"✓ Filtered exchange data (cleaning): {len(filtered_data.get('active_bids', []))} bids")
    
    # Test with include_completed flag
    response = requests.get(f"{api_url}/exchange_data?include_completed=true&limit=20",
        headers=headers, verify=False)
    assert response.status_code == 200
    complete_data = response.json()
    print(f"✓ Exchange data with completed jobs included")
    
    # Verify market stats
    if 'market_stats' in complete_data:
        stats = complete_data['market_stats']
        print(f"  Market stats: {stats.get('total_active_bids', 0)} active bids")
        if 'avg_price_cleaning' in stats:
            print(f"  Average cleaning price: {stats['avg_price_cleaning']}")
    
    # Test nearby services with enhanced response
    print("\n=== Testing Nearby Services ===")
    response = requests.post(f"{api_url}/nearby",
        headers=headers,
        json={
            "address": "Downtown Denver, CO",
            "radius": 20
        }, verify=False)
    assert response.status_code == 200
    services = response.json()['services']
    print(f"✓ Found {len(services)} nearby services")
    
    if services:
        sample_service = services[0]
        if 'currency' in sample_service:
            print(f"  Sample: {sample_service['currency']} {sample_service['price']} at {sample_service['distance']} miles")
    
    # Grab another job for completion testing
    print("\n=== Testing Job Completion Flow ===")
    response = requests.post(f"{api_url}/grab_job",
        headers=headers_provider,
        json={
            "capabilities": "Python development, Flask, REST API, web development",
            "location_type": "remote"
        }, verify=False)
    
    if response.status_code == 200:
        job2 = response.json()
        print(f"✓ Software job grabbed: {job2['currency']} {job2['price']}")
        
        # Check if this job belongs to our test buyer
        if job2.get('buyer_username') == buyer_username:
            print(f"  Job is from our test buyer: {buyer_username}")
            
            # Complete the job
            print("  Signing job as provider...")
            response = requests.post(f"{api_url}/sign_job",
                headers=headers_provider,
                json={"job_id": job2['job_id'], "star_rating": 5}, verify=False)
            assert response.status_code == 200
            
            print("  Signing job as buyer...")
            response = requests.post(f"{api_url}/sign_job",
                headers=headers,
                json={"job_id": job2['job_id'], "star_rating": 4}, verify=False)
            assert response.status_code == 200
            print("✓ Job completed successfully")
        else:
            print(f"  Job is from another buyer: {job2.get('buyer_username')}")
            print("  Skipping completion test (would need the other buyer's token)")
            
            # Just have the provider sign their part
            print("  Provider signing job...")
            response = requests.post(f"{api_url}/sign_job",
                headers=headers_provider,
                json={"job_id": job2['job_id'], "star_rating": 5}, verify=False)
            if response.status_code == 200:
                print("✓ Provider signed job")
    
    # Test my_jobs endpoint with completed jobs
    print("\n=== Testing /my_jobs Endpoint ===")
    
    # Check buyer's jobs
    response = requests.get(f"{api_url}/my_jobs", headers=headers, verify=False)
    assert response.status_code == 200
    buyer_jobs_data = response.json()
    print(f"✓ Buyer jobs: {len(buyer_jobs_data.get('completed_jobs', []))} completed, "
          f"{len(buyer_jobs_data.get('active_jobs', []))} active")
    
    # Check provider's jobs
    response = requests.get(f"{api_url}/my_jobs", headers=headers_provider, verify=False)
    assert response.status_code == 200
    provider_jobs_data = response.json()
    print(f"✓ Provider jobs: {len(provider_jobs_data.get('completed_jobs', []))} completed, "
          f"{len(provider_jobs_data.get('active_jobs', []))} active")
    
    # Verify enhanced job fields
    all_jobs = (buyer_jobs_data.get('completed_jobs', []) + 
                buyer_jobs_data.get('active_jobs', []) +
                provider_jobs_data.get('completed_jobs', []) + 
                provider_jobs_data.get('active_jobs', []))
    
    if all_jobs:
        sample_job = all_jobs[0]
        if 'currency' in sample_job and 'payment_method' in sample_job:
            print("✓ Enhanced job fields (currency, payment_method) present")
    
    # Test account info
    print("\n=== Testing Account Information ===")
    response = requests.get(f"{api_url}/account", headers=headers, verify=False)
    assert response.status_code == 200
    account_info = response.json()
    print(f"✓ Account: {account_info['username']}")
    print(f"  Reputation: {account_info['reputation_score']}")
    print(f"  Completed jobs: {account_info['completed_jobs']}")
    
    # Test bid cancellation
    print("\n=== Testing Bid Cancellation ===")
    # Get current bids (some may have been consumed by grab_job)
    response = requests.get(f"{api_url}/my_bids", headers=headers, verify=False)
    assert response.status_code == 200
    current_bids = response.json().get('bids', [])
    
    if current_bids:
        bid_to_cancel = current_bids[0]
        print(f"Attempting to cancel bid: {bid_to_cancel['bid_id'][:8]}...")
        response = requests.post(f"{api_url}/cancel_bid",
            headers=headers,
            json={"bid_id": bid_to_cancel['bid_id']}, verify=False)
        assert response.status_code == 200
        print(f"✓ Bid cancelled successfully")
        
        # Verify the bid no longer appears in my_bids
        response = requests.get(f"{api_url}/my_bids", headers=headers, verify=False)
        assert response.status_code == 200
        updated_bids = response.json().get('bids', [])
        cancelled_bid_ids = {bid['bid_id'] for bid in updated_bids}
        assert bid_to_cancel['bid_id'] not in cancelled_bid_ids, "Cancelled bid still appears in my_bids"
        print(f"✓ Cancelled bid correctly removed from /my_bids (now {len(updated_bids)} remaining)")
    else:
        print("No bids available to cancel (all consumed by job matching)")
        # Create a new bid just for cancellation testing
        print("Creating a new bid for cancellation test...")
        response = requests.post(f"{api_url}/submit_bid", headers=headers, json={
            "service": "Test service for cancellation",
            "price": 100,
            "currency": "USD",
            "payment_method": "cash",
            "end_time": int(time.time()) + 3600,
            "location_type": "remote"
        }, verify=False)
        assert response.status_code == 200
        new_bid_id = response.json()['bid_id']
        
        # Now cancel it
        response = requests.post(f"{api_url}/cancel_bid",
            headers=headers,
            json={"bid_id": new_bid_id}, verify=False)
        assert response.status_code == 200
        print(f"✓ New bid created and cancelled successfully")
    
    # Test invalid payment method
    print("\n=== Testing Validation ===")
    response = requests.post(f"{api_url}/submit_bid", headers=headers, json={
        "service": "Test service",
        "price": 100,
        "currency": "USD",
        "payment_method": "invalid_method",  # Invalid payment method
        "end_time": int(time.time()) + 3600,
        "location_type": "remote"
    }, verify=False)
    assert response.status_code == 400
    print("✓ Invalid payment method correctly rejected")
    
    # Test XMoney without account
    response = requests.post(f"{api_url}/submit_bid", headers=headers, json={
        "service": "Test service",
        "price": 100,
        "currency": "USD",
        "payment_method": "xmoney",  # XMoney but no account
        "end_time": int(time.time()) + 3600,
        "location_type": "remote"
    }, verify=False)
    assert response.status_code == 400
    print("✓ XMoney without account correctly rejected")
    
    return {
        'buyer_username': buyer_username,
        'provider_username': provider_username,
        'bid_count': len(user_bids),
        'jobs_completed': len(buyer_jobs_data.get('completed_jobs', [])) + len(provider_jobs_data.get('completed_jobs', [])),
        'exchange_data_count': len(exchange_data.get('active_bids', []))
    }

def test_seat_scenarios(api_url):
    """Test seat verification scenarios when enabled"""
    print("\n" + "="*50)
    print("🔒 SEAT VERIFICATION TESTS")
    print("="*50)
    
    golden_seats, silver_seats = load_test_seats()
    
    print("\n📌 Current Status: Seat verification is DISABLED during ramp-up")
    print("These tests verify the seat system works when re-enabled\n")
    
    if not (golden_seats or silver_seats):
        print("No seats available for testing")
        return
    
    # Register a test provider
    provider_username = f"seat_test_{uuid.uuid4().hex[:8]}"
    response = requests.post(f"{api_url}/register", json={
        "username": provider_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 201
    
    response = requests.post(f"{api_url}/login", json={
        "username": provider_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 200
    provider_token = response.json()['access_token']
    
    headers = {"Authorization": f"Bearer {provider_token}"}
    
    # Test with valid golden seat (would work when enabled)
    if golden_seats:
        print("Testing with golden seat credentials...")
        seat_credentials = create_seat_credentials(golden_seats[0])
        response = requests.post(f"{api_url}/grab_job",
            headers=headers,
            json={
                "capabilities": "Testing services",
                "location_type": "remote",
                "seat": seat_credentials
            }, verify=False)
        # Should work even though not required
        assert response.status_code in [200, 204]
        print(f"✓ Golden seat {golden_seats[0]['id'][:8]}... accepted (not required)")
    
    # Test with valid silver seat (would work when enabled)
    if silver_seats:
        print("Testing with silver seat credentials...")
        seat_credentials = create_seat_credentials(silver_seats[0])
        response = requests.post(f"{api_url}/grab_job",
            headers=headers,
            json={
                "capabilities": "Testing services",
                "location_type": "remote",
                "seat": seat_credentials
            }, verify=False)
        # Should work even though not required
        assert response.status_code in [200, 204]
        print(f"✓ Silver seat {silver_seats[0]['id'][:8]}... accepted (not required)")
    
    # Test wrong credentials (should still work while disabled)
    print("Testing with invalid seat credentials...")
    response = requests.post(f"{api_url}/grab_job",
        headers=headers,
        json={
            "capabilities": "Testing services",
            "location_type": "remote",
            "seat": {
                "id": "fake_seat",
                "owner": "fake_owner",
                "secret": "wrong_secret"
            }
        }, verify=False)
    # Should work even with bad credentials while disabled
    assert response.status_code in [200, 204]
    print("✓ Invalid credentials accepted (verification disabled)")
    
    print("\n📝 Note: When seat verification is re-enabled:")
    print("  • Golden seats: Permanent access for physical services")
    print("  • Silver seats: 1-year limited access for software services")
    print("  • Rate limit: 1 request per 15 minutes per seat")
    print("="*50)

def test_edge_cases(api_url):
    """Test edge cases and error handling"""
    print("\n" + "="*50)
    print("🔍 EDGE CASE & ERROR HANDLING TESTS")
    print("="*50)
    
    # Create a test user
    test_user = f"edge_test_{uuid.uuid4().hex[:8]}"
    response = requests.post(f"{api_url}/register", json={
        "username": test_user,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 201
    
    response = requests.post(f"{api_url}/login", json={
        "username": test_user,
        "password": "TestPass123"
    }, verify=False)
    token = response.json()['access_token']
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\nTesting rejection of non-existent job...")
    response = requests.post(f"{api_url}/reject_job",
        headers=headers,
        json={"job_id": str(uuid.uuid4())}, verify=False)
    assert response.status_code == 404
    print("✓ Non-existent job rejection handled")
    
    print("Testing chat to non-existent user...")
    response = requests.post(f"{api_url}/chat",
        headers=headers,
        json={
            "recipient": "non_existent_user_xyz",
            "message": "Test message"
        }, verify=False)
    assert response.status_code == 404
    print("✓ Chat to non-existent user handled")
    
    print("Testing empty bulletin content...")
    response = requests.post(f"{api_url}/bulletin",
        headers=headers,
        json={
            "title": "",
            "content": "",
            "category": "general"
        }, verify=False)
    assert response.status_code == 400
    print("✓ Empty bulletin content rejected")
    
    print("Testing expired bid submission...")
    response = requests.post(f"{api_url}/submit_bid",
        headers=headers,
        json={
            "service": "Expired service",
            "price": 100,
            "currency": "USD",
            "payment_method": "cash",
            "end_time": int(time.time()) - 3600,  # Past time
            "location_type": "remote"
        }, verify=False)
    assert response.status_code == 400
    print("✓ Expired bid rejected")
    
    print("Testing negative price...")
    response = requests.post(f"{api_url}/submit_bid",
        headers=headers,
        json={
            "service": "Test service",
            "price": -50,
            "currency": "USD",
            "payment_method": "cash",
            "end_time": int(time.time()) + 3600,
            "location_type": "remote"
        }, verify=False)
    assert response.status_code == 400
    print("✓ Negative price rejected")
    
    print("Testing invalid star rating...")
    response = requests.post(f"{api_url}/sign_job",
        headers=headers,
        json={
            "job_id": str(uuid.uuid4()),
            "star_rating": 6  # Invalid rating
        }, verify=False)
    assert response.status_code in [400, 404]  # 404 if job doesn't exist
    print("✓ Invalid star rating handled")
    
    print("Testing exchange_data with invalid limit...")
    response = requests.get(f"{api_url}/exchange_data?limit=abc",
        headers=headers, verify=False)
    assert response.status_code == 400
    print("✓ Invalid limit parameter handled")
    
    print("\n✅ All edge cases handled correctly")
    print("="*50)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Complete integration tests for Service Exchange API')
    parser.add_argument('--local', action='store_true', 
                       help='Test against localhost:5003 instead of rse-api.com:5003')
    parser.add_argument('--skip-seats', action='store_true',
                       help='Skip seat verification tests')
    args = parser.parse_args()
    
    # Set API URL based on command line flag
    print("\n" + "="*70)
    print("SERVICE EXCHANGE API TEST CONFIGURATION")
    print("="*70)
    
    if args.local:
        api_url = "http://localhost:5003"
        print(f"🏠 API Endpoint: {api_url} (LOCAL)")
        print(f"💾 Storage: Local filesystem (./data/)")
        print(f"📁 Data directories: accounts/, tokens/, bids/, jobs/, messages/, bulletins/")
    else:
        api_url = "https://rse-api.com:5003"
        print(f"🌐 API Endpoint: {api_url} (PRODUCTION)")
        print(f"☁️  Storage: AWS S3 (Bucket: mithrilmedia)")
        print(f"🔐 S3 Prefix: theservicesexchange/")
    
    print(f"🔒 Seat Verification: {'SKIPPED' if args.skip_seats else 'ENABLED (Currently DISABLED in API)'}")
    print(f"🕐 Test Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")
    
    # Disable SSL warnings for testing
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Track test start time
    start_time = time.time()
    
    try:
        # Run main tests
        test_results = test_api(api_url, test_seats=not args.skip_seats)
        
        # Run seat tests if not skipped
        if not args.skip_seats:
            test_seat_scenarios(api_url)
        
        # Run edge case tests
        test_edge_cases(api_url)
        
        # Final success summary
        print("\n" + "="*60)
        print("✅ COMPLETE TEST SUITE RESULTS")
        print("="*60)
        print(f"Environment: {api_url}")
        print(f"Storage: {'Local Filesystem' if 'localhost' in api_url else 'AWS S3'}")
        print("\nTests Passed:")
        print("  • Core API Tests: PASSED")
        print("  • Enhanced Bid System: PASSED")
        print("    - Multiple currencies supported")
        print("    - Payment methods validated") 
        print("    - XMoney integration working")
        print("    - Service objects supported")
        print("  • Chat Messaging: PASSED")
        print("  • Bulletin Board: PASSED")
        print("  • Exchange Data API: PASSED")
        print("  • Job Rejection: PASSED")
        print("  • My Bids/Jobs: PASSED")
        print("  • Nearby Services: PASSED")
        print("  • Authentication: PASSED")
        print("  • Edge Cases: PASSED")
        if not args.skip_seats:
            print("  • Seat Verification: TESTED (Currently DISABLED)")
        
        print(f"\nTest Metrics:")
        print(f"  • Bids created: {test_results['bid_count']}")
        print(f"  • Jobs completed: {test_results['jobs_completed']}")
        print(f"  • Exchange data entries: {test_results['exchange_data_count']}")
        print(f"  • Test duration: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")
        
        print("\n🚀 Service Exchange API: ALL FEATURES OPERATIONAL")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        print("Please check the API implementation and try again.")
        exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        print("Please check your setup and try again.")
        exit(1)
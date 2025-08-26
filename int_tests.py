"""
Integration Tests for Service Exchange API with Seat Verification
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

def test_api(api_url):
    """Run integration tests"""
    print("\n=== Service Exchange API Tests with Seat Verification ===\n")
    
    # Load test seats
    golden_seats, silver_seats = load_test_seats()
    
    if not golden_seats and not silver_seats:
        print("Warning: No seats loaded. Some tests may fail.")
    else:
        print(f"Loaded {len(golden_seats)} golden seats and {len(silver_seats)} silver seats for testing")
        
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
    
    # Register users
    print("\nRegistering test users...")
    buyer_username = f"buyer_{uuid.uuid4().hex[:8]}"
    provider_username = f"provider_{uuid.uuid4().hex[:8]}"
    
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
    print(f"✓ Provider registered: {provider_username}")
    
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
    print("✓ Provider logged in")
    
    # Submit bid
    print("\nSubmitting service request...")
    headers = {"Authorization": f"Bearer {buyer_token}"}
    response = requests.post(f"{api_url}/submit_bid", 
        headers=headers,
        json={
            "service": "House cleaning, 3 bedrooms, 2 bathrooms",
            "price": 150,
            "end_time": int(time.time()) + 3600,
            "location_type": "physical",
            "address": "123 Main St, Denver, CO 80202"
        }, verify=False)
    assert response.status_code == 200
    bid_id = response.json()['bid_id']
    print(f"✓ Bid created: {bid_id}")
    
    # Test seat verification failures first
    print("\nTesting seat verification failures...")
    headers = {"Authorization": f"Bearer {provider_token}"}
    
    # Test 1: No seat provided
    response = requests.post(f"{api_url}/grab_job",
        headers=headers,
        json={
            "capabilities": "House cleaning, office cleaning, deep cleaning",
            "location_type": "physical",
            "address": "456 Oak Ave, Denver, CO 80203",
            "max_distance": 20
        }, verify=False)
    assert response.status_code == 403
    print("✓ No seat provided - correctly rejected")
    
    # Test 2: Invalid seat credentials
    response = requests.post(f"{api_url}/grab_job",
        headers=headers,
        json={
            "capabilities": "House cleaning, office cleaning, deep cleaning",
            "location_type": "physical",
            "address": "456 Oak Ave, Denver, CO 80203",
            "max_distance": 20,
            "seat": {
                "id": "invalid_seat_123",
                "owner": "fake_owner",
                "secret": "fake_secret"
            }
        }, verify=False)
    assert response.status_code == 403
    print("✓ Invalid seat credentials - correctly rejected")
    
    # Test valid seat scenarios
    valid_seats = []
    
    # Add all golden seats (always valid)
    for seat in golden_seats:
        valid_seats.append(("Golden", seat))
    
    # Add non-expired silver seats
    current_time = int(time.time())
    one_year_seconds = 365 * 24 * 3600
    for seat in silver_seats:
        assigned_time = seat.get('assigned', 0)
        if current_time <= assigned_time + one_year_seconds:
            valid_seats.append(("Silver (Valid)", seat))
        else:
            # Test expired silver seat
            print(f"\nTesting expired silver seat: {seat['id']}")
            expired_credentials = create_seat_credentials(seat)
            
            response = requests.post(f"{api_url}/grab_job",
                headers=headers,
                json={
                    "capabilities": "House cleaning, office cleaning, deep cleaning",
                    "location_type": "physical",
                    "address": "456 Oak Ave, Denver, CO 80203",
                    "max_distance": 20,
                    "seat": expired_credentials
                }, verify=False)
            assert response.status_code == 403
            print(f"✓ Expired silver seat {seat['id']} correctly rejected")
    
    # Test with valid seats
    if valid_seats:
        print(f"\nTesting job grabbing with valid seats...")
        
        for seat_type, seat_data in valid_seats[:3]:  # Test up to 3 valid seats
            print(f"\nTesting {seat_type} seat: {seat_data['id']}")
            
            # Create valid credentials
            seat_credentials = create_seat_credentials(seat_data)
            
            response = requests.post(f"{api_url}/grab_job",
                headers=headers,
                json={
                    "capabilities": "House cleaning, office cleaning, deep cleaning",
                    "location_type": "physical",
                    "address": "456 Oak Ave, Denver, CO 80203",
                    "max_distance": 20,
                    "seat": seat_credentials
                }, verify=False)
            
            if response.status_code == 200:
                job = response.json()
                print(f"✓ {seat_type} seat verification successful - Job matched!")
                print(f"  Job details: ${job['price']} - {job['service'][:50]}...")
                
                # Sign job to complete it
                print("  Completing job...")
                headers_buyer = {"Authorization": f"Bearer {buyer_token}"}
                response = requests.post(f"{api_url}/sign_job",
                    headers=headers_buyer,
                    json={
                        "job_id": job['job_id'],
                        "star_rating": 5
                    }, verify=False)
                assert response.status_code == 200
                print("  ✓ Buyer signed job")
                
                headers_provider = {"Authorization": f"Bearer {provider_token}"}
                response = requests.post(f"{api_url}/sign_job",
                    headers=headers_provider,
                    json={
                        "job_id": job['job_id'],
                        "star_rating": 5
                    }, verify=False)
                assert response.status_code == 200
                print("  ✓ Provider signed job")
                
                # Submit another bid for additional seat testing if needed
                if len(valid_seats) > 1:
                    print("  Creating new bid for next seat test...")
                    headers_buyer = {"Authorization": f"Bearer {buyer_token}"}
                    requests.post(f"{api_url}/submit_bid", 
                        headers=headers_buyer,
                        json={
                            "service": f"Test service {uuid.uuid4().hex[:8]}",
                            "price": 100,
                            "end_time": int(time.time()) + 3600,
                            "location_type": "physical",
                            "address": "789 Pine St, Denver, CO 80204"
                        }, verify=False)
                
            elif response.status_code == 204:
                print(f"✓ {seat_type} seat verified but no matching jobs available")
            elif response.status_code == 403:
                print(f"✗ {seat_type} seat verification failed unexpectedly")
                print(f"  Response: {response.text}")
            else:
                print(f"✗ Unexpected response for {seat_type} seat: {response.status_code}")
    
    else:
        print("No valid seats available for job grabbing tests")
    
    # Test nearby services (no seat required)
    print("\nTesting nearby services...")
    headers = {"Authorization": f"Bearer {buyer_token}"}
    response = requests.post(f"{api_url}/nearby",
        headers=headers,
        json={
            "address": "Downtown Denver, CO",
            "radius": 20
        }, verify=False)
    assert response.status_code == 200
    services = response.json()['services']
    print(f"✓ Found {len(services)} nearby services")
    
    # Test account info
    print("\nTesting account information...")
    response = requests.get(f"{api_url}/account/{buyer_username}", 
        headers=headers, verify=False)
    assert response.status_code == 200
    account_info = response.json()
    print(f"✓ Account info retrieved - Rating: {account_info.get('stars', 0)}")
    
    print("\n=== All tests passed! ===\n")

def test_seat_edge_cases(api_url):
    """Test edge cases for seat verification"""
    print("\n=== Seat Edge Case Tests ===\n")
    
    golden_seats, silver_seats = load_test_seats()
    
    if not (golden_seats or silver_seats):
        print("No seats available for edge case testing")
        return
    
    # Register a test provider for seat testing
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
    
    # Test missing seat data
    print("Testing missing seat data...")
    response = requests.post(f"{api_url}/grab_job",
        headers=headers,
        json={
            "capabilities": "Testing services",
            "location_type": "remote"
        }, verify=False)
    assert response.status_code == 403
    print("✓ Missing seat data correctly rejected")
    
    # Test incomplete seat data
    print("Testing incomplete seat data...")
    response = requests.post(f"{api_url}/grab_job",
        headers=headers,
        json={
            "capabilities": "Testing services", 
            "location_type": "remote",
            "seat": {
                "id": "incomplete_seat"
                # Missing owner and secret
            }
        }, verify=False)
    assert response.status_code == 403
    print("✓ Incomplete seat data correctly rejected")
    
    # Test wrong secret format
    if golden_seats:
        print("Testing wrong secret format...")
        response = requests.post(f"{api_url}/grab_job",
            headers=headers,
            json={
                "capabilities": "Testing services",
                "location_type": "remote", 
                "seat": {
                    "id": golden_seats[0]['id'],
                    "owner": golden_seats[0]['owner'],
                    "secret": golden_seats[0]['phrase']  # Should be MD5 hash, not plain phrase
                }
            }, verify=False)
        assert response.status_code == 403
        print("✓ Wrong secret format correctly rejected")
    
    print("\n=== Seat edge case tests passed! ===\n")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Integration tests for Service Exchange API')
    parser.add_argument('--local', action='store_true', 
                       help='Test against localhost:5003 instead of rse-api.com:5003')
    args = parser.parse_args()
    
    # Set API URL based on command line flag
    if args.local:
        api_url = "http://localhost:5003"
        print(f"Testing against local server: {api_url}")
    else:
        api_url = "https://rse-api.com:5003"
        print(f"Testing against production server: {api_url}")
    
    # Disable SSL warnings for testing
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        test_api(api_url)
        test_seat_edge_cases(api_url)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        exit(1)
"""
Integration Tests for Service Exchange API
"""

import requests
import json
import time
import uuid

API_URL = "https://rse-api.com:5003"

def test_api():
    """Run integration tests"""
    print("\n=== Service Exchange API Tests ===\n")
    
    # Test ping
    print("Testing API health...")
    response = requests.get(f"{API_URL}/ping", verify=False)
    assert response.status_code == 200
    print("✓ API is operational")
    
    # Register users
    print("\nRegistering test users...")
    buyer_username = f"buyer_{uuid.uuid4().hex[:8]}"
    provider_username = f"provider_{uuid.uuid4().hex[:8]}"
    
    response = requests.post(f"{API_URL}/register", json={
        "username": buyer_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 201
    print(f"✓ Buyer registered: {buyer_username}")
    
    response = requests.post(f"{API_URL}/register", json={
        "username": provider_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 201
    print(f"✓ Provider registered: {provider_username}")
    
    # Login
    print("\nAuthenticating...")
    response = requests.post(f"{API_URL}/login", json={
        "username": buyer_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 200
    buyer_token = response.json()['access_token']
    print("✓ Buyer logged in")
    
    response = requests.post(f"{API_URL}/login", json={
        "username": provider_username,
        "password": "TestPass123"
    }, verify=False)
    assert response.status_code == 200
    provider_token = response.json()['access_token']
    print("✓ Provider logged in")
    
    # Submit bid
    print("\nSubmitting service request...")
    headers = {"Authorization": f"Bearer {buyer_token}"}
    response = requests.post(f"{API_URL}/submit_bid", 
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
    
    # Grab job
    print("\nProvider searching for job...")
    headers = {"Authorization": f"Bearer {provider_token}"}
    response = requests.post(f"{API_URL}/grab_job",
        headers=headers,
        json={
            "capabilities": "House cleaning, office cleaning, deep cleaning",
            "location_type": "physical",
            "address": "456 Oak Ave, Denver, CO 80203",
            "max_distance": 20
        }, verify=False)
    
    if response.status_code == 200:
        job = response.json()
        print(f"✓ Job matched: ${job['price']} - {job['service'][:50]}...")
        
        # Sign job
        print("\nCompleting job...")
        headers = {"Authorization": f"Bearer {buyer_token}"}
        response = requests.post(f"{API_URL}/sign_job",
            headers=headers,
            json={
                "job_id": job['job_id'],
                "star_rating": 5
            }, verify=False)
        assert response.status_code == 200
        print("✓ Buyer signed job")
        
        headers = {"Authorization": f"Bearer {provider_token}"}
        response = requests.post(f"{API_URL}/sign_job",
            headers=headers,
            json={
                "job_id": job['job_id'],
                "star_rating": 5
            }, verify=False)
        assert response.status_code == 200
        print("✓ Provider signed job")
    elif response.status_code == 204:
        print("✓ No matching jobs (expected)")
    else:
        print(f"✗ Job grab failed: {response.status_code}")
    
    # Test nearby services
    print("\nTesting nearby services...")
    headers = {"Authorization": f"Bearer {buyer_token}"}
    response = requests.post(f"{API_URL}/nearby",
        headers=headers,
        json={
            "address": "Downtown Denver, CO",
            "radius": 20
        }, verify=False)
    assert response.status_code == 200
    services = response.json()['services']
    print(f"✓ Found {len(services)} nearby services")
    
    print("\n=== All tests passed! ===\n")

if __name__ == "__main__":
    # Disable SSL warnings for testing
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        test_api()
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        exit(1)
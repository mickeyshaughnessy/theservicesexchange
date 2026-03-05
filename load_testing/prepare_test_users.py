#!/usr/bin/env python3
"""
Prepare test users and generate auth tokens for load testing
All test data is marked with LOAD_TEST_ prefix
"""

import requests
import json
import time
import urllib3

# Disable SSL warnings for local testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "http://localhost:5003"
LOAD_TEST_HEADERS = {"X-Load-Test": "LOAD_TESTING"}

def create_test_user(username, password):
    """Create a test user"""
    response = requests.post(
        f"{API_URL}/register",
        json={"username": username, "password": password},
        headers=LOAD_TEST_HEADERS,
        verify=False
    )
    if response.status_code in [201, 400]:  # 400 if user already exists
        print(f"✓ User {username} ready")
        return True
    else:
        print(f"✗ Failed to create {username}: {response.status_code}")
        return False

def login_user(username, password):
    """Login and get auth token"""
    response = requests.post(
        f"{API_URL}/login",
        json={"username": username, "password": password},
        headers=LOAD_TEST_HEADERS,
        verify=False
    )
    if response.status_code == 200:
        token = response.json()['access_token']
        print(f"✓ Token for {username}: {token[:16]}...")
        return token
    else:
        print(f"✗ Failed to login {username}: {response.status_code}")
        return None

def create_test_bids(token, count=5):
    """Create test bids for load testing"""
    headers = {
        **LOAD_TEST_HEADERS,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    services = [
        "LOAD_TEST: House cleaning - 3 bedrooms",
        "LOAD_TEST: Lawn mowing and trimming",
        "LOAD_TEST: Web development - React app",
        "LOAD_TEST: Dog walking service",
        "LOAD_TEST: Graphic design - logo"
    ]
    
    bid_ids = []
    for i in range(min(count, len(services))):
        response = requests.post(
            f"{API_URL}/submit_bid",
            headers=headers,
            json={
                "service": services[i],
                "price": 100 + (i * 50),
                "currency": "USD",
                "payment_method": "cash",
                "end_time": int(time.time()) + 7200,  # 2 hours
                "location_type": "physical",
                "address": f"{i+1}00 Test St, Denver, CO 80202"
            },
            verify=False
        )
        if response.status_code == 200:
            bid_id = response.json()['bid_id']
            bid_ids.append(bid_id)
            print(f"✓ Created bid: {bid_id[:8]}...")
        else:
            print(f"✗ Failed to create bid: {response.status_code}")
    
    return bid_ids

def main():
    print("=" * 60)
    print("Preparing Load Test Environment")
    print("=" * 60)
    
    # Check API is reachable
    try:
        response = requests.get(f"{API_URL}/ping", verify=False, timeout=5)
        if response.status_code != 200:
            print(f"✗ API not responding correctly: {response.status_code}")
            return 1
        print(f"✓ API is reachable at {API_URL}")
    except Exception as e:
        print(f"✗ Cannot reach API at {API_URL}: {e}")
        return 1
    
    print("\n" + "-" * 60)
    print("Creating Test Users")
    print("-" * 60)
    
    # Create test users
    test_users = []
    for i in range(1, 11):  # Create 10 test users
        username = f"LOAD_TEST_user{i}"
        password = "LoadTest123!"
        if create_test_user(username, password):
            test_users.append((username, password))
    
    print(f"\n✓ Created {len(test_users)} test users")
    
    print("\n" + "-" * 60)
    print("Generating Auth Tokens")
    print("-" * 60)
    
    # Login and collect tokens
    tokens = {}
    for username, password in test_users[:5]:  # Login first 5 users
        token = login_user(username, password)
        if token:
            tokens[username] = token
    
    # Save tokens to file for siege
    token_file = "load_testing/test_tokens.json"
    with open(token_file, 'w') as f:
        json.dump(tokens, f, indent=2)
    print(f"\n✓ Saved {len(tokens)} tokens to {token_file}")
    
    print("\n" + "-" * 60)
    print("Creating Test Bids")
    print("-" * 60)
    
    # Create some test bids
    buyer_token = list(tokens.values())[0]
    bid_ids = create_test_bids(buyer_token, count=5)
    print(f"\n✓ Created {len(bid_ids)} test bids")
    
    print("\n" + "-" * 60)
    print("Generating Siege URL Files")
    print("-" * 60)
    
    # Generate authenticated URL files for siege
    provider_token = list(tokens.values())[1]
    
    # Read-only endpoints
    with open("load_testing/urls_readonly.txt", 'w') as f:
        f.write("# Read-only endpoints for sustained load testing\n\n")
        f.write(f"http://localhost:5003/ping\n")
        f.write(f"http://localhost:5003/health\n")
        f.write(f"http://localhost:5003/account GET\n")
        f.write(f"http://localhost:5003/my_bids GET\n")
        f.write(f"http://localhost:5003/my_jobs GET\n")
    
    print("✓ Generated urls_readonly.txt")
    
    # Workflow URLs
    with open("load_testing/urls_workflow.txt", 'w') as f:
        f.write("# Full workflow URLs\n\n")
        f.write(f"http://localhost:5003/exchange_data?limit=10 GET\n")
        f.write(f"http://localhost:5003/nearby POST {{\"address\":\"Denver, CO\",\"radius\":15}}\n")
    
    print("✓ Generated urls_workflow.txt")
    
    print("\n" + "=" * 60)
    print("✅ Load Test Environment Ready!")
    print("=" * 60)
    print("\nYou can now run load tests:")
    print("  ./load_testing/run_smoke_test.sh")
    print("  ./load_testing/run_steady_test.sh")
    print("  ./load_testing/run_stress_test.sh")
    print("\nMonitor metrics during tests:")
    print("  watch -n 2 'curl -s http://localhost:5003/metrics | python3 -m json.tool'")
    
    return 0

if __name__ == "__main__":
    exit(main())

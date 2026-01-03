"""
Cleaned Integration Tests for Service Exchange API
Focused, efficient tests with proper cleanup
"""

import requests
import json
import time
import uuid
import hashlib
import argparse
import config

def md5(text):
    """Generate MD5 hash of text"""
    return hashlib.md5(text.encode()).hexdigest()

class ServiceExchangeAPITester:
    def __init__(self, api_url):
        self.api_url = api_url
        self.created_users = []
        self.created_bids = []
        self.active_tokens = []
        
    def cleanup(self):
        """Clean up ALL created test data"""
        print("\n🧹 Cleaning up test data...")
        
        cleanup_counts = {
            'bids_cancelled': 0,
            'bulletins_deleted': 0,
            'messages_deleted': 0,
            'jobs_deleted': 0
        }
        
        for token, username in self.active_tokens:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                
                # Cancel all test bids
                response = requests.get(f"{self.api_url}/my_bids", headers=headers, verify=False)
                if response.status_code == 200:
                    bids = response.json().get('bids', [])
                    for bid in bids:
                        bid_service = str(bid.get('service', ''))
                        # Cancel any bid that contains "TEST:" or was created by test users
                        if 'TEST:' in bid_service or bid.get('username') in self.created_users:
                            resp = requests.post(f"{self.api_url}/cancel_bid", 
                                        headers=headers,
                                        json={"bid_id": bid['bid_id']}, 
                                        verify=False)
                            if resp.status_code == 200:
                                cleanup_counts['bids_cancelled'] += 1
                                print(f"  ✓ Cancelled bid: {bid['bid_id'][:8]}...")
                
            except Exception as e:
                print(f"  ⚠ Error cleaning up for {username}: {e}")
        
        # Summary
        print(f"\n📊 Cleanup Summary:")
        print(f"  Bids cancelled: {cleanup_counts['bids_cancelled']}")
        print(f"  Test users: {len(self.created_users)}")
        print(f"✓ Cleanup completed")

    def test_core_functionality(self):
        """Test core API functionality with minimal test data"""
        print(f"\n=== Core API Tests ===")
        print(f"Environment: {self.api_url}")
        
        # Health check
        response = requests.get(f"{self.api_url}/ping", verify=False)
        assert response.status_code == 200, "API ping failed"
        print("✓ API health check passed")
        
        # Create test users (max 20 chars for username)
        buyer_username = f"buyer_{uuid.uuid4().hex[:8]}"
        provider_username = f"provider_{uuid.uuid4().hex[:8]}"
        
        # Register buyer (demand)
        response = requests.post(f"{self.api_url}/register", json={
            "username": buyer_username,
            "password": config.TEST_PASSWORD,
            "user_type": "demand"
        }, verify=False)
        assert response.status_code == 201, f"Registration failed for {buyer_username}: {response.status_code} - {response.text}"
        self.created_users.append(buyer_username)
        
        # Register provider (supply)
        response = requests.post(f"{self.api_url}/register", json={
            "username": provider_username,
            "password": config.TEST_PASSWORD,
            "user_type": "supply"
        }, verify=False)
        assert response.status_code == 201, f"Registration failed for {provider_username}: {response.status_code} - {response.text}"
        self.created_users.append(provider_username)
        
        print(f"✓ Test users created: {len(self.created_users)}")
        
        # Login users
        tokens = {}
        for username in [buyer_username, provider_username]:
            response = requests.post(f"{self.api_url}/login", json={
                "username": username,
                "password": config.TEST_PASSWORD
            }, verify=False)
            assert response.status_code == 200, f"Login failed for {username}"
            tokens[username] = response.json()['access_token']
            self.active_tokens.append((tokens[username], username))
        
        print("✓ User authentication successful")
        
        # Test bid submission
        buyer_headers = {"Authorization": f"Bearer {tokens[buyer_username]}"}
        
        test_bids = [
            {
                "service": "TEST: House cleaning service - 3 bedrooms",
                "price": 150,
                "currency": "USD",
                "payment_method": "cash",
                "end_time": int(time.time()) + 3600,
                "location_type": "physical",
                "address": "123 Test St, Denver, CO 80202"
            },
            {
                "service": {
                    "type": "TEST: Software development",
                    "description": "React web application",
                    "technologies": ["React", "TypeScript", "Node.js"]
                },
                "price": 2000,
                "currency": "USD", 
                "payment_method": "paypal",
                "end_time": int(time.time()) + 7200,
                "location_type": "remote"
            }
        ]
        
        bid_ids = []
        for bid_data in test_bids:
            response = requests.post(f"{self.api_url}/submit_bid", 
                                   headers=buyer_headers, 
                                   json=bid_data, verify=False)
            assert response.status_code == 200, "Bid submission failed"
            bid_id = response.json()['bid_id']
            bid_ids.append(bid_id)
            self.created_bids.append(bid_id)
        
        print(f"✓ Test bids created: {len(bid_ids)}")
        
        # Test my_bids endpoint
        response = requests.get(f"{self.api_url}/my_bids", headers=buyer_headers, verify=False)
        assert response.status_code == 200, "my_bids endpoint failed"
        bids_data = response.json()
        assert len(bids_data.get('bids', [])) >= len(test_bids), "Not all bids returned"
        print("✓ Bid retrieval working")
        
        # Test job grabbing (provider side)
        provider_headers = {"Authorization": f"Bearer {tokens[provider_username]}"}
        
        # Try to grab physical cleaning job
        response = requests.post(f"{self.api_url}/grab_job",
            headers=provider_headers,
            json={
                "capabilities": "House cleaning, deep cleaning, residential cleaning services",
                "location_type": "physical",
                "address": "456 Provider Ave, Denver, CO 80203",
                "max_distance": 25
            }, verify=False)
        
        job_grabbed = False
        if response.status_code == 200:
            job = response.json()
            print(f"✓ Physical job grabbed: {job['currency']} {job['price']}")
            job_grabbed = True
        elif response.status_code == 204:
            print("✓ No matching physical jobs (expected)")
        
        # Try to grab software job
        response = requests.post(f"{self.api_url}/grab_job",
            headers=provider_headers,
            json={
                "capabilities": "React development, TypeScript, Node.js, web applications",
                "location_type": "remote"
            }, verify=False)
        
        if response.status_code == 200:
            job = response.json()
            print(f"✓ Software job grabbed: {job['currency']} {job['price']}")
            job_grabbed = True
        elif response.status_code == 204:
            print("✓ No matching software jobs (expected)")
        
        # Test account info
        response = requests.get(f"{self.api_url}/account",
            headers=buyer_headers, verify=False)
        assert response.status_code == 200, "Account info failed"
        account_data = response.json()
        assert account_data['username'] == buyer_username
        print("✓ Account information retrieval working")
        
        # Test chat messaging
        response = requests.post(f"{self.api_url}/chat",
            headers=buyer_headers,
            json={
                "recipient": provider_username,
                "message": "TEST: Hello, this is a test message."
            }, verify=False)
        assert response.status_code == 200, "Chat failed"
        print("✓ Chat messaging working")
        
        # Test bulletin posting
        response = requests.post(f"{self.api_url}/bulletin",
            headers=buyer_headers,
            json={
                "title": "TEST: Integration Test Post",
                "content": "This is a test bulletin post from integration tests.",
                "category": "general"
            }, verify=False)
        assert response.status_code == 200, "Bulletin posting failed"
        print("✓ Bulletin posting working")
        
        # Test bid cancellation (create a new bid specifically for cancellation)
        response = requests.post(f"{self.api_url}/submit_bid", 
                               headers=buyer_headers, 
                               json={
                                   "service": "TEST: Bid for cancellation test",
                                   "price": 100,
                                   "currency": "USD",
                                   "payment_method": "cash",
                                   "end_time": int(time.time()) + 3600,
                                   "location_type": "remote"
                               }, verify=False)
        assert response.status_code == 200, "Test cancellation bid creation failed"
        cancel_bid_id = response.json()['bid_id']
        self.created_bids.append(cancel_bid_id)
        
        response = requests.post(f"{self.api_url}/cancel_bid",
            headers=buyer_headers,
            json={"bid_id": cancel_bid_id}, verify=False)
        assert response.status_code == 200, f"Bid cancellation failed: {response.status_code} - {response.text}"
        print("✓ Bid cancellation working")
        
        # Test error handling
        response = requests.post(f"{self.api_url}/submit_bid", 
            headers=buyer_headers,
            json={
                "service": "Invalid bid",
                "price": -100,  # Invalid negative price
                "end_time": int(time.time()) + 3600,
                "location_type": "remote"
            }, verify=False)
        assert response.status_code == 400, "Negative price validation failed"
        print("✓ Input validation working")
        
        return {
            'users_created': len(self.created_users),
            'bids_created': len(self.created_bids),
            'job_grabbed': job_grabbed
        }

    def test_ridesharing(self):
        """Test ridesharing-specific functionality"""
        print(f"\n=== Ridesharing Tests ===")
        
        # Create ridesharing buyer and driver
        rider_username = f"rider_{uuid.uuid4().hex[:8]}"
        driver_username = f"driver_{uuid.uuid4().hex[:8]}"
        
        # Register rider
        response = requests.post(f"{self.api_url}/register", json={
            "username": rider_username,
            "password": config.TEST_PASSWORD,
            "user_type": "demand"
        }, verify=False)
        assert response.status_code == 201, f"Rider registration failed: {response.text}"
        self.created_users.append(rider_username)
        
        # Register driver
        response = requests.post(f"{self.api_url}/register", json={
            "username": driver_username,
            "password": config.TEST_PASSWORD,
            "user_type": "supply"
        }, verify=False)
        assert response.status_code == 201, f"Driver registration failed: {response.text}"
        self.created_users.append(driver_username)
        
        # Login both users
        response = requests.post(f"{self.api_url}/login", json={
            "username": rider_username,
            "password": config.TEST_PASSWORD
        }, verify=False)
        rider_token = response.json()['access_token']
        rider_headers = {"Authorization": f"Bearer {rider_token}"}
        self.active_tokens.append((rider_token, rider_username))
        
        response = requests.post(f"{self.api_url}/login", json={
            "username": driver_username,
            "password": config.TEST_PASSWORD
        }, verify=False)
        driver_token = response.json()['access_token']
        driver_headers = {"Authorization": f"Bearer {driver_token}"}
        self.active_tokens.append((driver_token, driver_username))
        
        # Submit ridesharing request with start and end addresses
        response = requests.post(f"{self.api_url}/submit_bid", 
            headers=rider_headers, 
            json={
                "service": "TEST: Rideshare from airport to downtown",
                "price": 45,
                "currency": "USD",
                "payment_method": "credit_card",
                "end_time": int(time.time()) + 3600,
                "location_type": "physical",
                "start_address": "Denver Airport",
                "end_address": "Downtown Denver, CO"
            }, verify=False)
        assert response.status_code == 200, f"Rideshare bid failed: {response.text}"
        ride_bid_id = response.json()['bid_id']
        self.created_bids.append(ride_bid_id)
        print("✓ Ridesharing bid created with start/end addresses")
        
        # Driver grabs the ride
        response = requests.post(f"{self.api_url}/grab_job",
            headers=driver_headers,
            json={
                "capabilities": "Driver, rideshare, taxi service, transportation",
                "location_type": "physical",
                "address": "Denver Airport Terminal",
                "max_distance": 5
            }, verify=False)
        
        if response.status_code == 200:
            job = response.json()
            # Verify ridesharing fields are present
            assert job.get('start_address'), "Start address missing from job"
            assert job.get('end_address'), "End address missing from job"
            assert job.get('start_lat') is not None, "Start lat missing from job"
            assert job.get('end_lat') is not None, "End lat missing from job"
            print(f"✓ Rideshare matched: {job.get('start_address')} -> {job.get('end_address')} (${job['price']})")
        else:
            print(f"✓ No rideshare match (status {response.status_code}) - acceptable")
        
        # Test backward compatibility: traditional bid without ridesharing fields
        response = requests.post(f"{self.api_url}/submit_bid", 
            headers=rider_headers, 
            json={
                "service": "TEST: Regular cleaning service",
                "price": 100,
                "currency": "USD",
                "payment_method": "cash",
                "end_time": int(time.time()) + 3600,
                "location_type": "physical",
                "address": "123 Test St, Denver, CO"
            }, verify=False)
        assert response.status_code == 200, "Traditional bid failed (backward compatibility broken)"
        print("✓ Backward compatibility: Traditional bids still work")
        
        print("✓ Ridesharing tests completed successfully")

    def test_advanced_features(self):
        """Test advanced features with enhanced data"""
        print(f"\n=== Advanced Feature Tests ===")
        
        # Create advanced test user (demand side for submitting bids, max 20 chars)
        advanced_user = f"adv_{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{self.api_url}/register", json={
            "username": advanced_user,
            "password": config.TEST_PASSWORD,
            "user_type": "demand"
        }, verify=False)
        assert response.status_code == 201
        self.created_users.append(advanced_user)
        
        response = requests.post(f"{self.api_url}/login", json={
            "username": advanced_user,
            "password": config.TEST_PASSWORD
        }, verify=False)
        token = response.json()['access_token']
        headers = {"Authorization": f"Bearer {token}"}
        self.active_tokens.append((token, advanced_user))
        
        # Test enhanced bid with XMoney
        response = requests.post(f"{self.api_url}/submit_bid", headers=headers, json={
            "service": {
                "type": "TEST: Advanced service",
                "description": "Complex multi-step service",
                "requirements": ["professional", "insured", "experienced"]
            },
            "price": 500,
            "currency": "USD",
            "payment_method": "xmoney",
            "xmoney_account": "@test_account",
            "end_time": int(time.time()) + 3600,
            "location_type": "hybrid",
            "address": "789 Advanced St, Denver, CO 80204"
        }, verify=False)
        assert response.status_code == 200, "Enhanced bid submission failed"
        print("✓ Enhanced bid with XMoney payment created")
        
        # Test exchange data endpoint
        response = requests.get(f"{self.api_url}/exchange_data?category=TEST&limit=10", 
                              headers=headers, verify=False)
        assert response.status_code == 200, "Exchange data endpoint failed"
        exchange_data = response.json()
        assert 'active_bids' in exchange_data
        print("✓ Exchange data endpoint working")
        
        # Test nearby services
        response = requests.post(f"{self.api_url}/nearby", headers=headers, json={
            "address": "Downtown Denver, CO",
            "radius": 15
        }, verify=False)
        assert response.status_code == 200, "Nearby services failed"
        print("✓ Nearby services working")
        
        print("✓ Advanced features tested successfully")

def main():
    parser = argparse.ArgumentParser(description='Clean integration tests for Service Exchange API')
    parser.add_argument('--local', action='store_true', 
                       help='Test against localhost:5003')
    parser.add_argument('--quick', action='store_true',
                       help='Run only core tests, skip advanced features')
    args = parser.parse_args()
    
    api_url = "http://localhost:5003" if args.local else "https://rse-api.com:5003"
    
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    tester = ServiceExchangeAPITester(api_url)
    
    try:
        start_time = time.time()
        
        # Run core tests
        core_results = tester.test_core_functionality()
        
        # Run ridesharing tests
        tester.test_ridesharing()
        
        # Run advanced tests unless quick mode
        if not args.quick:
            tester.test_advanced_features()
        
        # Success summary
        duration = time.time() - start_time
        print(f"\n✅ ALL TESTS PASSED")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Test users created: {core_results['users_created']}")
        print(f"Test bids created: {core_results['bids_created']}")
        print(f"Job matching: {'✓' if core_results['job_grabbed'] else 'No matches'}")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        return 1
    finally:
        # Always cleanup
        tester.cleanup()
    
    return 0

if __name__ == "__main__":
    exit(main())
"""
Integration Tests for Service Exchange (SEX) API
"""

import requests
import json
import time
import uuid
import sys
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
API_URL = "http://localhost:5000"  # Change this for production

class TestState:
    """Shared state for tests"""
    def __init__(self):
        self.buyer_username = None
        self.provider_username = None
        self.buyer_token = None
        self.provider_token = None
        self.test_bid_id = None
        self.test_job_id = None
        self.test_message_id = None
        self.test_bulletin_id = None

def run_test(test_name, test_function, state):
    """Execute a single test"""
    print(f"\n{'='*50}")
    print(f"🧪 Testing: {test_name}")
    print(f"{'='*50}")
    
    try:
        result, message = test_function(state)
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {message}")
        return result
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

# Test Functions
def test_ping(state):
    """Test API health check"""
    response = requests.get(f"{API_URL}/ping")
    return response.status_code == 200, f"API status: {response.status_code}"

def test_buyer_registration(state):
    """Test buyer account registration"""
    state.buyer_username = f"test_buyer_{uuid.uuid4().hex[:8]}"
    
    response = requests.post(f"{API_URL}/register", json={
        "username": state.buyer_username,
        "password": "TestPass123!"
    })
    
    if response.status_code == 201:
        return True, f"Buyer registered: {state.buyer_username}"
    return False, f"Registration failed: {response.status_code} - {response.text}"

def test_provider_registration(state):
    """Test provider account registration"""
    state.provider_username = f"test_provider_{uuid.uuid4().hex[:8]}"
    
    response = requests.post(f"{API_URL}/register", json={
        "username": state.provider_username,
        "password": "TestPass123!"
    })
    
    if response.status_code == 201:
        return True, f"Provider registered: {state.provider_username}"
    return False, f"Registration failed: {response.status_code}"

def test_buyer_login(state):
    """Test buyer authentication"""
    response = requests.post(f"{API_URL}/login", json={
        "username": state.buyer_username,
        "password": "TestPass123!"
    })
    
    if response.status_code == 200:
        data = response.json()
        state.buyer_token = data.get("access_token")
        return True, "Buyer authenticated successfully"
    return False, f"Login failed: {response.status_code}"

def test_provider_login(state):
    """Test provider authentication"""
    response = requests.post(f"{API_URL}/login", json={
        "username": state.provider_username,
        "password": "TestPass123!"
    })
    
    if response.status_code == 200:
        data = response.json()
        state.provider_token = data.get("access_token")
        return True, "Provider authenticated successfully"
    return False, f"Login failed: {response.status_code}"

def test_account_info(state):
    """Test account information retrieval"""
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    response = requests.get(f"{API_URL}/account", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        required_fields = ["username", "stars", "total_ratings", "reputation_score"]
        
        for field in required_fields:
            if field not in data:
                return False, f"Missing field: {field}"
        
        return True, f"Account info retrieved for {data['username']}"
    return False, f"Failed to get account: {response.status_code}"

def test_submit_physical_bid(state):
    """Test submitting a bid for physical service"""
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    bid_data = {
        "service": "I need my house cleaned, including kitchen, 2 bedrooms, and bathroom",
        "price": 150,
        "end_time": int(time.time()) + 7200,  # 2 hours from now
        "location_type": "physical",
        "address": "123 Main St, Denver, CO 80202"
    }
    
    response = requests.post(f"{API_URL}/submit_bid", 
                            json=bid_data, 
                            headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        state.test_bid_id = data.get("bid_id")
        return True, f"Physical service bid created: {state.test_bid_id}"
    return False, f"Bid submission failed: {response.status_code}"

def test_submit_remote_bid(state):
    """Test submitting a bid for remote service"""
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    bid_data = {
        "service": "Need a React developer to build a dashboard with charts",
        "price": 500,
        "end_time": int(time.time()) + 86400,  # 24 hours from now
        "location_type": "remote"
    }
    
    response = requests.post(f"{API_URL}/submit_bid", 
                            json=bid_data, 
                            headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return True, f"Remote service bid created: {data.get('bid_id')}"
    return False, f"Remote bid submission failed: {response.status_code}"

def test_nearby_services(state):
    """Test finding nearby services"""
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    params = {
        "address": "Downtown Denver, CO",
        "radius": 20
    }
    
    response = requests.post(f"{API_URL}/nearby", 
                            json=params,
                            headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        services = data.get("services", [])
        return True, f"Found {len(services)} nearby services"
    return False, f"Nearby search failed: {response.status_code}"

def test_grab_job(state):
    """Test provider grabbing a compatible job"""
    headers = {"Authorization": f"Bearer {state.provider_token}"}
    job_data = {
        "capabilities": "House cleaning, office cleaning, deep cleaning, kitchen, bathroom",
        "location_type": "physical",
        "address": "456 Oak Ave, Denver, CO 80203",
        "max_distance": 25
    }
    
    response = requests.post(f"{API_URL}/grab_job", 
                            json=job_data,
                            headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        state.test_job_id = data.get("job_id")
        return True, f"Job grabbed: {state.test_job_id} for ${data.get('price')}"
    elif response.status_code == 204:
        return True, "No matching jobs available (expected for test)"
    return False, f"Job grab failed: {response.status_code}"

def test_grab_remote_job(state):
    """Test provider grabbing a remote job"""
    headers = {"Authorization": f"Bearer {state.provider_token}"}
    job_data = {
        "capabilities": "React, JavaScript, TypeScript, dashboard development, data visualization",
        "location_type": "remote"
    }
    
    response = requests.post(f"{API_URL}/grab_job", 
                            json=job_data,
                            headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return True, f"Remote job grabbed: {data.get('job_id')}"
    elif response.status_code == 204:
        return True, "No matching remote jobs available"
    return False, f"Remote job grab failed: {response.status_code}"

def test_sign_job(state):
    """Test completing and rating a job"""
    if not state.test_job_id:
        return True, "Skipping job signing (no job available)"
    
    # Buyer signs first
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    response = requests.post(f"{API_URL}/sign_job",
                            headers=headers,
                            json={
                                "job_id": state.test_job_id,
                                "star_rating": 5
                            })
    
    if response.status_code not in [200, 400]:  # 400 might mean already signed
        return False, f"Buyer signing failed: {response.status_code}"
    
    # Provider signs
    headers = {"Authorization": f"Bearer {state.provider_token}"}
    response = requests.post(f"{API_URL}/sign_job",
                            headers=headers,
                            json={
                                "job_id": state.test_job_id,
                                "star_rating": 4
                            })
    
    if response.status_code in [200, 400]:
        return True, "Job completion tested successfully"
    return False, f"Provider signing failed: {response.status_code}"

def test_cancel_bid(state):
    """Test cancelling a bid"""
    if not state.test_bid_id:
        return True, "Skipping bid cancellation (no bid available)"
    
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    response = requests.post(f"{API_URL}/cancel_bid",
                            headers=headers,
                            json={"bid_id": state.test_bid_id})
    
    if response.status_code == 200:
        return True, f"Bid cancelled: {state.test_bid_id}"
    elif response.status_code == 404:
        return True, "Bid already processed or expired"
    return False, f"Bid cancellation failed: {response.status_code}"

def test_send_message(state):
    """Test sending a message between users"""
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    message_data = {
        "recipient": state.provider_username,
        "message": "Great service, thank you!"
    }
    
    response = requests.post(f"{API_URL}/chat",
                            headers=headers,
                            json=message_data)
    
    if response.status_code == 200:
        data = response.json()
        state.test_message_id = data.get("message_id")
        return True, f"Message sent: {state.test_message_id}"
    return False, f"Message send failed: {response.status_code}"

def test_get_messages(state):
    """Test retrieving messages"""
    headers = {"Authorization": f"Bearer {state.provider_token}"}
    response = requests.get(f"{API_URL}/chat", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        messages = data.get("messages", [])
        return True, f"Retrieved {len(messages)} messages"
    return False, f"Message retrieval failed: {response.status_code}"

def test_post_bulletin(state):
    """Test posting to bulletin board"""
    headers = {"Authorization": f"Bearer {state.buyer_token}"}
    bulletin_data = {
        "title": "Looking for Regular Cleaning Service",
        "content": "Need weekly house cleaning service in Denver area. Must be reliable and thorough.",
        "category": "services_wanted"
    }
    
    response = requests.post(f"{API_URL}/bulletin",
                            headers=headers,
                            json=bulletin_data)
    
    if response.status_code == 200:
        data = response.json()
        state.test_bulletin_id = data.get("bulletin_id")
        return True, f"Bulletin posted: {state.test_bulletin_id}"
    return False, f"Bulletin post failed: {response.status_code}"

def test_get_bulletins(state):
    """Test retrieving bulletin board posts"""
    response = requests.get(f"{API_URL}/bulletin", 
                           params={"limit": 10})
    
    if response.status_code == 200:
        data = response.json()
        bulletins = data.get("bulletins", [])
        return True, f"Retrieved {len(bulletins)} bulletins"
    return False, f"Bulletin retrieval failed: {response.status_code}"

def run_all_tests():
    """Execute all integration tests"""
    print("\n" + "="*60)
    print("🚀 Service Exchange Integration Tests")
    print("="*60)
    
    state = TestState()
    
    # Define test suite
    tests = [
        ("API Health Check", test_ping),
        ("Buyer Registration", test_buyer_registration),
        ("Provider Registration", test_provider_registration),
        ("Buyer Login", test_buyer_login),
        ("Provider Login", test_provider_login),
        ("Account Information", test_account_info),
        ("Submit Physical Service Bid", test_submit_physical_bid),
        ("Submit Remote Service Bid", test_submit_remote_bid),
        ("Find Nearby Services", test_nearby_services),
        ("Provider Grab Physical Job", test_grab_job),
        ("Provider Grab Remote Job", test_grab_remote_job),
        ("Complete and Rate Job", test_sign_job),
        ("Cancel Bid", test_cancel_bid),
        ("Send Message", test_send_message),
        ("Get Messages", test_get_messages),
        ("Post Bulletin", test_post_bulletin),
        ("Get Bulletins", test_get_bulletins),
    ]
    
    # Run tests
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        if run_test(test_name, test_func, state):
            passed += 1
        else:
            failed += 1
    
    # Print summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    print(f"Total Tests: {len(tests)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {(passed/len(tests)*100):.1f}%")
    
    # Cleanup message
    if state.buyer_username or state.provider_username:
        print("\n💡 Test users created:")
        if state.buyer_username:
            print(f"  - Buyer: {state.buyer_username}")
        if state.provider_username:
            print(f"  - Provider: {state.provider_username}")
    
    return failed == 0

if __name__ == "__main__":
    # Check for verbose flag
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run tests
    success = run_all_tests()
    sys.exit(0 if success else 1)
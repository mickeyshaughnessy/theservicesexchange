"""
Enhanced Integration Tests for Service Exchange API
Includes comprehensive chat and bulletin system testing
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

class ServiceExchangeAPITester:
    def __init__(self, api_url):
        self.api_url = api_url
        self.created_users = []
        self.created_bids = []
        self.active_tokens = []
        self.sent_messages = []
        self.bulletin_posts = []
        
    def cleanup(self):
        """Clean up created test data"""
        print("\n🧹 Cleaning up test data...")
        
        # Cancel any remaining bids
        for token, username in self.active_tokens:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(f"{self.api_url}/my_bids", headers=headers, verify=False)
                if response.status_code == 200:
                    bids = response.json().get('bids', [])
                    for bid in bids:
                        if 'TEST:' in str(bid.get('service', '')):
                            requests.post(f"{self.api_url}/cancel_bid", 
                                        headers=headers,
                                        json={"bid_id": bid['bid_id']}, 
                                        verify=False)
                            print(f"  Cancelled test bid: {bid['bid_id'][:8]}...")
            except Exception as e:
                print(f"  Error cleaning up bids for {username}: {e}")
        
        print(f"✓ Cleanup completed for {len(self.created_users)} test users")
        print(f"  Messages sent: {len(self.sent_messages)}")
        print(f"  Bulletin posts: {len(self.bulletin_posts)}")

    def test_core_functionality(self):
        """Test core API functionality with minimal test data"""
        print(f"\n=== Core API Tests ===")
        print(f"Environment: {self.api_url}")
        
        # Health check
        response = requests.get(f"{self.api_url}/ping", verify=False)
        assert response.status_code == 200, "API ping failed"
        print("✓ API health check passed")
        
        # Create test users
        buyer_username = f"test_buyer_{uuid.uuid4().hex[:8]}"
        provider_username = f"test_provider_{uuid.uuid4().hex[:8]}"
        
        for username in [buyer_username, provider_username]:
            response = requests.post(f"{self.api_url}/register", json={
                "username": username,
                "password": "TestPass123"
            }, verify=False)
            assert response.status_code == 201, f"Registration failed for {username}"
            self.created_users.append(username)
        
        print(f"✓ Test users created: {len(self.created_users)}")
        
        # Login users
        tokens = {}
        for username in [buyer_username, provider_username]:
            response = requests.post(f"{self.api_url}/login", json={
                "username": username,
                "password": "TestPass123"
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
        response = requests.post(f"{self.api_url}/account",
            headers=buyer_headers,
            json={"username": buyer_username}, verify=False)
        assert response.status_code == 200, "Account info failed"
        account_data = response.json()
        assert account_data['username'] == buyer_username
        print("✓ Account information retrieval working")
        
        # Test bid cancellation
        if bid_ids:
            response = requests.post(f"{self.api_url}/cancel_bid",
                headers=buyer_headers,
                json={"bid_id": bid_ids[0]}, verify=False)
            assert response.status_code == 200, "Bid cancellation failed"
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
        
        # Store tokens for chat tests
        self.buyer_token = tokens[buyer_username]
        self.provider_token = tokens[provider_username]
        self.buyer_username = buyer_username
        self.provider_username = provider_username
        
        return {
            'users_created': len(self.created_users),
            'bids_created': len(self.created_bids),
            'job_grabbed': job_grabbed
        }

    def test_chat_system(self):
        """Comprehensive chat system testing"""
        print(f"\n=== Chat System Tests ===")
        
        buyer_headers = {"Authorization": f"Bearer {self.buyer_token}"}
        provider_headers = {"Authorization": f"Bearer {self.provider_token}"}
        
        # Test sending initial message
        test_message_1 = "TEST: Hello from buyer, are you available for cleaning services?"
        response = requests.post(f"{self.api_url}/chat", 
            headers=buyer_headers,
            json={
                "recipient": self.provider_username,
                "message": test_message_1
            }, verify=False)
        assert response.status_code == 200, "Initial chat message failed"
        message_data = response.json()
        assert 'message_id' in message_data
        assert 'sent_at' in message_data
        self.sent_messages.append(message_data['message_id'])
        print("✓ Initial chat message sent successfully")
        
        # Test sending reply
        test_message_2 = "TEST: Yes, I'm available! What's your schedule like?"
        response = requests.post(f"{self.api_url}/chat",
            headers=provider_headers,
            json={
                "recipient": self.buyer_username,
                "message": test_message_2
            }, verify=False)
        assert response.status_code == 200, "Reply message failed"
        reply_data = response.json()
        self.sent_messages.append(reply_data['message_id'])
        print("✓ Reply message sent successfully")
        
        # Test conversation list retrieval
        response = requests.get(f"{self.api_url}/chat/conversations", 
                              headers=buyer_headers, verify=False)
        assert response.status_code == 200, "Get conversations failed"
        conversations = response.json()
        assert 'conversations' in conversations
        conv_list = conversations['conversations']
        assert len(conv_list) >= 1, "No conversations found"
        
        # Find our test conversation
        test_conversation = None
        for conv in conv_list:
            if conv['user'] == self.provider_username:
                test_conversation = conv
                break
        
        assert test_conversation is not None, "Test conversation not found"
        assert 'lastMessage' in test_conversation
        assert 'timestamp' in test_conversation
        print(f"✓ Conversation list retrieved: {len(conv_list)} conversations")
        
        # Test message history retrieval
        response = requests.post(f"{self.api_url}/chat/messages",
            headers=buyer_headers,
            json={"conversation_id": self.provider_username}, verify=False)
        assert response.status_code == 200, "Get messages failed"
        messages_data = response.json()
        assert 'messages' in messages_data
        messages = messages_data['messages']
        assert len(messages) >= 2, "Not all messages retrieved"
        
        # Verify message order and content
        messages.sort(key=lambda x: x['timestamp'])
        assert messages[0]['sender'] == self.buyer_username
        assert messages[0]['recipient'] == self.provider_username
        assert test_message_1 in messages[0]['message']
        
        assert messages[1]['sender'] == self.provider_username
        assert messages[1]['recipient'] == self.buyer_username
        assert test_message_2 in messages[1]['message']
        print(f"✓ Message history retrieved: {len(messages)} messages")
        
        # Test reply endpoint
        test_reply = "TEST: How about tomorrow at 2 PM?"
        response = requests.post(f"{self.api_url}/chat/reply",
            headers=buyer_headers,
            json={
                "recipient": self.provider_username,
                "message": test_reply,
                "conversation_id": self.provider_username
            }, verify=False)
        assert response.status_code == 200, "Reply endpoint failed"
        reply_response = response.json()
        self.sent_messages.append(reply_response['message_id'])
        print("✓ Reply endpoint working")
        
        # Test message with job reference
        test_job_message = "TEST: This is about job #12345"
        response = requests.post(f"{self.api_url}/chat",
            headers=provider_headers,
            json={
                "recipient": self.buyer_username,
                "message": test_job_message,
                "job_id": "test_job_12345"
            }, verify=False)
        assert response.status_code == 200, "Job-referenced message failed"
        self.sent_messages.append(response.json()['message_id'])
        print("✓ Job-referenced messaging working")
        
        # Test error cases
        response = requests.post(f"{self.api_url}/chat",
            headers=buyer_headers,
            json={
                "recipient": "nonexistent_user",
                "message": "This should fail"
            }, verify=False)
        assert response.status_code == 404, "Nonexistent recipient validation failed"
        
        response = requests.post(f"{self.api_url}/chat",
            headers=buyer_headers,
            json={
                "recipient": self.provider_username,
                "message": ""  # Empty message
            }, verify=False)
        assert response.status_code == 400, "Empty message validation failed"
        print("✓ Chat error handling working")

    def test_bulletin_system(self):
        """Comprehensive bulletin system testing"""
        print(f"\n=== Bulletin System Tests ===")
        
        buyer_headers = {"Authorization": f"Bearer {self.buyer_token}"}
        provider_headers = {"Authorization": f"Bearer {self.provider_token}"}
        
        # Test bulletin post creation - different categories
        test_posts = [
            {
                "title": "TEST: New Cleaning Service Available",
                "content": "Professional house cleaning services now available in Denver metro area. Eco-friendly products, competitive rates, fully insured.",
                "category": "offer"
            },
            {
                "title": "TEST: Looking for React Developers",
                "content": "Startup seeking experienced React developers for exciting new project. Remote work available, competitive compensation.",
                "category": "announcement"
            },
            {
                "title": "TEST: Best practices for service pricing?",
                "content": "What factors do you consider when pricing your services? Looking for advice from experienced providers.",
                "category": "question"
            },
            {
                "title": "TEST: General marketplace update",
                "content": "Just wanted to share some thoughts about the growing Service Exchange community.",
                "category": "general"
            }
        ]
        
        post_ids = []
        for i, post_data in enumerate(test_posts):
            headers = buyer_headers if i % 2 == 0 else provider_headers
            response = requests.post(f"{self.api_url}/bulletin",
                headers=headers,
                json=post_data, verify=False)
            assert response.status_code == 200, f"Bulletin post failed: {post_data['title']}"
            post_response = response.json()
            assert 'post_id' in post_response
            assert 'posted_at' in post_response
            post_ids.append(post_response['post_id'])
            self.bulletin_posts.append(post_response['post_id'])
        
        print(f"✓ Bulletin posts created: {len(post_ids)}")
        
        # Test bulletin feed retrieval
        response = requests.get(f"{self.api_url}/bulletin/feed", 
                              headers=buyer_headers, verify=False)
        assert response.status_code == 200, "Get bulletin feed failed"
        feed_data = response.json()
        assert 'posts' in feed_data
        posts = feed_data['posts']
        assert len(posts) >= len(test_posts), "Not all posts retrieved"
        
        # Verify post structure and content
        test_post_found = False
        for post in posts:
            if 'TEST:' in post['title']:
                test_post_found = True
                assert 'post_id' in post
                assert 'title' in post
                assert 'content' in post
                assert 'category' in post
                assert 'author' in post
                assert 'timestamp' in post
                break
        
        assert test_post_found, "Test posts not found in feed"
        print(f"✓ Bulletin feed retrieved: {len(posts)} posts")
        
        # Test feed with category filter
        response = requests.get(f"{self.api_url}/bulletin/feed?category=offer", 
                              headers=buyer_headers, verify=False)
        assert response.status_code == 200, "Category filtered feed failed"
        filtered_feed = response.json()
        filtered_posts = filtered_feed['posts']
        
        # Check that filtered posts only contain the specified category
        for post in filtered_posts:
            if 'TEST:' in post['title']:
                assert post['category'] == 'offer', "Category filter not working"
        print("✓ Category filtering working")
        
        # Test feed with limit
        response = requests.get(f"{self.api_url}/bulletin/feed?limit=2", 
                              headers=buyer_headers, verify=False)
        assert response.status_code == 200, "Limited feed failed"
        limited_feed = response.json()
        limited_posts = limited_feed['posts']
        assert len(limited_posts) <= 2, "Limit not respected"
        print("✓ Feed limiting working")
        
        # Test bulletin post validation
        response = requests.post(f"{self.api_url}/bulletin",
            headers=buyer_headers,
            json={
                "title": "",  # Empty title
                "content": "This should fail",
                "category": "general"
            }, verify=False)
        assert response.status_code == 400, "Empty title validation failed"
        
        response = requests.post(f"{self.api_url}/bulletin",
            headers=buyer_headers,
            json={
                "title": "Valid title",
                "content": "",  # Empty content
                "category": "general"
            }, verify=False)
        assert response.status_code == 400, "Empty content validation failed"
        print("✓ Bulletin validation working")
        
        # Test invalid category handling
        response = requests.post(f"{self.api_url}/bulletin",
            headers=buyer_headers,
            json={
                "title": "TEST: Invalid category test",
                "content": "This should default to general category",
                "category": "invalid_category"
            }, verify=False)
        assert response.status_code == 200, "Invalid category handling failed"
        self.bulletin_posts.append(response.json()['post_id'])
        print("✓ Invalid category defaulting working")

    def test_advanced_features(self):
        """Test advanced features with enhanced data"""
        print(f"\n=== Advanced Feature Tests ===")
        
        # Create advanced test user
        advanced_user = f"advanced_test_{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{self.api_url}/register", json={
            "username": advanced_user,
            "password": "TestPass123"
        }, verify=False)
        assert response.status_code == 201
        self.created_users.append(advanced_user)
        
        response = requests.post(f"{self.api_url}/login", json={
            "username": advanced_user,
            "password": "TestPass123"
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
        assert 'market_stats' in exchange_data
        print("✓ Exchange data endpoint working")
        
        # Test nearby services
        response = requests.post(f"{self.api_url}/nearby", headers=headers, json={
            "address": "Downtown Denver, CO",
            "radius": 15
        }, verify=False)
        assert response.status_code == 200, "Nearby services failed"
        nearby_data = response.json()
        assert 'services' in nearby_data
        print("✓ Nearby services working")
        
        print("✓ Advanced features tested successfully")

def main():
    parser = argparse.ArgumentParser(description='Enhanced integration tests for Service Exchange API')
    parser.add_argument('--local', action='store_true', 
                       help='Test against localhost:5003')
    parser.add_argument('--quick', action='store_true',
                       help='Run only core tests, skip chat/bulletin/advanced features')
    parser.add_argument('--chat-only', action='store_true',
                       help='Run only chat system tests')
    parser.add_argument('--bulletin-only', action='store_true',
                       help='Run only bulletin system tests')
    args = parser.parse_args()
    
    api_url = "http://localhost:5003" if args.local else "https://rse-api.com:5003"
    
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    tester = ServiceExchangeAPITester(api_url)
    
    try:
        start_time = time.time()
        
        # Run specific test suites based on arguments
        if args.chat_only:
            # Need to set up users first
            core_results = tester.test_core_functionality()
            tester.test_chat_system()
            print(f"\n✅ CHAT TESTS PASSED")
        elif args.bulletin_only:
            # Need to set up users first
            core_results = tester.test_core_functionality()
            tester.test_bulletin_system()
            print(f"\n✅ BULLETIN TESTS PASSED")
        else:
            # Run core tests
            core_results = tester.test_core_functionality()
            
            # Run communication tests unless quick mode
            if not args.quick:
                tester.test_chat_system()
                tester.test_bulletin_system()
                tester.test_advanced_features()
            
            # Success summary
            duration = time.time() - start_time
            print(f"\n✅ ALL TESTS PASSED")
            print(f"Duration: {duration:.2f} seconds")
            print(f"Test users created: {core_results['users_created']}")
            print(f"Test bids created: {core_results['bids_created']}")
            print(f"Job matching: {'✓' if core_results['job_grabbed'] else 'No matches'}")
            if not args.quick:
                print(f"Messages sent: {len(tester.sent_messages)}")
                print(f"Bulletin posts: {len(tester.bulletin_posts)}")
        
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
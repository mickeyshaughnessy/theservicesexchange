#!/usr/bin/env python3
"""
Demand Monitoring Script for Service Exchange
Creates test service requests to maintain marketplace activity
"""

import requests
import json
import time
import random
import uuid
import argparse
from datetime import datetime, timedelta

class DemandMonitor:
    def __init__(self, api_url, interval=300):
        self.api_url = api_url
        self.interval = interval  # seconds between demand creation
        self.test_users = []
        self.active_tokens = []
        
        # Service templates that match common provider capabilities
        self.physical_services = [
            {
                "template": "TEST: House cleaning service - {rooms} bedrooms, {bathrooms} bathrooms",
                "price_range": (120, 250),
                "location_addresses": [
                    "123 Elm St, Denver, CO 80202",
                    "456 Oak Ave, Denver, CO 80203", 
                    "789 Pine Rd, Denver, CO 80204",
                    "321 Maple Dr, Denver, CO 80205"
                ],
                "variations": {
                    "rooms": [2, 3, 4, 5],
                    "bathrooms": [1, 2, 3]
                }
            },
            {
                "template": "TEST: Home repair - {repair_type} needed",
                "price_range": (150, 400),
                "location_addresses": [
                    "555 Repair St, Denver, CO 80206",
                    "777 Fix Ave, Denver, CO 80207",
                    "999 Mend Rd, Denver, CO 80208"
                ],
                "variations": {
                    "repair_type": ["plumbing", "electrical", "drywall", "painting", "flooring"]
                }
            },
            {
                "template": "TEST: Landscaping service - {service_type}",
                "price_range": (200, 500),
                "location_addresses": [
                    "111 Garden Way, Denver, CO 80209",
                    "222 Lawn St, Denver, CO 80210",
                    "333 Yard Ave, Denver, CO 80211"
                ],
                "variations": {
                    "service_type": ["lawn mowing", "tree trimming", "garden design", "snow removal"]
                }
            }
        ]
        
        self.software_services = [
            {
                "template": "TEST: {app_type} web application development",
                "price_range": (1500, 5000),
                "technologies": ["React", "Vue.js", "Angular", "Node.js", "Python", "Django"],
                "variations": {
                    "app_type": ["E-commerce", "Social media", "Business", "Educational", "Portfolio"]
                }
            },
            {
                "template": "TEST: {task_type} automation script",
                "price_range": (300, 1200),
                "technologies": ["Python", "JavaScript", "automation", "scripting"],
                "variations": {
                    "task_type": ["Data processing", "File management", "Email", "Report generation", "API integration"]
                }
            },
            {
                "template": "TEST: Mobile app development - {platform}",
                "price_range": (2000, 8000),
                "technologies": ["React Native", "Flutter", "iOS", "Android", "mobile"],
                "variations": {
                    "platform": ["iOS", "Android", "cross-platform"]
                }
            }
        ]

    def create_test_user(self):
        """Create a test user for demand generation"""
        username = f"demand_bot_{uuid.uuid4().hex[:8]}"
        
        try:
            # Register
            response = requests.post(f"{self.api_url}/register", json={
                "username": username,
                "password": "DemandBot123!"
            }, verify=False)
            
            if response.status_code != 201:
                print(f"Failed to register {username}: {response.status_code}")
                return None
            
            # Login
            response = requests.post(f"{self.api_url}/login", json={
                "username": username,
                "password": "DemandBot123!"
            }, verify=False)
            
            if response.status_code != 200:
                print(f"Failed to login {username}: {response.status_code}")
                return None
            
            token = response.json()['access_token']
            self.test_users.append(username)
            self.active_tokens.append(token)
            
            print(f"✓ Created demand bot: {username}")
            return token
            
        except Exception as e:
            print(f"Error creating test user: {e}")
            return None

    def generate_physical_demand(self, token):
        """Generate a physical service demand"""
        service_template = random.choice(self.physical_services)
        
        # Generate service description with variations
        description = service_template["template"]
        for key, values in service_template["variations"].items():
            value = random.choice(values)
            description = description.format(**{key: value})
        
        # Random price within range
        price = random.uniform(*service_template["price_range"])
        
        # Random address
        address = random.choice(service_template["location_addresses"])
        
        # Random duration (1-7 days)
        duration_hours = random.randint(24, 168)
        
        demand_data = {
            "service": description,
            "price": round(price, 2),
            "currency": "USD",
            "payment_method": random.choice(["cash", "credit_card", "paypal", "venmo"]),
            "end_time": int(time.time()) + (duration_hours * 3600),
            "location_type": "physical",
            "address": address
        }
        
        return demand_data

    def generate_software_demand(self, token):
        """Generate a software service demand"""
        service_template = random.choice(self.software_services)
        
        # Generate service description
        description = service_template["template"]
        for key, values in service_template["variations"].items():
            value = random.choice(values)
            description = description.format(**{key: value})
        
        # Create structured service object for software
        service_obj = {
            "type": "TEST: software_development",
            "description": description,
            "technologies": random.sample(service_template["technologies"], 
                                        random.randint(2, 4)),
            "timeline": f"{random.randint(2, 8)} weeks",
            "complexity": random.choice(["simple", "moderate", "complex"])
        }
        
        # Random price within range
        price = random.uniform(*service_template["price_range"])
        
        # Random duration (3-14 days for software projects)
        duration_hours = random.randint(72, 336)
        
        demand_data = {
            "service": service_obj,
            "price": round(price, 2),
            "currency": "USD",
            "payment_method": random.choice(["paypal", "bank_transfer", "credit_card"]),
            "end_time": int(time.time()) + (duration_hours * 3600),
            "location_type": "remote"
        }
        
        return demand_data

    def submit_demand(self, token, demand_data):
        """Submit a demand to the API"""
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = requests.post(f"{self.api_url}/submit_bid", 
                                   headers=headers, 
                                   json=demand_data, 
                                   verify=False)
            
            if response.status_code == 200:
                bid_id = response.json()['bid_id']
                service_desc = (json.dumps(demand_data['service']) 
                              if isinstance(demand_data['service'], dict) 
                              else demand_data['service'])
                print(f"✓ Demand created: {service_desc[:50]}... | ${demand_data['price']} | {bid_id[:8]}...")
                return bid_id
            else:
                error_data = response.json() if response.content else {}
                print(f"✗ Failed to create demand: {response.status_code} - {error_data.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            print(f"✗ Error submitting demand: {e}")
            return None

    def cleanup_expired_bids(self, token):
        """Clean up expired test bids"""
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = requests.get(f"{self.api_url}/my_bids", headers=headers, verify=False)
            if response.status_code == 200:
                bids = response.json().get('bids', [])
                current_time = int(time.time())
                
                for bid in bids:
                    # Only clean up TEST bids that are close to expiring
                    service_str = (json.dumps(bid.get('service', '')) 
                                 if isinstance(bid.get('service'), dict) 
                                 else str(bid.get('service', '')))
                    
                    if 'TEST:' in service_str and bid.get('end_time', 0) < current_time + 3600:
                        requests.post(f"{self.api_url}/cancel_bid",
                                    headers=headers,
                                    json={"bid_id": bid['bid_id']}, 
                                    verify=False)
                        print(f"🧹 Cleaned up expiring test bid: {bid['bid_id'][:8]}...")
                        
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def monitor_marketplace(self):
        """Monitor marketplace activity"""
        try:
            response = requests.get(f"{self.api_url}/exchange_data?category=TEST&limit=20", 
                                  verify=False)
            if response.status_code == 200:
                data = response.json()
                active_bids = len(data.get('active_bids', []))
                print(f"📊 Marketplace: {active_bids} active TEST bids")
                return active_bids
        except Exception as e:
            print(f"Error monitoring marketplace: {e}")
        return 0

    def run(self, duration_minutes=60):
        """Run demand monitoring for specified duration"""
        print(f"\n🚀 Starting Demand Monitor")
        print(f"API: {self.api_url}")
        print(f"Interval: {self.interval} seconds")
        print(f"Duration: {duration_minutes} minutes")
        print("="*50)
        
        # Create initial test users
        num_users = 3
        for i in range(num_users):
            self.create_test_user()
        
        if not self.active_tokens:
            print("❌ No active tokens available. Exiting.")
            return
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        cycle_count = 0
        
        try:
            while time.time() < end_time:
                cycle_count += 1
                print(f"\n--- Cycle {cycle_count} [{datetime.now().strftime('%H:%M:%S')}] ---")
                
                # Select random token for this cycle
                token = random.choice(self.active_tokens)
                
                # Decide service type (60% physical, 40% software)
                if random.random() < 0.6:
                    demand_data = self.generate_physical_demand(token)
                    service_type = "Physical"
                else:
                    demand_data = self.generate_software_demand(token)
                    service_type = "Software"
                
                # Submit demand
                bid_id = self.submit_demand(token, demand_data)
                
                if bid_id:
                    print(f"  Type: {service_type} | Payment: {demand_data['payment_method']}")
                
                # Monitor marketplace every 5 cycles
                if cycle_count % 5 == 0:
                    active_count = self.monitor_marketplace()
                    
                    # Cleanup if too many bids
                    if active_count > 50:
                        print("🧹 High bid count, cleaning up...")
                        for cleanup_token in self.active_tokens[:2]:
                            self.cleanup_expired_bids(cleanup_token)
                
                # Wait for next cycle
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            print("\n⏹️  Demand monitoring stopped by user")
        
        # Final cleanup
        print(f"\n🧹 Final cleanup...")
        for token in self.active_tokens:
            self.cleanup_expired_bids(token)
        
        total_time = time.time() - start_time
        print(f"\n✅ Demand monitoring completed")
        print(f"Total runtime: {total_time/60:.1f} minutes")
        print(f"Cycles completed: {cycle_count}")
        print(f"Test users created: {len(self.test_users)}")

def main():
    parser = argparse.ArgumentParser(description='Service Exchange Demand Monitor')
    parser.add_argument('--local', action='store_true', help='Use localhost API')
    parser.add_argument('--interval', type=int, default=300, help='Seconds between demands (default: 300)')
    parser.add_argument('--duration', type=int, default=60, help='Run duration in minutes (default: 60)')
    args = parser.parse_args()
    
    api_url = "http://localhost:5003" if args.local else "https://rse-api.com:5003"
    
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    monitor = DemandMonitor(api_url, args.interval)
    monitor.run(args.duration)

if __name__ == "__main__":
    main()
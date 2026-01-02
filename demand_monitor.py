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
import signal
import sys
from datetime import datetime, timedelta

class DemandMonitor:
    def __init__(self, api_url, interval=300):
        self.api_url = api_url
        self.interval = interval  # seconds between demand creation
        self.test_users = []
        self.active_tokens = []
        self.running = True
        self.start_time = time.time()
        self.last_cleanup = time.time()
        self.last_user_check = time.time()
        self.created_demands = 0
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
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

    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        self.running = False

    def log_status(self, message, level="INFO"):
        """Log status with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {level}: {message}")

    def check_api_health(self):
        """Check if API is accessible"""
        try:
            response = requests.get(f"{self.api_url}/ping", timeout=10, verify=False)
            return response.status_code == 200
        except Exception as e:
            self.log_status(f"API health check failed: {e}", "ERROR")
            return False

    def maintain_users(self):
        """Maintain minimum number of active users"""
        if time.time() - self.last_user_check < 3600:  # Check hourly
            return
            
        self.last_user_check = time.time()
        self.log_status(f"User maintenance: {len(self.active_tokens)} active users")
        
        # Recreate users if we have too few
        target_users = 3
        if len(self.active_tokens) < target_users:
            self.log_status("Recreating missing demand users...", "WARN")
            missing_users = target_users - len(self.active_tokens)
            for i in range(missing_users):
                self.create_test_user()
                time.sleep(1)  # Avoid rate limiting

    def periodic_cleanup(self):
        """Perform periodic cleanup tasks"""
        if time.time() - self.last_cleanup < 3600:  # Cleanup every hour
            return
            
        self.last_cleanup = time.time()
        self.log_status("Performing periodic cleanup...")
        
        # Cleanup expired bids
        for token in self.active_tokens[:2]:  # Only use first 2 tokens for cleanup
            self.cleanup_expired_bids(token)
        
        # Log statistics
        runtime_hours = (time.time() - self.start_time) / 3600
        self.log_status(f"Runtime: {runtime_hours:.1f}h, Demands created: {self.created_demands}")
        
        # Monitor marketplace
        try:
            active_count = self.monitor_marketplace()
            self.log_status(f"Marketplace: {active_count} active TEST bids")
        except Exception as e:
            self.log_status(f"Error in periodic cleanup: {e}", "ERROR")

    def create_test_user(self):
        """Create a test user for demand generation"""
        # Keep username under 20 chars (validation limit)
        username = f"d_bot_{uuid.uuid4().hex[:10]}"
        
        try:
            # Register
            response = requests.post(f"{self.api_url}/register", json={
                "username": username,
                "password": "DemandBot123!",
                "user_type": "demand"
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
        format_values = {}
        for key, values in service_template["variations"].items():
            format_values[key] = random.choice(values)
        description = description.format(**format_values)
        
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
        format_values = {}
        for key, values in service_template["variations"].items():
            format_values[key] = random.choice(values)
        description = description.format(**format_values)
        
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
                self.log_status(f"Demand created: {service_desc[:40]}... | ${demand_data['price']} | {bid_id[:8]}...")
                self.created_demands += 1
                return bid_id
            else:
                error_data = response.json() if response.content else {}
                self.log_status(f"Failed to create demand: {response.status_code} - {error_data.get('error', 'Unknown error')}", "ERROR")
                return None
                
        except Exception as e:
            self.log_status(f"Error submitting demand: {e}", "ERROR")
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

    def run_continuous(self):
        """Run demand monitoring continuously until stopped"""
        self.log_status("Starting continuous Demand Monitor")
        self.log_status(f"API: {self.api_url}")
        self.log_status(f"Interval: {self.interval} seconds")
        
        # Initial API health check
        if not self.check_api_health():
            self.log_status("API not accessible, waiting 60 seconds before retry...", "ERROR")
            time.sleep(60)
            if not self.check_api_health():
                self.log_status("API still not accessible, exiting", "ERROR")
                return
        
        # Create initial demand users
        num_users = 3
        for i in range(num_users):
            self.create_test_user()
            time.sleep(1)  # Avoid rate limiting
        
        if not self.active_tokens:
            self.log_status("No active tokens available. Retrying in 5 minutes...", "ERROR")
            time.sleep(300)
            return self.run_continuous()  # Retry
        
        cycle_count = 0
        consecutive_errors = 0
        
        while self.running:
            try:
                cycle_count += 1
                current_time = datetime.now().strftime('%H:%M:%S')
                
                # Periodic status log (every 10 cycles)
                if cycle_count % 10 == 0:
                    runtime_hours = (time.time() - self.start_time) / 3600
                    self.log_status(f"Cycle {cycle_count} | Runtime: {runtime_hours:.1f}h | Demands: {self.created_demands}")
                
                # API health check every 50 cycles
                if cycle_count % 50 == 0:
                    if not self.check_api_health():
                        self.log_status("API health check failed, waiting 60 seconds...", "ERROR")
                        time.sleep(60)
                        continue
                
                # Select random token for this cycle
                if self.active_tokens:
                    token = random.choice(self.active_tokens)
                    
                    # Decide service type (60% physical, 40% software)
                    if random.random() < 0.6:
                        demand_data = self.generate_physical_demand(token)
                        service_type = "Physical"
                    else:
                        demand_data = self.generate_software_demand(token)
                        service_type = "Software"
                    
                    # Submit demand
                    try:
                        bid_id = self.submit_demand(token, demand_data)
                        if bid_id:
                            self.log_status(f"Type: {service_type} | Payment: {demand_data['payment_method']}")
                    except Exception as e:
                        self.log_status(f"Error submitting demand: {e}", "ERROR")
                        # Remove invalid tokens
                        if "401" in str(e) or "403" in str(e):
                            self.active_tokens = [t for t in self.active_tokens if t != token]
                            self.log_status(f"Removed invalid token", "WARN")
                
                # Maintenance tasks
                self.maintain_users()
                self.periodic_cleanup()
                
                # Reset error counter on successful cycle
                consecutive_errors = 0
                
                # Wait for next cycle
                time.sleep(self.interval)
                
            except KeyboardInterrupt:
                self.log_status("Interrupted by user", "INFO")
                break
            except Exception as e:
                consecutive_errors += 1
                self.log_status(f"Cycle error ({consecutive_errors}): {e}", "ERROR")
                
                # If too many consecutive errors, take a longer break
                if consecutive_errors >= 5:
                    self.log_status("Too many consecutive errors, taking 5 minute break...", "ERROR")
                    time.sleep(300)
                    consecutive_errors = 0
                else:
                    time.sleep(30)  # Short pause on error
        
        # Cleanup on shutdown
        self.log_status("Performing final cleanup...")
        for token in self.active_tokens:
            self.cleanup_expired_bids(token)
        
        total_time = time.time() - self.start_time
        self.log_status(f"Demand monitoring completed")
        self.log_status(f"Total runtime: {total_time/3600:.1f} hours")
        self.log_status(f"Cycles completed: {cycle_count}")
        self.log_status(f"Demands created: {self.created_demands}")

    def run(self, duration_minutes=None):
        """Run demand monitoring (continuous if no duration specified)"""
        if duration_minutes is None:
            self.run_continuous()
            return
        
        # Legacy timed run for backwards compatibility
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
    parser = argparse.ArgumentParser(description='Service Exchange Demand Monitor - Continuous Operation')
    parser.add_argument('--local', action='store_true', help='Use localhost API')
    parser.add_argument('--interval', type=int, default=300, help='Seconds between demands (default: 300)')
    parser.add_argument('--duration', type=int, default=None, help='Run duration in minutes (default: continuous)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()
    
    api_url = "http://localhost:5003" if args.local else "https://rse-api.com:5003"
    
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    monitor = DemandMonitor(api_url, args.interval)
    
    if args.duration:
        print(f"Running for {args.duration} minutes...")
        monitor.run(args.duration)
    else:
        print("Running continuously (Ctrl+C or SIGTERM to stop)...")
        monitor.run()  # Continuous mode

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Robotaxi Fleet Manager for The Services Exchange
-------------------------------------------------
Production-ready script demonstrating how autonomous vehicle fleets
can integrate with the Service Exchange API to grab ridesharing jobs.

Usage:
    # Test mode - creates and grabs test jobs
    python robotaxi_fleet.py --test
    
    # Production mode - grabs real jobs from the exchange
    python robotaxi_fleet.py --production
    
    # Specify number of vehicles (default: 3)
    python robotaxi_fleet.py --test --vehicles 5
"""

import argparse
import hashlib
import json
import requests
import time
import sys
from typing import Dict, List, Optional
import urllib3

# Disable SSL warnings for development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
API_URL = "https://rse-api.com:5003"
SEATS_FILE = "seats.dat"

# Test seats from seats.dat (first 3)
TEST_SEATS = [
    {
        "id": "RSX0000000",
        "phrase": "elephant lab aware runway prepare head hurdle round pudding excuse edit sibling",
        "owner": "@satori_jojo"
    },
    {
        "id": "RSX0000001", 
        "phrase": "symptom share tunnel joy write clown movie pair usual demand treat sword",
        "owner": "@satori_jojo"
    },
    {
        "id": "RSX0000002",
        "phrase": "strategy cherry range captain section woman raw trust master spoon add resource",
        "owner": "@satori_jojo"
    }
]


def print_logo():
    """Display ASCII art logo for the robotaxi fleet manager."""
    logo = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║    ██████╗  ██████╗ ██████╗  ██████╗ ████████╗ █████╗ ██╗  ██╗██╗  ║
    ║    ██╔══██╗██╔═══██╗██╔══██╗██╔═══██╗╚══██╔══╝██╔══██╗╚██╗██╔╝██║  ║
    ║    ██████╔╝██║   ██║██████╔╝██║   ██║   ██║   ███████║ ╚███╔╝ ██║  ║
    ║    ██╔══██╗██║   ██║██╔══██╗██║   ██║   ██║   ██╔══██║ ██╔██╗ ██║  ║
    ║    ██║  ██║╚██████╔╝██████╔╝╚██████╔╝   ██║   ██║  ██║██╔╝ ██╗██║  ║
    ║    ╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ║
    ║                                                               ║
    ║           🚕  Fleet Manager for The Services Exchange  🚕     ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(logo)


def md5(text: str) -> str:
    """Generate MD5 hash for seat authentication."""
    return hashlib.md5(text.encode()).hexdigest()


class RobotaxiVehicle:
    """Represents a single autonomous vehicle in the fleet."""
    
    def __init__(self, vehicle_id: int, seat_data: Dict, api_url: str):
        self.vehicle_id = vehicle_id
        self.seat_id = seat_data['id']
        self.seat_owner = seat_data['owner']
        self.seat_secret = md5(seat_data['phrase'])
        self.api_url = api_url
        self.access_token = None
        # Short username to stay within 20 char limit
        self.username = f"robo_{vehicle_id}_{int(time.time()) % 10000}"
        self.current_job = None
        
    def register(self) -> bool:
        """Register vehicle as a service provider."""
        try:
            response = requests.post(
                f"{self.api_url}/register",
                json={
                    "username": self.username,
                    "password": f"secure_pass_{self.vehicle_id}_{int(time.time())}",
                    "user_type": "supply"
                },
                verify=False,
                timeout=10
            )
            
            if response.status_code == 201:
                print(f"  ✓ Vehicle {self.vehicle_id} registered as {self.username}")
                return True
            else:
                print(f"  ✗ Vehicle {self.vehicle_id} registration failed: {response.json().get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"  ✗ Vehicle {self.vehicle_id} registration error: {e}")
            return False
    
    def login(self, password: str) -> bool:
        """Authenticate vehicle with the exchange."""
        try:
            response = requests.post(
                f"{self.api_url}/login",
                json={
                    "username": self.username,
                    "password": password
                },
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                self.access_token = response.json()['access_token']
                print(f"  ✓ Vehicle {self.vehicle_id} authenticated")
                return True
            else:
                print(f"  ✗ Vehicle {self.vehicle_id} login failed")
                return False
                
        except Exception as e:
            print(f"  ✗ Vehicle {self.vehicle_id} login error: {e}")
            return False
    
    def grab_job(self, location: str = "Denver Airport") -> Optional[Dict]:
        """Attempt to grab a ridesharing job from the exchange."""
        if not self.access_token:
            print(f"  ✗ Vehicle {self.vehicle_id} not authenticated")
            return None
        
        try:
            # Prepare seat credentials
            seat_data = {
                "id": self.seat_id,
                "owner": self.seat_owner,
                "secret": self.seat_secret
            }
            
            response = requests.post(
                f"{self.api_url}/grab_job",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "capabilities": "Autonomous vehicle, rideshare, taxi service, transportation, airport pickup, city transport",
                    "location_type": "physical",
                    "address": location,
                    "max_distance": 15,
                    "seat": seat_data  # Include seat credentials
                },
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                job = response.json()
                self.current_job = job
                print(f"  ✓ Vehicle {self.vehicle_id} grabbed job!")
                print(f"    Route: {job.get('start_address', 'N/A')} → {job.get('end_address', 'N/A')}")
                print(f"    Price: {job.get('currency', 'USD')} {job['price']}")
                print(f"    Job ID: {job['job_id']}")
                return job
            elif response.status_code == 204:
                print(f"  - Vehicle {self.vehicle_id}: No jobs available in area")
                return None
            else:
                error_msg = response.json().get('error', 'Unknown error')
                print(f"  ✗ Vehicle {self.vehicle_id} grab failed: {error_msg}")
                return None
                
        except Exception as e:
            print(f"  ✗ Vehicle {self.vehicle_id} grab error: {e}")
            return None


class RobotaxiFleet:
    """Manages a fleet of autonomous vehicles on the Service Exchange."""
    
    def __init__(self, num_vehicles: int, api_url: str, test_mode: bool = True):
        self.num_vehicles = min(num_vehicles, len(TEST_SEATS))
        self.api_url = api_url
        self.test_mode = test_mode
        self.vehicles: List[RobotaxiVehicle] = []
        self.test_rider_token = None
        self.test_rider_username = None
        
    def initialize_fleet(self) -> bool:
        """Initialize all vehicles in the fleet."""
        print(f"\n🚗 Initializing fleet of {self.num_vehicles} autonomous vehicles...")
        print(f"   Mode: {'TEST' if self.test_mode else 'PRODUCTION'}")
        print(f"   API: {self.api_url}\n")
        
        for i in range(self.num_vehicles):
            vehicle = RobotaxiVehicle(i + 1, TEST_SEATS[i], self.api_url)
            
            # Register vehicle
            if not vehicle.register():
                print(f"Failed to register vehicle {i + 1}")
                continue
            
            # Login vehicle
            password = f"secure_pass_{i + 1}_{int(time.time())}"
            if not vehicle.login(password):
                print(f"Failed to login vehicle {i + 1}")
                continue
            
            self.vehicles.append(vehicle)
        
        print(f"\n✓ Fleet initialized: {len(self.vehicles)}/{self.num_vehicles} vehicles ready\n")
        return len(self.vehicles) > 0
    
    def create_test_jobs(self) -> bool:
        """Create test ridesharing jobs for vehicles to grab."""
        print("📝 Creating test ridesharing jobs...\n")
        
        # Register test rider
        test_rider = f"rider_{int(time.time()) % 100000}"
        password = f"test_pass_{int(time.time())}"
        
        try:
            # Register
            response = requests.post(
                f"{self.api_url}/register",
                json={
                    "username": test_rider,
                    "password": password,
                    "user_type": "demand"
                },
                verify=False,
                timeout=10
            )
            
            if response.status_code != 201:
                print(f"  ✗ Failed to register test rider")
                return False
            
            # Login
            response = requests.post(
                f"{self.api_url}/login",
                json={
                    "username": test_rider,
                    "password": password
                },
                verify=False,
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"  ✗ Failed to login test rider")
                return False
            
            self.test_rider_token = response.json()['access_token']
            self.test_rider_username = test_rider
            
            # Create test ride requests
            test_rides = [
                {
                    "service": "TEST: Airport pickup for robotaxi demo",
                    "price": 45,
                    "start_address": "Denver Airport",
                    "end_address": "Downtown Denver, CO"
                },
                {
                    "service": "TEST: City ride for robotaxi demo",
                    "price": 35,
                    "start_address": "Downtown Denver, CO",
                    "end_address": "Denver Tech Center"
                },
                {
                    "service": "TEST: Short trip for robotaxi demo",
                    "price": 25,
                    "start_address": "Denver Convention Center",
                    "end_address": "Union Station Denver"
                }
            ]
            
            jobs_created = 0
            for ride in test_rides:
                response = requests.post(
                    f"{self.api_url}/submit_bid",
                    headers={"Authorization": f"Bearer {self.test_rider_token}"},
                    json={
                        "service": ride["service"],
                        "price": ride["price"],
                        "currency": "USD",
                        "payment_method": "credit_card",
                        "end_time": int(time.time()) + 3600,
                        "location_type": "physical",
                        "start_address": ride["start_address"],
                        "end_address": ride["end_address"]
                    },
                    verify=False,
                    timeout=10
                )
                
                if response.status_code == 200:
                    bid_id = response.json()['bid_id']
                    print(f"  ✓ Created: {ride['start_address']} → {ride['end_address']} (${ride['price']})")
                    jobs_created += 1
                else:
                    print(f"  ✗ Failed to create ride: {ride['start_address']} → {ride['end_address']}")
            
            print(f"\n✓ Created {jobs_created} test jobs\n")
            return jobs_created > 0
            
        except Exception as e:
            print(f"  ✗ Error creating test jobs: {e}")
            return False
    
    def dispatch_fleet(self, location: str = "Denver Airport") -> Dict:
        """Dispatch all vehicles to grab available jobs."""
        print(f"🚕 Dispatching fleet to grab jobs near {location}...\n")
        
        results = {
            "jobs_grabbed": 0,
            "no_jobs_available": 0,
            "errors": 0
        }
        
        for vehicle in self.vehicles:
            job = vehicle.grab_job(location)
            if job:
                results["jobs_grabbed"] += 1
            elif job is None:
                # Could be no jobs or error - check if it was a 204
                results["no_jobs_available"] += 1
            else:
                results["errors"] += 1
            
            # Small delay between requests to be polite to the API
            time.sleep(0.5)
        
        return results
    
    def print_summary(self, results: Dict):
        """Print summary of fleet operations."""
        print("\n" + "="*60)
        print("📊 FLEET DISPATCH SUMMARY")
        print("="*60)
        print(f"  Total Vehicles: {len(self.vehicles)}")
        print(f"  Jobs Grabbed:   {results['jobs_grabbed']} ✓")
        print(f"  No Jobs Found:  {results['no_jobs_available']}")
        print(f"  Errors:         {results['errors']}")
        print("="*60 + "\n")


def main():
    """Main entry point for the robotaxi fleet manager."""
    parser = argparse.ArgumentParser(
        description="Robotaxi Fleet Manager for The Services Exchange",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run in test mode (creates test jobs and grabs them)'
    )
    parser.add_argument(
        '--production',
        action='store_true',
        help='Run in production mode (grabs real jobs from the exchange)'
    )
    parser.add_argument(
        '--vehicles',
        type=int,
        default=3,
        help='Number of vehicles in the fleet (default: 3, max: 3 for test seats)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.test and not args.production:
        print("Error: Must specify --test or --production mode")
        parser.print_help()
        sys.exit(1)
    
    if args.test and args.production:
        print("Error: Cannot specify both --test and --production")
        sys.exit(1)
    
    # Print logo
    print_logo()
    
    # Initialize fleet
    fleet = RobotaxiFleet(
        num_vehicles=args.vehicles,
        api_url=API_URL,
        test_mode=args.test
    )
    
    if not fleet.initialize_fleet():
        print("❌ Failed to initialize fleet")
        sys.exit(1)
    
    # Create test jobs if in test mode
    if args.test:
        if not fleet.create_test_jobs():
            print("⚠️  Failed to create test jobs, but continuing...")
        
        # Wait a moment for jobs to be available
        print("⏳ Waiting for jobs to be available...")
        time.sleep(2)
    
    # Dispatch fleet to grab jobs
    results = fleet.dispatch_fleet()
    
    # Print summary
    fleet.print_summary(results)
    
    # Exit code based on results
    if results["jobs_grabbed"] > 0:
        print("✅ SUCCESS: Fleet successfully grabbed jobs from the exchange!")
        sys.exit(0)
    else:
        if args.test:
            print("⚠️  WARNING: No jobs were grabbed in test mode")
            sys.exit(1)
        else:
            print("ℹ️  INFO: No jobs available on the exchange at this time")
            sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Supply Monitoring Script for Service Exchange
Creates test service providers to fulfill marketplace demands
"""

import requests
import json
import time
import random
import uuid
import argparse
from datetime import datetime, timedelta

class SupplyMonitor:
    def __init__(self, api_url, interval=180):
        self.api_url = api_url
        self.interval = interval  # seconds between supply attempts
        self.test_providers = []
        self.active_tokens = []
        self.completed_jobs = 0
        
        # Provider capability profiles that match demand templates
        self.physical_providers = [
            {
                "name": "cleaning_specialist",
                "capabilities": "House cleaning, deep cleaning, residential cleaning, bathroom cleaning, kitchen cleaning, move-out cleaning",
                "location_type": "physical",
                "addresses": [
                    "100 Cleaner Ave, Denver, CO 80220",
                    "200 Sparkle St, Denver, CO 80221", 
                    "300 Polish Rd, Denver, CO 80222"
                ],
                "max_distance": 25
            },
            {
                "name": "handyman_expert", 
                "capabilities": "Home repairs, plumbing, electrical work, drywall repair, painting, flooring installation, general maintenance",
                "location_type": "physical",
                "addresses": [
                    "400 Repair Blvd, Denver, CO 80223",
                    "500 Fix St, Denver, CO 80224",
                    "600 Mend Ave, Denver, CO 80225"
                ],
                "max_distance": 20
            },
            {
                "name": "landscaping_pro",
                "capabilities": "Landscaping, lawn mowing, tree trimming, garden design, snow removal, outdoor maintenance",
                "location_type": "physical", 
                "addresses": [
                    "700 Garden Way, Denver, CO 80226",
                    "800 Lawn Dr, Denver, CO 80227",
                    "900 Yard St, Denver, CO 80228"
                ],
                "max_distance": 30
            }
        ]
        
        self.software_providers = [
            {
                "name": "fullstack_developer",
                "capabilities": "React development, Node.js, TypeScript, web applications, e-commerce platforms, full-stack development",
                "location_type": "remote"
            },
            {
                "name": "automation_specialist", 
                "capabilities": "Python scripting, automation, data processing, file management, API integration, report generation",
                "location_type": "remote"
            },
            {
                "name": "mobile_developer",
                "capabilities": "Mobile app development, React Native, Flutter, iOS development, Android development, cross-platform apps",
                "location_type": "remote"
            },
            {
                "name": "backend_expert",
                "capabilities": "Backend development, API development, database design, Python, Django, Node.js, microservices",
                "location_type": "remote"
            }
        ]

    def create_test_provider(self, provider_profile):
        """Create a test provider user"""
        # Keep username under 20 chars (validation limit)
        provider_short = provider_profile['name'][:8]  # truncate if needed
        username = f"s_{provider_short}_{uuid.uuid4().hex[:8]}"
        
        try:
            # Register
            response = requests.post(f"{self.api_url}/register", json={
                "username": username,
                "password": "SupplyBot123!"
            }, verify=False)
            
            if response.status_code != 201:
                print(f"Failed to register {username}: {response.status_code}")
                return None
            
            # Login
            response = requests.post(f"{self.api_url}/login", json={
                "username": username,
                "password": "SupplyBot123!"
            }, verify=False)
            
            if response.status_code != 200:
                print(f"Failed to login {username}: {response.status_code}")
                return None
            
            token = response.json()['access_token']
            self.test_providers.append((username, provider_profile))
            self.active_tokens.append((token, username, provider_profile))
            
            print(f"✓ Created supply bot: {username} ({provider_profile['name']})")
            return token
            
        except Exception as e:
            print(f"Error creating test provider: {e}")
            return None

    def attempt_job_grab(self, token, username, provider_profile):
        """Attempt to grab a job matching provider capabilities"""
        headers = {"Authorization": f"Bearer {token}"}
        
        # Build grab_job request based on provider type
        grab_data = {
            "capabilities": provider_profile["capabilities"],
            "location_type": provider_profile["location_type"]
        }
        
        # Add location data for physical providers
        if provider_profile["location_type"] in ["physical", "hybrid"]:
            grab_data["address"] = random.choice(provider_profile["addresses"])
            grab_data["max_distance"] = provider_profile["max_distance"]
        
        try:
            response = requests.post(f"{self.api_url}/grab_job", 
                                   headers=headers, 
                                   json=grab_data, 
                                   verify=False)
            
            if response.status_code == 200:
                job = response.json()
                service_desc = (json.dumps(job['service']) 
                              if isinstance(job['service'], dict) 
                              else job['service'])
                
                # Only report TEST jobs
                if 'TEST:' in service_desc:
                    print(f"✓ Job grabbed by {username}: {service_desc[:40]}... | ${job['price']} | {job['job_id'][:8]}...")
                    
                    # Simulate job completion for TEST jobs
                    self.complete_test_job(token, job)
                    return True
                else:
                    # Reject non-test jobs to keep them available for real users
                    self.reject_job(token, job['job_id'], "Bot only handles TEST jobs")
                    return False
                    
            elif response.status_code == 204:
                # No jobs available - this is normal
                return False
            else:
                error_data = response.json() if response.content else {}
                if response.status_code != 403:  # Don't spam seat verification errors
                    print(f"✗ Job grab failed for {username}: {response.status_code} - {error_data.get('error', 'Unknown')}")
                return False
                
        except Exception as e:
            print(f"✗ Error grabbing job for {username}: {e}")
            return False

    def reject_job(self, token, job_id, reason):
        """Reject a job to return it to the marketplace"""
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = requests.post(f"{self.api_url}/reject_job",
                                   headers=headers,
                                   json={
                                       "job_id": job_id,
                                       "reason": reason
                                   }, verify=False)
            
            if response.status_code == 200:
                print(f"  → Job {job_id[:8]}... rejected (non-test job)")
            
        except Exception as e:
            print(f"Error rejecting job: {e}")

    def complete_test_job(self, token, job):
        """Simulate completion of a TEST job"""
        headers = {"Authorization": f"Bearer {token}"}
        job_id = job['job_id']
        
        try:
            # Wait a bit to simulate work
            time.sleep(random.uniform(5, 15))
            
            # Sign the job with a random rating
            rating = random.randint(4, 5)  # High ratings for test jobs
            response = requests.post(f"{self.api_url}/sign_job",
                                   headers=headers,
                                   json={
                                       "job_id": job_id,
                                       "star_rating": rating
                                   }, verify=False)
            
            if response.status_code == 200:
                self.completed_jobs += 1
                print(f"  → Job {job_id[:8]}... completed with {rating} stars")
            else:
                print(f"  → Failed to complete job {job_id[:8]}: {response.status_code}")
                
        except Exception as e:
            print(f"Error completing job: {e}")

    def monitor_job_market(self):
        """Monitor available jobs in the market"""
        try:
            response = requests.get(f"{self.api_url}/exchange_data?category=TEST&include_completed=true&limit=30", 
                                  verify=False)
            if response.status_code == 200:
                data = response.json()
                active_bids = len(data.get('active_bids', []))
                completed_jobs = len(data.get('completed_jobs', []))
                print(f"📊 Job Market: {active_bids} available TEST jobs, {completed_jobs} completed today")
                return active_bids, completed_jobs
        except Exception as e:
            print(f"Error monitoring job market: {e}")
        return 0, 0

    def cleanup_test_data(self):
        """Clean up any remaining test jobs"""
        print("🧹 Cleaning up incomplete test jobs...")
        
        for token, username, profile in self.active_tokens:
            headers = {"Authorization": f"Bearer {token}"}
            
            try:
                # Get active jobs
                response = requests.get(f"{self.api_url}/my_jobs", headers=headers, verify=False)
                if response.status_code == 200:
                    jobs_data = response.json()
                    active_jobs = jobs_data.get('active_jobs', [])
                    
                    for job in active_jobs:
                        service_str = (json.dumps(job.get('service', '')) 
                                     if isinstance(job.get('service'), dict) 
                                     else str(job.get('service', '')))
                        
                        if 'TEST:' in service_str:
                            # Complete any remaining test jobs
                            response = requests.post(f"{self.api_url}/sign_job",
                                                   headers=headers,
                                                   json={
                                                       "job_id": job['job_id'],
                                                       "star_rating": 5
                                                   }, verify=False)
                            if response.status_code == 200:
                                print(f"  ✓ Completed job {job['job_id'][:8]}... during cleanup")
                                
            except Exception as e:
                print(f"Error during cleanup for {username}: {e}")

    def run(self, duration_minutes=60):
        """Run supply monitoring for specified duration"""
        print(f"\n🔧 Starting Supply Monitor")
        print(f"API: {self.api_url}")
        print(f"Interval: {self.interval} seconds")
        print(f"Duration: {duration_minutes} minutes")
        print("="*50)
        
        # Create provider bots
        all_providers = self.physical_providers + self.software_providers
        for provider_profile in all_providers:
            self.create_test_provider(provider_profile)
        
        if not self.active_tokens:
            print("❌ No active provider tokens available. Exiting.")
            return
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        cycle_count = 0
        jobs_grabbed = 0
        
        try:
            while time.time() < end_time:
                cycle_count += 1
                print(f"\n--- Supply Cycle {cycle_count} [{datetime.now().strftime('%H:%M:%S')}] ---")
                
                # Try each provider to grab jobs
                cycle_grabs = 0
                for token, username, profile in self.active_tokens:
                    if self.attempt_job_grab(token, username, profile):
                        jobs_grabbed += 1
                        cycle_grabs += 1
                        
                        # Small delay between grabs to avoid overwhelming
                        time.sleep(2)
                
                if cycle_grabs == 0:
                    print(f"  No TEST jobs available for providers")
                
                # Monitor market every 3 cycles
                if cycle_count % 3 == 0:
                    self.monitor_job_market()
                
                # Wait for next cycle
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            print("\n⏹️  Supply monitoring stopped by user")
        
        # Final cleanup
        self.cleanup_test_data()
        
        total_time = time.time() - start_time
        print(f"\n✅ Supply monitoring completed")
        print(f"Total runtime: {total_time/60:.1f} minutes")
        print(f"Cycles completed: {cycle_count}")
        print(f"Jobs grabbed: {jobs_grabbed}")
        print(f"Jobs completed: {self.completed_jobs}")
        print(f"Provider bots created: {len(self.test_providers)}")

def main():
    parser = argparse.ArgumentParser(description='Service Exchange Supply Monitor')
    parser.add_argument('--local', action='store_true', help='Use localhost API')
    parser.add_argument('--interval', type=int, default=180, help='Seconds between supply attempts (default: 180)')
    parser.add_argument('--duration', type=int, default=60, help='Run duration in minutes (default: 60)')
    args = parser.parse_args()
    
    api_url = "http://localhost:5003" if args.local else "https://rse-api.com:5003"
    
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    monitor = SupplyMonitor(api_url, args.interval)
    monitor.run(args.duration)

if __name__ == "__main__":
    main()
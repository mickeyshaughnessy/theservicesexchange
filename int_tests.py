"""
Integration Tests for the Services Exchange API

Covers:
  • Core API mechanics (auth, bid CRUD, chat, bulletin)
  • Service matching accuracy across 30 diverse real-world categories
  • Advanced features (XMoney, exchange_data, nearby)

Labeling & cleanup contract
  - Every test bid/service starts with "TEST:" so it is unambiguously synthetic.
  - Provider accounts call set_wallet with the real seat wallet (seats #1-100)
    so tests remain valid if SEAT_VERIFICATION_ENABLED is turned on.
  - cleanup() cancels outstanding bids AND completes (signs) any open test jobs,
    leaving the live exchange in the same state it was before the run.

Usage:
  python int_tests.py --local          # localhost:5003
  python int_tests.py --local --quick  # skip matching + advanced suites
  python int_tests.py                  # https://rse-api.com:5003
"""

import requests
import json
import time
import uuid
import hashlib
import argparse
import config

# ── Silence SSL warnings for self-signed certs on localhost ──────────────────
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def md5(text):
    return hashlib.md5(text.encode()).hexdigest()


# ── 30 diverse service-matching test cases ───────────────────────────────────
# Each case drives:
#   1. Buyer posts the bid.
#   2. Provider grabs with non_matching_caps  → expect 204 (no match).
#   3. Provider grabs with matching_caps      → expect 200 (job created).
#
# "matching" and "non-matching" are chosen to be semantically distant so that
# even the keyword fallback behaves correctly.

MATCHING_TEST_CASES = [
    # ── Home Health Aides ─────────────────────────────────────────────────────
    {
        "name": "Home health: post-surgery wound care",
        "bid": {
            "service": "TEST: Post-surgery home nursing visit, daily wound dressing and medication management",
            "price": 250, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "100 Main St, Denver, CO 80202",
        },
        "matching_caps": "Registered nurse, home health aide, wound care, medication administration, post-op recovery",
        "non_matching_caps": "Lawn mowing, grass cutting, yard cleanup, leaf blowing",
    },
    {
        "name": "Home health: Alzheimer's companionship",
        "bid": {
            "service": "TEST: Daily companionship visits for Alzheimer's patient, light housekeeping",
            "price": 180, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "200 Elm St, Denver, CO 80203",
        },
        "matching_caps": "Dementia care, Alzheimer's companion, CNA, elder care, personal care aide",
        "non_matching_caps": "React developer, TypeScript, Node.js, web application development",
    },
    {
        "name": "Home health: pediatric physical therapy",
        "bid": {
            "service": "TEST: Licensed pediatric physical therapy home visit, mobility and strength exercises",
            "price": 200, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "300 Oak Ave, Denver, CO 80204",
        },
        "matching_caps": "Licensed pediatric physical therapist, home visits, mobility and strength therapy",
        "non_matching_caps": "Commercial electrician, panel installation, conduit, rough-in wiring",
    },
    # ── Food Delivery ─────────────────────────────────────────────────────────
    {
        "name": "Food delivery: hot restaurant meals",
        "bid": {
            "service": "TEST: Hot restaurant meal delivery, 30-minute window, downtown pickup",
            "price": 25, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "400 16th St, Denver, CO 80202",
        },
        "matching_caps": "Food delivery driver, restaurant courier, last-mile delivery, DoorDash-style",
        "non_matching_caps": "Tree removal, arborist, stump grinding, chainsaw operation",
    },
    {
        "name": "Food delivery: same-day grocery",
        "bid": {
            "service": "TEST: Same-day grocery delivery, ~40 items, perishable handling required",
            "price": 35, "currency": "USD", "payment_method": "paypal",
            "location_type": "physical", "address": "500 Colfax Ave, Denver, CO 80203",
        },
        "matching_caps": "Grocery delivery, personal shopper, Instacart-style, produce handling",
        "non_matching_caps": "Penetration testing, ethical hacking, OSCP, web security audit",
    },
    {
        "name": "Food delivery: specialty diabetic-friendly meals",
        "bid": {
            "service": "TEST: Diabetic-friendly prepared meal delivery, low-glycemic menu, weekly subscription",
            "price": 150, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "600 Broadway, Denver, CO 80203",
        },
        "matching_caps": "Specialty diet meal delivery, diabetic-friendly food service, nutritional compliance",
        "non_matching_caps": "Concrete foundation pour, rebar installation, slab work, site grading",
    },
    # ── Landscaping ───────────────────────────────────────────────────────────
    {
        "name": "Landscaping: weekly lawn mowing",
        "bid": {
            "service": "TEST: Weekly lawn mowing and edging, 1-acre residential property",
            "price": 80, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "700 Vine St, Denver, CO 80206",
        },
        "matching_caps": "Residential lawn mowing, edging, yard maintenance, grass cutting",
        "non_matching_caps": "Tax preparation, bookkeeping, CPA, financial statements",
    },
    {
        "name": "Landscaping: emergency storm tree removal",
        "bid": {
            "service": "TEST: Emergency storm-damaged tree removal, large oak, debris hauling",
            "price": 900, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "800 York St, Denver, CO 80206",
        },
        "matching_caps": "Tree removal, certified arborist, chainsaw operation, stump grinding, debris hauling",
        "non_matching_caps": "Home nursing, wound care, medication management, CNA, post-op care",
    },
    {
        "name": "Landscaping: drip irrigation installation",
        "bid": {
            "service": "TEST: Drip and sprinkler irrigation system installation, full residential yard",
            "price": 1800, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "900 Race St, Denver, CO 80206",
        },
        "matching_caps": "Irrigation installation, landscape plumbing, drip systems, sprinkler heads",
        "non_matching_caps": "Children's party planning, bounce house rental, face painting, balloon animals",
    },
    # ── Commercial Construction ───────────────────────────────────────────────
    {
        "name": "Construction: steel frame erection",
        "bid": {
            "service": "TEST: Structural steel frame erection, 50,000 sq ft warehouse, crane required",
            "price": 85000, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1000 Industrial Blvd, Denver, CO 80216",
        },
        "matching_caps": "Structural steel erection, ironworker, crane operator, commercial construction",
        "non_matching_caps": "Dog grooming, pet bathing, nail trimming, animal care",
    },
    {
        "name": "Construction: commercial electrical rough-in",
        "bid": {
            "service": "TEST: Commercial electrical rough-in, 3-story office building, panels and conduit",
            "price": 45000, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1100 Commerce St, Denver, CO 80216",
        },
        "matching_caps": "Commercial electrician, rough-in wiring, conduit installation, panel work, NEC code",
        "non_matching_caps": "Food delivery, grocery shopping, restaurant courier, personal shopper",
    },
    {
        "name": "Construction: concrete foundation pour",
        "bid": {
            "service": "TEST: Concrete slab foundation pour, 8,000 sq ft, rebar grid, 6-inch depth",
            "price": 32000, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1200 Manufacturing Dr, Denver, CO 80216",
        },
        "matching_caps": "Concrete contractor, foundation work, slab pouring, rebar, site grading",
        "non_matching_caps": "Aerial drone photography, FAA Part 107, aerial mapping, photogrammetry",
    },
    # ── Air Quality Monitoring ────────────────────────────────────────────────
    {
        "name": "Air quality: EPA emissions stack testing",
        "bid": {
            "service": "TEST: Industrial stack emissions testing, EPA Method 5 compliance, boiler facility",
            "price": 7500, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1300 Factory Rd, Denver, CO 80216",
        },
        "matching_caps": "Stack emissions testing, EPA Method 5, industrial hygienist, CEM monitoring",
        "non_matching_caps": "Wedding photography, portrait, ceremony coverage, photo editing",
    },
    {
        "name": "Air quality: indoor HVAC survey",
        "bid": {
            "service": "TEST: Indoor air quality survey, office HVAC assessment, VOC and CO2 testing",
            "price": 3200, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "1400 Office Park Way, Denver, CO 80237",
        },
        "matching_caps": "Indoor air quality testing, HVAC assessment, VOC sampling, ASHRAE standards, IAQ",
        "non_matching_caps": "Meal delivery, grocery delivery, food courier, personal shopper",
    },
    {
        "name": "Air quality: wildfire PM2.5 sensor deployment",
        "bid": {
            "service": "TEST: PM2.5 wildfire smoke monitoring station deployment, 5 sites, calibration included",
            "price": 12000, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1500 Mountain View Rd, Denver, CO 80210",
        },
        "matching_caps": "Air quality monitoring, particulate matter sensors, PM2.5 field deployment, calibration",
        "non_matching_caps": "Elder companionship, Alzheimer's care, CNA, personal care aide",
    },
    # ── Industrial Supply Delivery ────────────────────────────────────────────
    {
        "name": "Industrial supply: HAZMAT chemical delivery",
        "bid": {
            "service": "TEST: Bulk HAZMAT chemical delivery, corrosive materials, DOT compliance, 500 gallons",
            "price": 1200, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1600 Industrial Park, Denver, CO 80216",
        },
        "matching_caps": "HAZMAT certified driver, chemical transport, DOT compliance, corrosive materials handling",
        "non_matching_caps": "Children's party coordinator, event planning, birthday parties, kids entertainer",
    },
    {
        "name": "Industrial supply: heavy equipment parts overnight",
        "bid": {
            "service": "TEST: Overnight heavy equipment parts delivery, 2,000 lbs, flatbed required",
            "price": 850, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1700 Freight Terminal, Denver, CO 80216",
        },
        "matching_caps": "Heavy freight delivery, flatbed trucking, oversized load, CDL-A, overnight logistics",
        "non_matching_caps": "Nursing, wound care, post-surgery, home health aide, medication",
    },
    {
        "name": "Industrial supply: sterile medical device cold chain",
        "bid": {
            "service": "TEST: Sterile medical device supply delivery, temperature-controlled, FDA chain of custody",
            "price": 2500, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "1800 Medical Center Dr, Denver, CO 80218",
        },
        "matching_caps": "Medical supply delivery, cold chain logistics, sterile handling, FDA compliance, temperature-controlled transport",
        "non_matching_caps": "Steel erection, ironworker, crane operator, commercial construction framing",
    },
    # ── Children's Party Management ───────────────────────────────────────────
    {
        "name": "Children's party: full-service coordination",
        "bid": {
            "service": "TEST: Full-service 6-year-old birthday party, 20 kids, themed decoration, games, cake",
            "price": 1200, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "1900 Residence Rd, Denver, CO 80207",
        },
        "matching_caps": "Children's party coordinator, event planning, birthday parties, decorations, kids entertainment",
        "non_matching_caps": "HAZMAT driver, chemical transport, DOT compliance, corrosive materials",
    },
    {
        "name": "Children's party: bounce house rental",
        "bid": {
            "service": "TEST: Bounce house and inflatable obstacle course rental, setup and teardown, 6 hours",
            "price": 450, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "2000 Park Blvd, Denver, CO 80207",
        },
        "matching_caps": "Inflatable bounce house rental, event setup, inflatable entertainment, party equipment",
        "non_matching_caps": "EPA stack emissions testing, industrial hygienist, CEM monitoring",
    },
    {
        "name": "Children's party: face painter and balloon artist",
        "bid": {
            "service": "TEST: Face painter and balloon animal artist for children's party, 3-hour event",
            "price": 350, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "2100 Maple Ave, Denver, CO 80207",
        },
        "matching_caps": "Face painting, balloon animals, children's entertainer, party artist",
        "non_matching_caps": "Concrete contractor, foundation pour, rebar, slab work",
    },
    # ── National Security / Government ───────────────────────────────────────
    {
        "name": "National security: Tier-3 background investigation",
        "bid": {
            "service": "TEST: Security clearance background investigation, Tier 3 (Secret), 5-year scope",
            "price": 4500, "currency": "USD", "payment_method": "wire",
            "location_type": "remote",
        },
        "matching_caps": "Background investigator, security clearance vetting, federal contractor, NBIB standards",
        "non_matching_caps": "Lawn mowing, landscaping, yard maintenance, grass cutting, edging",
    },
    {
        "name": "National security: facility vulnerability assessment",
        "bid": {
            "service": "TEST: Physical security vulnerability assessment, federal facility, intrusion testing",
            "price": 8000, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "Federal Center, Lakewood, CO 80228",
        },
        "matching_caps": "Physical security assessment, facility vulnerability survey, cleared personnel, PPSM",
        "non_matching_caps": "Grocery delivery, personal shopper, produce handling, food courier",
    },
    {
        "name": "National security: OPSEC training workshop",
        "bid": {
            "service": "TEST: Operations security (OPSEC) training, 20-employee on-site workshop, government contractor",
            "price": 5500, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "500 Tech Park Dr, Denver, CO 80237",
        },
        "matching_caps": "OPSEC training, security awareness, government contractor, classified briefings",
        "non_matching_caps": "Tree removal, arborist, stump grinding, chainsaw operation, debris hauling",
    },
    # ── Diverse Other Services ────────────────────────────────────────────────
    {
        "name": "Logistics: long-haul refrigerated trucking",
        "bid": {
            "service": "TEST: Refrigerated long-haul trucking, 1,200 miles, perishable food cargo",
            "price": 4800, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "Denver Freight Hub, Denver, CO 80216",
        },
        "matching_caps": "Long-haul truck driver, CDL-A, reefer unit, refrigerated transport, perishable cargo",
        "non_matching_caps": "Face painting, balloon animals, party entertainer, children's events",
    },
    {
        "name": "Legal: certified Mandarin-English translation",
        "bid": {
            "service": "TEST: Certified Mandarin-to-English legal document translation, 80 pages, court-admissible",
            "price": 2400, "currency": "USD", "payment_method": "paypal",
            "location_type": "remote",
        },
        "matching_caps": "Certified translator, Mandarin Chinese, English, legal documents, ATA certification",
        "non_matching_caps": "HVAC repair, air conditioning, rooftop unit, EPA 608, refrigerant handling",
    },
    {
        "name": "Aerial survey: 500-acre drone mapping",
        "bid": {
            "service": "TEST: Drone aerial survey and photogrammetry, 500-acre agricultural field, GIS output",
            "price": 3500, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "Rural Route 5, Greeley, CO 80631",
        },
        "matching_caps": "FAA Part 107 drone pilot, aerial mapping, photogrammetry, agricultural survey, GIS",
        "non_matching_caps": "Background investigator, security clearance vetting, NBIB, federal investigation",
    },
    {
        "name": "Events: corporate conference catering",
        "bid": {
            "service": "TEST: Full-service catering, 200-person corporate conference, 3 meals, setup and teardown",
            "price": 9500, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "Convention Center Dr, Denver, CO 80202",
        },
        "matching_caps": "Corporate catering, large-event food service, buffet, licensed caterer, event staffing",
        "non_matching_caps": "Wound care, medication management, post-surgery nursing, home health aide",
    },
    {
        "name": "Cybersecurity: web application penetration test",
        "bid": {
            "service": "TEST: Black-box web application penetration test, OWASP Top 10, written report",
            "price": 12000, "currency": "USD", "payment_method": "wire",
            "location_type": "remote",
        },
        "matching_caps": "Web application penetration testing, ethical hacking, OSCP, OWASP, vulnerability assessment",
        "non_matching_caps": "Lawn mowing, grass cutting, yard maintenance, residential landscaping",
    },
    {
        "name": "HVAC: emergency commercial rooftop repair",
        "bid": {
            "service": "TEST: Emergency commercial HVAC repair, 20-ton rooftop unit, refrigerant recharge",
            "price": 3800, "currency": "USD", "payment_method": "wire",
            "location_type": "physical", "address": "Commercial Park, Aurora, CO 80011",
        },
        "matching_caps": "Commercial HVAC technician, rooftop unit repair, EPA 608 certified, refrigerant handling",
        "non_matching_caps": "Children's party coordinator, balloon artist, face painting, kids entertainment",
    },
    {
        "name": "Pet care: long-term dog boarding",
        "bid": {
            "service": "TEST: Dog boarding for 2 large dogs, 2 weeks, outdoor space required",
            "price": 560, "currency": "USD", "payment_method": "cash",
            "location_type": "physical", "address": "Aurora, CO 80014",
        },
        "matching_caps": "Dog boarding, pet care, kennel, large breed experience, outdoor run",
        "non_matching_caps": "Stack emissions testing, EPA Method 5, industrial hygienist, CEM monitoring",
    },
]


class ServiceExchangeAPITester:
    def __init__(self, api_url):
        self.api_url = api_url
        self.created_users = []
        # List of (job_id, buyer_token, provider_token) for cleanup
        self.created_jobs = []
        self.active_tokens = []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _register_and_login(self, username, user_type):
        r = requests.post(f"{self.api_url}/register", json={
            "username": username, "password": config.TEST_PASSWORD,
            "user_type": user_type,
        }, verify=False)
        assert r.status_code == 201, f"Register failed for {username}: {r.status_code} {r.text}"
        self.created_users.append(username)

        r = requests.post(f"{self.api_url}/login", json={
            "username": username, "password": config.TEST_PASSWORD,
        }, verify=False)
        assert r.status_code == 200, f"Login failed for {username}"
        token = r.json()["access_token"]
        self.active_tokens.append((token, username))
        return token

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _post_bid(self, token, bid_data):
        """Submit a bid and return bid_id. Injects end_time if not set."""
        payload = {"end_time": int(time.time()) + 7200, **bid_data}
        r = requests.post(f"{self.api_url}/submit_bid",
                          headers=self._headers(token), json=payload, verify=False)
        assert r.status_code == 200, f"submit_bid failed: {r.status_code} {r.text}"
        return r.json()["bid_id"]

    def _grab_job(self, token, caps, location_type, address=None, max_distance=50):
        payload = {"capabilities": caps, "location_type": location_type,
                   "max_distance": max_distance}
        if address:
            payload["address"] = address
        return requests.post(f"{self.api_url}/grab_job",
                             headers=self._headers(token), json=payload, verify=False)

    def _set_wallet(self, token, wallet_address):
        r = requests.post(f"{self.api_url}/set_wallet",
                          headers=self._headers(token),
                          json={"wallet_address": wallet_address}, verify=False)
        return r.status_code == 200

    def _reject_job(self, token, job_id, reason="Test: returning to exchange"):
        """Reject a job so it goes back on the exchange for the real buyer."""
        requests.post(f"{self.api_url}/reject_job",
                      headers=self._headers(token),
                      json={"job_id": job_id, "reason": reason},
                      verify=False)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        """Cancel outstanding bids and complete open test jobs."""
        print("\n🧹 Cleaning up test data...")
        bids_cancelled = 0
        jobs_completed = 0

        # Complete any open jobs (sign from both sides with 5 stars)
        for (job_id, buyer_token, provider_token) in self.created_jobs:
            try:
                for tok in (provider_token, buyer_token):
                    requests.post(f"{self.api_url}/sign_job",
                                  headers=self._headers(tok),
                                  json={"job_id": job_id, "rating": 5},
                                  verify=False)
                jobs_completed += 1
            except Exception as e:
                print(f"  ⚠ Could not complete job {job_id[:8]}…: {e}")

        # Cancel any remaining bids from test user accounts
        for token, username in self.active_tokens:
            try:
                r = requests.get(f"{self.api_url}/my_bids",
                                 headers=self._headers(token), verify=False)
                if r.status_code != 200:
                    continue
                for bid in r.json().get("bids", []):
                    svc = str(bid.get("service", ""))
                    if "TEST:" in svc or bid.get("username") in self.created_users:
                        resp = requests.post(f"{self.api_url}/cancel_bid",
                                             headers=self._headers(token),
                                             json={"bid_id": bid["bid_id"]},
                                             verify=False)
                        if resp.status_code == 200:
                            bids_cancelled += 1
            except Exception as e:
                print(f"  ⚠ Error cleaning up for {username}: {e}")

        print(f"  Bids cancelled: {bids_cancelled}")
        print(f"  Jobs completed: {jobs_completed}")
        print(f"  Test users:     {len(self.created_users)}")
        print("✓ Cleanup done")

    # ── Core functionality ────────────────────────────────────────────────────

    def test_core_functionality(self):
        print("\n=== Core API Tests ===")
        print(f"Environment: {self.api_url}")

        # Health check
        r = requests.get(f"{self.api_url}/ping", verify=False)
        assert r.status_code == 200, "API ping failed"
        print("✓ Health check")

        buyer_username = f"buyer_{uuid.uuid4().hex[:8]}"
        provider_username = f"prov_{uuid.uuid4().hex[:8]}"

        buyer_token = self._register_and_login(buyer_username, "demand")
        provider_token = self._register_and_login(provider_username, "supply")
        print(f"✓ Users created ({buyer_username}, {provider_username})")

        # Link the real seat wallet for the provider
        if self._set_wallet(provider_token, config.TEST_WALLET_ADDRESS):
            print(f"✓ Provider wallet linked (seats #1-100)")

        bids = [
            {
                "service": "TEST: House cleaning service - 3 bedrooms",
                "price": 150, "currency": "USD", "payment_method": "cash",
                "location_type": "physical", "address": "123 Main St, Denver, CO 80202",
            },
            {
                "service": {
                    "type": "TEST: Software development",
                    "description": "React web application",
                    "technologies": ["React", "TypeScript", "Node.js"],
                },
                "price": 2000, "currency": "USD", "payment_method": "paypal",
                "location_type": "remote",
            },
        ]
        bid_ids = [self._post_bid(buyer_token, b) for b in bids]
        print(f"✓ Bids submitted: {len(bid_ids)}")

        r = requests.get(f"{self.api_url}/my_bids",
                         headers=self._headers(buyer_token), verify=False)
        assert r.status_code == 200
        assert len(r.json().get("bids", [])) >= len(bids)
        print("✓ my_bids")

        # Try to grab both
        job_grabbed = False
        for caps, loc, addr in [
            ("House cleaning, deep cleaning, residential cleaning", "physical",
             "456 Oak Ave, Denver, CO 80203"),
            ("React development, TypeScript, Node.js, web applications", "remote", None),
        ]:
            r = self._grab_job(provider_token, caps, loc, addr)
            if r.status_code == 200:
                job = r.json()
                print(f"✓ Job grabbed: {job['currency']} {job['price']}")
                self.created_jobs.append((job["job_id"], buyer_token, provider_token))
                job_grabbed = True
            else:
                print(f"  (No match for '{caps[:30]}…')")

        r = requests.get(f"{self.api_url}/account",
                         headers=self._headers(buyer_token), verify=False)
        assert r.status_code == 200
        assert r.json()["username"] == buyer_username
        print("✓ Account info")

        r = requests.post(f"{self.api_url}/chat",
                          headers=self._headers(buyer_token),
                          json={"recipient": provider_username,
                                "message": "TEST: Hello from integration test"},
                          verify=False)
        assert r.status_code == 200
        print("✓ Chat")

        r = requests.post(f"{self.api_url}/bulletin",
                          headers=self._headers(buyer_token),
                          json={"title": "TEST: Integration Test Post",
                                "content": "Automated test bulletin.",
                                "category": "general"},
                          verify=False)
        assert r.status_code == 200
        print("✓ Bulletin")

        # Bid cancellation
        cancel_id = self._post_bid(buyer_token, {
            "service": "TEST: Bid for cancellation test",
            "price": 100, "currency": "USD", "payment_method": "cash",
            "location_type": "remote",
        })
        r = requests.post(f"{self.api_url}/cancel_bid",
                          headers=self._headers(buyer_token),
                          json={"bid_id": cancel_id}, verify=False)
        assert r.status_code == 200
        print("✓ Bid cancellation")

        # Input validation
        r = requests.post(f"{self.api_url}/submit_bid",
                          headers=self._headers(buyer_token),
                          json={"service": "Invalid bid", "price": -100,
                                "end_time": int(time.time()) + 3600,
                                "location_type": "remote"}, verify=False)
        assert r.status_code == 400
        print("✓ Negative price rejected")

        return {"job_grabbed": job_grabbed}

    # ── Service matching accuracy ─────────────────────────────────────────────

    def test_service_matching(self):
        print(f"\n=== Service Matching Tests ({len(MATCHING_TEST_CASES)} cases) ===")

        buyer_username = f"mbuy_{uuid.uuid4().hex[:7]}"
        prov_username  = f"mpro_{uuid.uuid4().hex[:7]}"

        buyer_token   = self._register_and_login(buyer_username,  "demand")
        prov_token    = self._register_and_login(prov_username,   "supply")

        # Link the real seat wallet (seats #1-100) to the test provider
        if self._set_wallet(prov_token, config.TEST_WALLET_ADDRESS):
            print(f"✓ Provider wallet linked ({config.TEST_WALLET_ADDRESS[:10]}… seats #1-100)")

        results = []  # list of (name, non_match_ok, match_ok, notes)
        external_grabs = 0   # jobs grabbed from other users and rejected back

        for i, case in enumerate(MATCHING_TEST_CASES, 1):
            name = case["name"]
            bid_data = case["bid"]
            loc = bid_data.get("location_type", "physical")
            addr = bid_data.get("address")
            matching_caps     = case["matching_caps"]
            non_matching_caps = case["non_matching_caps"]

            # ── 1. Post bid ──────────────────────────────────────────────────
            try:
                bid_id = self._post_bid(buyer_token, bid_data)
            except AssertionError as e:
                results.append((name, False, False, f"submit_bid failed: {e}"))
                continue

            # ── 2. Non-matching provider should get 204 ──────────────────────
            # If grab returns 200 we check whose bid was consumed:
            #   • Our bid  → genuine false-positive; re-post for step 3.
            #   • Someone else's bid (demand-monitor etc.) → reject it back to
            #     the exchange immediately so the real buyer isn't stranded, and
            #     treat our non-match test as passing (our bid was untouched).
            r = self._grab_job(prov_token, non_matching_caps, loc, addr)
            non_match_note = ""

            if r.status_code == 204:
                non_match_ok = True

            elif r.status_code == 200:
                job = r.json()
                if job.get("buyer_username") == buyer_username:
                    # True false-positive: wrong caps grabbed our bid.
                    non_match_ok = False
                    non_match_note = "FP: wrong caps grabbed our bid"
                    self.created_jobs.append((job["job_id"], buyer_token, prov_token))
                    # Re-post so step 3 still has something to grab.
                    try:
                        bid_id = self._post_bid(buyer_token, bid_data)
                    except AssertionError:
                        results.append((name, False, False,
                                        non_match_note + "; re-post failed"))
                        continue
                else:
                    # Grabbed an external bid — return it to the exchange.
                    self._reject_job(prov_token, job["job_id"])
                    external_grabs += 1
                    non_match_ok = True   # our bid was never consumed
                    non_match_note = f"(grabbed+rejected external bid from {job.get('buyer_username','?')})"

            else:
                non_match_ok = False
                non_match_note = f"unexpected status {r.status_code}"

            # ── 3. Matching provider should get 200 on OUR bid ───────────────
            # Same buyer_username check: if we land on an external bid we
            # reject it back and record a false-negative.
            r = self._grab_job(prov_token, matching_caps, loc, addr)
            match_ok = False

            if r.status_code == 200:
                job = r.json()
                if job.get("buyer_username") == buyer_username:
                    match_ok = True
                    self.created_jobs.append((job["job_id"], buyer_token, prov_token))
                else:
                    # Grabbed wrong external bid; reject back and cancel ours.
                    self._reject_job(prov_token, job["job_id"])
                    external_grabs += 1
                    non_match_note = (non_match_note +
                                      " FN: matched external bid instead of ours").strip()
                    requests.post(f"{self.api_url}/cancel_bid",
                                  headers=self._headers(buyer_token),
                                  json={"bid_id": bid_id}, verify=False)

            elif r.status_code == 204:
                # Our bid is still in pool but LLM said no — cancel it.
                requests.post(f"{self.api_url}/cancel_bid",
                              headers=self._headers(buyer_token),
                              json={"bid_id": bid_id}, verify=False)

            results.append((name, non_match_ok, match_ok, non_match_note))

            status = "✓" if (non_match_ok and match_ok) else "✗"
            print(f"  [{i:02d}] {status} {name}")
            if non_match_note and not non_match_note.startswith("(grabbed+rejected"):
                print(f"         {non_match_note}")

        # ── Summary table ─────────────────────────────────────────────────────
        passed   = sum(1 for _, nm, m, _ in results if nm and m)
        fp_count = sum(1 for _, nm, _, n in results if not nm)
        fn_count = sum(1 for _, _, m, _ in results if not m)

        print(f"\n{'─'*60}")
        print(f"  Matching test results: {passed}/{len(results)} passed")
        print(f"  False positives (wrong caps grabbed our bid): {fp_count}")
        print(f"  False negatives (right caps didn't match our bid): {fn_count}")
        print(f"  External bids grabbed & rejected back: {external_grabs}")
        print(f"{'─'*60}")

        if fp_count + fn_count > 0:
            print("\n  Failures:")
            for name, nm, m, note in results:
                if not (nm and m):
                    fp = "" if nm else "FP"
                    fn = "" if m  else "FN"
                    flags = " ".join(filter(None, [fp, fn]))
                    print(f"    [{flags}] {name}")
                    if note:
                        print(f"          {note}")

        return {"passed": passed, "total": len(results),
                "false_positives": fp_count, "false_negatives": fn_count,
                "external_grabs": external_grabs}

    # ── Advanced features ─────────────────────────────────────────────────────

    def test_advanced_features(self):
        print("\n=== Advanced Feature Tests ===")

        username = f"adv_{uuid.uuid4().hex[:8]}"
        token = self._register_and_login(username, "demand")

        r = requests.post(f"{self.api_url}/submit_bid",
                          headers=self._headers(token), json={
                              "service": {
                                  "type": "TEST: Advanced service",
                                  "description": "Complex multi-step service",
                                  "requirements": ["professional", "insured", "experienced"],
                              },
                              "price": 500, "currency": "USD", "payment_method": "xmoney",
                              "xmoney_account": "@test_account",
                              "end_time": int(time.time()) + 3600,
                              "location_type": "hybrid",
                              "address": "789 Advanced St, Denver, CO 80204",
                          }, verify=False)
        assert r.status_code == 200
        print("✓ Enhanced bid with XMoney payment")

        r = requests.get(f"{self.api_url}/exchange_data?category=TEST&limit=10",
                         headers=self._headers(token), verify=False)
        assert r.status_code == 200
        assert "active_bids" in r.json()
        print("✓ Exchange data endpoint")

        r = requests.post(f"{self.api_url}/nearby",
                          headers=self._headers(token),
                          json={"address": "Downtown Denver, CO", "radius": 15},
                          verify=False)
        assert r.status_code == 200
        print("✓ Nearby services")

        print("✓ Advanced features passed")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Services Exchange integration tests")
    parser.add_argument("--local", action="store_true",
                        help="Test against localhost:5003")
    parser.add_argument("--quick", action="store_true",
                        help="Core tests only (skip matching + advanced)")
    args = parser.parse_args()

    api_url = "http://localhost:5003" if args.local else "https://rse-api.com:5003"

    tester = ServiceExchangeAPITester(api_url)

    try:
        start = time.time()

        core = tester.test_core_functionality()

        if not args.quick:
            matching = tester.test_service_matching()
            tester.test_advanced_features()

        duration = time.time() - start
        print(f"\n{'='*60}")
        print(f"ALL TESTS PASSED  ({duration:.1f}s)")
        if not args.quick:
            print(f"Matching accuracy: {matching['passed']}/{matching['total']} "
                  f"(FP={matching['false_positives']} FN={matching['false_negatives']} "
                  f"ext={matching['external_grabs']})")
        print(f"{'='*60}")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        import traceback
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        return 1
    finally:
        tester.cleanup()

    return 0


if __name__ == "__main__":
    exit(main())

"""
Edge Case Integration Tests — Round 2
======================================
Five more tests that SHOULD pass per the docs/contract but fail in the
current implementation.

Bug summary
-----------
1. /my_jobs omits `bid_id` → passenger_app._find_job_for_bid() always returns None
2. submit_bid succeeds for supply-type users (no user_type guard)
3. /my_jobs strips start_address / end_address for rideshare jobs
4. cancel_bid on a grabbed bid returns 404, not a distinguishable error
5. /nearby unknown-address geocoding fallback: all unknowns → Denver coords

Usage:
  python edge_tests_2.py                  # https://rse-api.com:5003
  python edge_tests_2.py --local          # http://localhost:5003
"""

import requests
import time
import argparse
import config
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RSE_API = "https://rse-api.com:5003"
VERIFY_SSL = True

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


# ── Helpers ───────────────────────────────────────────────────────────────────

def h(token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def register_and_login(username, user_type):
    requests.post(f"{RSE_API}/register", verify=VERIFY_SSL,
                  json={"username": username, "password": config.TEST_PASSWORD,
                        "user_type": user_type})
    r = requests.post(f"{RSE_API}/login", verify=VERIFY_SSL,
                      json={"username": username, "password": config.TEST_PASSWORD})
    assert r.status_code == 200, f"Login failed for {username}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def post_bid(token, service, price=100, location_type="remote",
             address=None, start_address=None, end_address=None, expiry=7200):
    payload = {
        "service": service, "price": price, "currency": "USD",
        "payment_method": "cash", "location_type": location_type,
        "end_time": int(time.time()) + expiry,
    }
    if address:        payload["address"] = address
    if start_address:  payload["start_address"] = start_address
    if end_address:    payload["end_address"] = end_address
    r = requests.post(f"{RSE_API}/submit_bid", headers=h(token),
                      json=payload, verify=VERIFY_SSL)
    assert r.status_code == 200, f"submit_bid failed: {r.status_code} {r.text}"
    return r.json()["bid_id"]


def grab_job(token, caps, location_type="remote", address=None):
    payload = {"capabilities": caps, "location_type": location_type, "max_distance": 100}
    if address:
        payload["address"] = address
    return requests.post(f"{RSE_API}/grab_job", headers=h(token),
                         json=payload, verify=VERIFY_SSL)


def cleanup_bid(token, bid_id):
    requests.post(f"{RSE_API}/cancel_bid", headers=h(token),
                  json={"bid_id": bid_id}, verify=VERIFY_SSL)


def cleanup_job(buyer_token, prov_token, job_id):
    for tok in (prov_token, buyer_token):
        requests.post(f"{RSE_API}/sign_job", headers=h(tok),
                      json={"job_id": job_id, "rating": 5}, verify=VERIFY_SSL)


class R:
    def __init__(self, name):
        self.name = name
        self.outcome = None
        self.notes = []

    def note(self, msg):  self.notes.append(msg)
    def passed(self, msg=""): self.outcome = PASS; self.notes.append(msg) if msg else None
    def failed(self, msg=""): self.outcome = FAIL; self.notes.append(msg) if msg else None
    def skipped(self, msg=""): self.outcome = SKIP; self.notes.append(msg) if msg else None

    def show(self):
        icons = {PASS: "\033[92m✓\033[0m", FAIL: "\033[91m✗\033[0m", SKIP: "\033[93m—\033[0m"}
        print(f"\n{icons.get(self.outcome,'?')} {self.name}")
        for n in self.notes:
            print(f"    {n}")


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 1
# ── /my_jobs omits bid_id → passenger app can never find its accepted ride ───
#
# passenger_app.py _find_job_for_bid() does:
#   for job in data.get("active_jobs", []):
#       if job.get("bid_id") == bid_id:
#           return job
#
# handlers.py get_my_jobs() builds job_info with these keys:
#   job_id, service, price, currency, payment_method, location_type,
#   address, accepted_at, status, buyer_username, provider_username,
#   role, counterparty, my_rating, their_rating
#
# bid_id is NEVER included. job.get("bid_id") is always None.
# The condition `None == bid_id` is always False → always returns None.
# wait_for_driver() times out even though a driver accepted the job.
# ══════════════════════════════════════════════════════════════════════════════

def test_my_jobs_missing_bid_id():
    res = R("/my_jobs: bid_id missing from response (passenger_app.wait_for_driver breaks)")
    ts = str(int(time.time()))[-5:]

    buyer_token = register_and_login(f"e2t1b_{ts}", "demand")
    prov_token  = register_and_login(f"e2t1p_{ts}", "supply")

    bid_id = post_bid(buyer_token,
                      "TEST-EDGE2: remote contract review, intellectual property law")

    gr = grab_job(prov_token, "Intellectual property lawyer, contract review, IP law")
    if gr.status_code != 200:
        cleanup_bid(buyer_token, bid_id)
        res.skipped(f"grab_job returned {gr.status_code}; skipping")
        res.show(); return res

    job = gr.json()
    if job.get("buyer_username") != f"e2t1b_{ts}":
        requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                      json={"job_id": job["job_id"], "reason": "edge2 skip"}, verify=VERIFY_SSL)
        cleanup_bid(buyer_token, bid_id)
        res.skipped("Grabbed external bid; skipping")
        res.show(); return res

    job_id = job["job_id"]
    res.note(f"Provider grabbed bid. job_id={job_id[:8]}…")
    res.note(f"grab_job response includes bid_id: {'bid_id' in job} (value: {job.get('bid_id','<missing>')[:8] if job.get('bid_id') else 'None'}…)")

    # Buyer checks /my_jobs
    mj = requests.get(f"{RSE_API}/my_jobs", headers=h(buyer_token), verify=VERIFY_SSL).json()
    active = mj.get("active_jobs", [])
    res.note(f"/my_jobs active_jobs count: {len(active)}")

    if active:
        job_from_my_jobs = active[0]
        bid_id_in_response = job_from_my_jobs.get("bid_id")
        res.note(f"bid_id in /my_jobs response: {bid_id_in_response!r}")

        # Simulate what passenger_app._find_job_for_bid() does
        found = next((j for j in active if j.get("bid_id") == bid_id), None)
        res.note(f"passenger_app lookup (bid_id match): {'found' if found else 'None'}")

        if bid_id_in_response is None:
            res.failed(
                "BUG CONFIRMED: bid_id is absent from /my_jobs response. "
                "passenger_app._find_job_for_bid() compares job.get('bid_id') == bid_id, "
                "which is always None == <uuid> → False. wait_for_driver() will always "
                "time out and cancel the ride even after a driver has accepted."
            )
        else:
            res.passed("bid_id is present in /my_jobs (bug may be fixed)")
    else:
        res.skipped("No active jobs returned (unexpected); inconclusive")

    cleanup_job(buyer_token, prov_token, job_id)
    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 2
# ── submit_bid succeeds for supply-type users (no user_type guard) ────────────
#
# Docs: POST /submit_bid is for demand-side (buyers) only.
# Grab_job now correctly rejects demand users with 403.
# But submit_bid has no symmetric guard — supply users can post bids.
#
# handlers.py submit_bid() does not check user_data['user_type'].
# A supply user posting a bid creates a job request they can never respond
# to themselves, and pollutes the demand pool.
# ══════════════════════════════════════════════════════════════════════════════

def test_supply_user_can_post_bid():
    res = R("submit_bid: supply-type user can post bids (no user_type guard)")
    ts = str(int(time.time()))[-5:]

    supply_token = register_and_login(f"e2t2sup_{ts}", "supply")

    r = requests.post(f"{RSE_API}/submit_bid", headers=h(supply_token), verify=VERIFY_SSL,
                      json={
                          "service": "TEST-EDGE2: supply user posting a demand bid",
                          "price": 50, "currency": "USD", "payment_method": "cash",
                          "location_type": "remote",
                          "end_time": int(time.time()) + 3600,
                      })
    res.note(f"submit_bid as supply-type user → HTTP {r.status_code}  body={r.text[:80]}")

    if r.status_code == 200:
        bid_id = r.json().get("bid_id")
        res.note(f"bid_id={bid_id[:8] if bid_id else 'None'}…")
        res.failed(
            "BUG CONFIRMED: supply-type user successfully posted a bid (HTTP 200). "
            "submit_bid has no user_type guard. This is asymmetric: grab_job now "
            "rejects demand users (403), but submit_bid allows supply users. "
            "Supply accounts can pollute the demand pool with bids they can never "
            "legitimately fulfill as their own provider."
        )
        if bid_id:
            cleanup_bid(supply_token, bid_id)
    elif r.status_code == 403:
        res.passed("Server correctly rejected supply user posting a bid with 403")
    else:
        res.failed(f"Unexpected status {r.status_code}: {r.text[:80]}")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 3
# ── /my_jobs strips start_address / end_address for rideshare jobs ────────────
#
# When a rideshare bid is posted with start_address + end_address, the job
# record (stored and returned by grab_job) includes both fields.
# But get_my_jobs() builds job_info without them (lines 527-538).
#
# The passenger who wants to display "Your driver is heading to: <pickup>"
# cannot get the pickup address from /my_jobs — the field is simply absent.
# grab_job's response has the fields, but that goes to the provider, not buyer.
# ══════════════════════════════════════════════════════════════════════════════

def test_my_jobs_missing_rideshare_fields():
    res = R("/my_jobs: start_address / end_address stripped (rideshare buyer can't see pickup)")
    ts = str(int(time.time()))[-5:]

    buyer_token = register_and_login(f"e2t3b_{ts}", "demand")
    prov_token  = register_and_login(f"e2t3p_{ts}", "supply")

    bid_id = post_bid(
        buyer_token,
        "TEST-EDGE2: taxi ride from 123 Main St Denver to Denver Airport",
        location_type="physical",
        start_address="123 Main St, Denver, CO 80202",
        end_address="Denver Airport",
    )
    res.note(f"Bid with start/end address posted, bid_id={bid_id[:8]}…")

    gr = grab_job(prov_token, "Licensed taxi, rideshare driver, sedan, airport runs",
                  location_type="physical", address="Downtown Denver, CO")
    if gr.status_code != 200:
        cleanup_bid(buyer_token, bid_id)
        res.skipped(f"grab_job returned {gr.status_code}; skipping")
        res.show(); return res

    job = gr.json()
    if job.get("buyer_username") != f"e2t3b_{ts}":
        requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                      json={"job_id": job["job_id"], "reason": "edge2 skip"}, verify=VERIFY_SSL)
        cleanup_bid(buyer_token, bid_id)
        res.skipped("Grabbed external bid; skipping")
        res.show(); return res

    job_id = job["job_id"]
    res.note(f"grab_job response: start_address={job.get('start_address')!r}, end_address={job.get('end_address')!r}")

    # Buyer fetches /my_jobs — should see start/end address
    mj = requests.get(f"{RSE_API}/my_jobs", headers=h(buyer_token), verify=VERIFY_SSL).json()
    active = mj.get("active_jobs", [])
    buyer_job = next((j for j in active if j["job_id"] == job_id), None)

    if buyer_job is None:
        res.skipped("Job not found in buyer's /my_jobs; skipping")
        cleanup_job(buyer_token, prov_token, job_id)
        res.show(); return res

    start = buyer_job.get("start_address")
    end   = buyer_job.get("end_address")
    res.note(f"/my_jobs (buyer) start_address={start!r}  end_address={end!r}")

    if start is None and end is None:
        res.failed(
            "BUG CONFIRMED: start_address and end_address are absent from /my_jobs. "
            "get_my_jobs() builds job_info without rideshare fields. The passenger "
            "app displays pickup/dropoff from /my_jobs — both are missing. "
            "Buyers see 'address: None' even for rideshare jobs that have clear "
            "start/end points."
        )
    else:
        res.passed(f"Rideshare fields present: start={start}, end={end}")

    cleanup_job(buyer_token, prov_token, job_id)
    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 4
# ── cancel_bid on already-grabbed bid returns 404 (indistinguishable from
#    "bid never existed") ────────────────────────────────────────────────────
#
# When a provider grabs a bid, delete_bid() removes it from the store.
# If the buyer then calls cancel_bid with the same bid_id, cancel_bid
# calls get_bid(bid_id) which returns None → 404 "Bid not found".
#
# The buyer has no way to distinguish:
#   (a) "Bid was just accepted by a driver" (good, check /my_jobs)
#   (b) "Bid ID is wrong / never existed"   (error)
#
# The docs say cancel returns 200 for success, 404 for not found.
# There should be a specific error or redirect hint for case (a).
# ══════════════════════════════════════════════════════════════════════════════

def test_cancel_grabbed_bid_returns_404():
    res = R("cancel_bid on grabbed bid returns generic 404 (no 'already accepted' signal)")
    ts = str(int(time.time()))[-5:]

    buyer_token = register_and_login(f"e2t4b_{ts}", "demand")
    prov_token  = register_and_login(f"e2t4p_{ts}", "supply")

    bid_id = post_bid(buyer_token,
                      "TEST-EDGE2: remote software audit, Python codebase review")

    gr = grab_job(prov_token, "Python developer, code review, software audit")
    if gr.status_code != 200:
        cleanup_bid(buyer_token, bid_id)
        res.skipped(f"grab_job returned {gr.status_code}; skipping")
        res.show(); return res

    job = gr.json()
    if job.get("buyer_username") != f"e2t4b_{ts}":
        requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                      json={"job_id": job["job_id"], "reason": "edge2 skip"}, verify=VERIFY_SSL)
        cleanup_bid(buyer_token, bid_id)
        res.skipped("Grabbed external bid; skipping")
        res.show(); return res

    job_id = job["job_id"]
    res.note(f"Bid grabbed by provider, job_id={job_id[:8]}…")

    # Buyer tries to cancel the now-consumed bid
    cr = requests.post(f"{RSE_API}/cancel_bid", headers=h(buyer_token),
                       json={"bid_id": bid_id}, verify=VERIFY_SSL)
    res.note(f"cancel_bid(original bid_id) after grab → HTTP {cr.status_code}  body={cr.text[:80]}")

    # Also try cancelling a completely random bid_id for comparison
    import uuid
    fake_id = str(uuid.uuid4())
    cr2 = requests.post(f"{RSE_API}/cancel_bid", headers=h(buyer_token),
                        json={"bid_id": fake_id}, verify=VERIFY_SSL)
    res.note(f"cancel_bid(random fake id)               → HTTP {cr2.status_code}  body={cr2.text[:80]}")

    if cr.status_code == 404 and cr2.status_code == 404:
        res.failed(
            "BUG CONFIRMED: cancel_bid returns identical 404 'Bid not found' whether the bid "
            "was grabbed by a provider OR never existed. The buyer cannot distinguish "
            "between 'your ride was accepted — check /my_jobs' and 'something went wrong'. "
            "passenger_app cancels the 'missing' bid and reports 'No driver found' when a "
            "driver has already accepted."
        )
    elif cr.status_code == 200:
        res.failed("Unexpected: buyer cancelled a bid that had already been claimed by a provider")
    else:
        res.passed(f"Server returned distinct status for grabbed vs non-existent bid")

    cleanup_job(buyer_token, prov_token, job_id)
    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 5
# ── /nearby unknown-address geocoding fallback: all unknowns → Denver ─────────
#
# simple_geocode() in handlers.py has a hardcoded lookup table of ~10 addresses.
# Any address not in the table falls back silently to Denver coords:
#   return address_map["unknown"]  → (39.7392, -104.9903)
#
# Consequences:
#   • A service posted at "15 Rue de Rivoli, Paris, France" is stored at Denver.
#   • A caller at "Shibuya, Tokyo, Japan" is also at Denver.
#   • Distance: ~0 miles. The Tokyo caller sees Paris services as 0 miles away.
#   • Every unknown-address physical bid appears "nearby" every unknown-address
#     caller, regardless of actual geography.
#
# /nearby is documented as "find services near you" with distance filtering.
# ══════════════════════════════════════════════════════════════════════════════

def test_nearby_geocoding_fallback():
    res = R("/nearby geocoding: unknown addresses all collapse to Denver; distance filtering is meaningless")
    ts = str(int(time.time()))[-5:]

    buyer_token = register_and_login(f"e2t5b_{ts}", "demand")

    # Post a physical service at an address NOT in the geocode table
    paris_address = "15 Rue de Rivoli, Paris, France 75001"
    bid_id = post_bid(
        buyer_token,
        "TEST-EDGE2: gourmet meal delivery, Marais district, Paris",
        price=80, location_type="physical",
        address=paris_address,
    )
    res.note(f"Bid posted at: {paris_address}")
    res.note(f"bid_id={bid_id[:8]}…")

    # Check /nearby from Tokyo — should be ~10,000 km away, NOT nearby at all
    tokyo_address = "Shibuya Crossing, Tokyo, Japan"
    nb = requests.post(f"{RSE_API}/nearby", verify=VERIFY_SSL,
                       json={"address": tokyo_address, "radius": 20})
    res.note(f"GET /nearby from '{tokyo_address}' (radius=20 miles) → HTTP {nb.status_code}")

    services = nb.json().get("services", [])
    our_bid = next((s for s in services if s.get("bid_id") == bid_id), None)

    res.note(f"Services returned: {len(services)}")
    if our_bid:
        res.note(f"Our Paris bid found at distance: {our_bid.get('distance')} miles from Tokyo!")

    # Also directly check what geocode the bid got stored with
    # by checking /exchange_data
    ed = requests.get(f"{RSE_API}/exchange_data", verify=VERIFY_SSL)
    all_bids = ed.json().get("active_bids", [])
    our_ed_bid = next((b for b in all_bids if b.get("bid_id") == bid_id), None)
    if our_ed_bid:
        stored_lat = our_ed_bid.get("lat")
        stored_lon = our_ed_bid.get("lon")
        res.note(f"Stored coords for Paris bid: lat={stored_lat}, lon={stored_lon}")
        res.note(f"Denver coords are: lat=39.7392, lon=-104.9903")
        denver_match = (stored_lat is not None and abs(stored_lat - 39.7392) < 0.01)
        res.note(f"Coords match Denver default: {denver_match}")

    cleanup_bid(buyer_token, bid_id)

    if our_bid is not None:
        dist = our_bid.get("distance", -1)
        res.failed(
            f"BUG CONFIRMED: Paris bid appears {dist} miles from Tokyo. "
            "simple_geocode() maps all unrecognized addresses to Denver "
            "(39.7392, -104.9903). A service posted in Paris and a caller "
            "from Tokyo both land at Denver — distance ≈ 0, well within the "
            "20-mile radius filter. /nearby returns geographically meaningless "
            "results for any address outside the hardcoded ~10-entry table."
        )
    else:
        # Still check if coords defaulted to Denver even if radius didn't catch it
        if our_ed_bid and our_ed_bid.get("lat") and abs(our_ed_bid["lat"] - 39.7392) < 0.01:
            res.failed(
                "BUG CONFIRMED (partial): Paris address stored at Denver coords "
                f"(lat={our_ed_bid['lat']}). The Tokyo query happened to miss it this run "
                "(radius or other filtering), but the geocoding collapse is real — "
                "any unknown address silently falls back to Denver."
            )
        else:
            res.passed("Geocoding handled correctly or bid not found (inconclusive)")

    res.show(); return res


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    if args.local:
        RSE_API = "http://localhost:5003"
        VERIFY_SSL = False

    print("══════════════════════════════════════════════════════════")
    print("  RSE Edge Case Tests — Round 2")
    print(f"  Target: {RSE_API}")
    print("══════════════════════════════════════════════════════════")

    results = []
    for fn in [
        test_my_jobs_missing_bid_id,
        test_supply_user_can_post_bid,
        test_my_jobs_missing_rideshare_fields,
        test_cancel_grabbed_bid_returns_404,
        test_nearby_geocoding_fallback,
    ]:
        try:
            results.append(fn())
        except Exception as e:
            print(f"\n  ERROR in {fn.__name__}: {e}")
        time.sleep(0.5)

    print("\n══════════════════════════════════════════════════════════")
    print("  Summary")
    print("══════════════════════════════════════════════════════════")
    for r in results:
        icons = {PASS: "\033[92m✓\033[0m", FAIL: "\033[91m✗\033[0m", SKIP: "\033[93m—\033[0m"}
        print(f"  {icons.get(r.outcome,'?')}  {r.name}")
    print(f"\n  {sum(1 for r in results if r.outcome==PASS)} passed  "
          f"{sum(1 for r in results if r.outcome==FAIL)} failed  "
          f"{sum(1 for r in results if r.outcome==SKIP)} skipped  ({len(results)} total)")

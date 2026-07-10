"""
Edge Case Integration Tests — The Services Exchange
====================================================
Five tests that SHOULD pass according to the documentation and API contract
but are predicted to FAIL due to implementation bugs found in handlers.py.

Each test documents:
  - What the docs / contract says should happen
  - What the code actually does
  - The predicted failure mode
  - The observed result

Usage:
  python edge_tests.py                  # https://rse-api.com:5003
  python edge_tests.py --local          # http://localhost:5003
"""

import requests
import time
import uuid
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


def register_and_login(username, user_type, password=None):
    pw = password or config.TEST_PASSWORD
    requests.post(f"{RSE_API}/register", verify=VERIFY_SSL,
                  json={"username": username, "password": pw, "user_type": user_type})
    r = requests.post(f"{RSE_API}/login", verify=VERIFY_SSL,
                      json={"username": username, "password": pw})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def post_bid(token, service, price=100, location_type="remote",
             address=None, start_address=None, end_address=None,
             expiry=7200):
    payload = {
        "service": service,
        "price": price,
        "currency": "USD",
        "payment_method": "cash",
        "location_type": location_type,
        "end_time": int(time.time()) + expiry,
    }
    if address:
        payload["address"] = address
    if start_address:
        payload["start_address"] = start_address
    if end_address:
        payload["end_address"] = end_address
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


def sign_job_field(token, job_id, field_name, rating=5):
    """Sign a job using the given field name (correct=star_rating, documented=rating)."""
    return requests.post(f"{RSE_API}/sign_job", headers=h(token),
                         json={"job_id": job_id, field_name: rating},
                         verify=VERIFY_SSL)


def cleanup_job(buyer_token, prov_token, job_id):
    """Best-effort: sign from both sides to leave the exchange clean."""
    for tok in (prov_token, buyer_token):
        for field in ("star_rating", "rating"):
            r = requests.post(f"{RSE_API}/sign_job", headers=h(tok),
                              json={"job_id": job_id, field: 5},
                              verify=VERIFY_SSL)
            if r.status_code == 200:
                break


def cleanup_bid(token, bid_id):
    requests.post(f"{RSE_API}/cancel_bid", headers=h(token),
                  json={"bid_id": bid_id}, verify=VERIFY_SSL)


# ── Test runner ───────────────────────────────────────────────────────────────

class EdgeTestResult:
    def __init__(self, name):
        self.name = name
        self.outcome = None
        self.notes = []

    def note(self, msg):
        self.notes.append(msg)

    def passed(self, msg=""):
        self.outcome = PASS
        if msg:
            self.notes.append(msg)

    def failed(self, msg=""):
        self.outcome = FAIL
        if msg:
            self.notes.append(msg)

    def skipped(self, msg=""):
        self.outcome = SKIP
        if msg:
            self.notes.append(msg)

    def show(self):
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "—"}.get(self.outcome, "?")
        color = {"PASS": "\033[92m", "FAIL": "\033[91m", "SKIP": "\033[93m"}.get(self.outcome, "")
        reset = "\033[0m"
        print(f"\n{color}{icon} {self.name}{reset}")
        for n in self.notes:
            print(f"    {n}")


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 1
# ── sign_job: documented field is `rating`; handler reads `star_rating` ──────
#
# Docs say: POST /sign_job { "job_id": str, "rating": int }
# Reference apps (passenger_app.py, driver_app.py, int_tests.py cleanup) all
# use the field name `rating`.
#
# handlers.py line 906:
#   star_rating = data.get('star_rating')
#   if not job_id or star_rating is None:
#       return {"error": "Job ID and rating required"}, 400
#
# Prediction: calling sign_job with {"rating": 5} returns 400.
# ══════════════════════════════════════════════════════════════════════════════

def test_sign_job_rating_field_name():
    res = EdgeTestResult("sign_job: documented `rating` field rejected (handler wants `star_rating`)")
    ts = str(int(time.time()))[-5:]

    buyer_token  = register_and_login(f"et1b_{ts}", "demand")
    prov_token   = register_and_login(f"et1p_{ts}", "supply")

    bid_id = post_bid(buyer_token,
                      "TEST-EDGE: remote document review, legal proofreading")

    gr = grab_job(prov_token, "Legal document reviewer, proofreader, lawyer")
    if gr.status_code != 200:
        cleanup_bid(buyer_token, bid_id)
        res.skipped(f"grab_job returned {gr.status_code} (no matching bid); skipping")
        res.show()
        return res

    job = gr.json()
    if job.get("buyer_username") != f"et1b_{ts}":
        # Grabbed external bid — return it and skip
        requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                      json={"job_id": job["job_id"], "reason": "edge test skip"}, verify=VERIFY_SSL)
        cleanup_bid(buyer_token, bid_id)
        res.skipped("Grabbed an external bid; skipping this run")
        res.show()
        return res

    job_id = job["job_id"]
    res.note(f"job_id={job_id[:8]}…")

    # ── Attempt to sign with documented field name `rating` ──
    r_doc = sign_job_field(prov_token, job_id, "rating", 5)
    res.note(f"sign_job(rating=5)       → HTTP {r_doc.status_code}  body={r_doc.text[:80]}")

    # ── Attempt to sign with the ACTUAL field name `star_rating` ──
    r_real = sign_job_field(prov_token, job_id, "star_rating", 5)
    res.note(f"sign_job(star_rating=5)  → HTTP {r_real.status_code}  body={r_real.text[:80]}")

    if r_doc.status_code == 400 and r_real.status_code == 200:
        res.failed(
            "BUG CONFIRMED: `rating` → 400 error; `star_rating` → 200. "
            "Docs and reference apps all use `rating` — they silently fail to sign."
        )
    elif r_doc.status_code == 200:
        res.passed("Both field names accepted (bug may have been fixed)")
    else:
        res.failed(f"Unexpected: rating={r_doc.status_code}, star_rating={r_real.status_code}")

    # Cleanup — sign buyer side too
    cleanup_job(buyer_token, prov_token, job_id)
    res.show()
    return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 2
# ── register: duplicate username returns 400, docs/apps expect 409 ───────────
#
# The taxi reference apps (and common REST practice) treat 409 Conflict as
# "username taken; proceed to login instead."  The handler returns 400.
#
# handlers.py line 362:
#   if account_exists(username):
#       return {"error": "Username already exists"}, 400
#
# Prediction: second /register call returns 400, not 409.
# The passenger_app / driver_app check `r.status_code == 409`; they never
# match and fall through to `r.raise_for_status()` which raises on 400.
# ══════════════════════════════════════════════════════════════════════════════

def test_register_duplicate_status_code():
    res = EdgeTestResult("register: duplicate username returns 400 not 409 (reference apps break)")
    ts = str(int(time.time()))[-5:]
    username = f"et2dup_{ts}"
    pw = config.TEST_PASSWORD

    r1 = requests.post(f"{RSE_API}/register", verify=VERIFY_SSL,
                       json={"username": username, "password": pw, "user_type": "demand"})
    res.note(f"First  /register → HTTP {r1.status_code}  (expected 201)")

    r2 = requests.post(f"{RSE_API}/register", verify=VERIFY_SSL,
                       json={"username": username, "password": pw, "user_type": "demand"})
    res.note(f"Second /register → HTTP {r2.status_code}  body={r2.text[:80]}")
    res.note(f"Docs / reference apps expect 409 Conflict")

    if r1.status_code == 201 and r2.status_code == 400:
        res.failed(
            "BUG CONFIRMED: duplicate user returns 400 not 409. "
            "passenger_app.py and driver_app.py both check `if r.status_code == 409` "
            "to detect an existing account — they miss it, then call r.raise_for_status() "
            "which raises an exception, aborting the app on every run after first registration."
        )
    elif r2.status_code == 409:
        res.passed("Server returned 409 as documented")
    else:
        res.failed(f"First={r1.status_code}, second={r2.status_code}")

    res.show()
    return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 3
# ── reject_job: restored bid has new bid_id; buyer can't track it ─────────────
#
# Docs say: reject_job "returns the ride to the exchange for another driver."
# The implication is the buyer's pending request is back in the pool.
#
# handlers.py line 869:
#   bid_id = str(uuid.uuid4())   ← NEW random ID, NOT the original
#
# The buyer was polling /my_bids for the ORIGINAL bid_id.  After reject_job,
# the original bid is gone and a new one with a fresh UUID appears.
# The passenger_app.wait_for_driver() will time out even though a bid exists.
#
# Also: start_address / end_address are NOT copied to the restored bid.
# ══════════════════════════════════════════════════════════════════════════════

def test_reject_job_bid_id_orphan():
    res = EdgeTestResult("reject_job: restored bid gets new bid_id; buyer loses track of request")
    ts = str(int(time.time()))[-5:]

    buyer_token = register_and_login(f"et3b_{ts}", "demand")
    prov_token  = register_and_login(f"et3p_{ts}", "supply")

    original_bid_id = post_bid(
        buyer_token,
        "TEST-EDGE: rideshare from 123 Main St, Denver to Denver Airport",
        location_type="physical",
        start_address="123 Main St, Denver, CO 80202",
        end_address="Denver Airport",
    )
    res.note(f"Original bid_id = {original_bid_id[:8]}…")

    # Grab
    gr = grab_job(prov_token, "Licensed taxi driver, rideshare, sedan",
                  location_type="physical", address="Downtown Denver, CO")
    if gr.status_code != 200:
        cleanup_bid(buyer_token, original_bid_id)
        res.skipped(f"grab_job returned {gr.status_code}; skipping")
        res.show()
        return res

    job = gr.json()
    if job.get("buyer_username") != f"et3b_{ts}":
        requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                      json={"job_id": job["job_id"], "reason": "edge test skip"}, verify=VERIFY_SSL)
        cleanup_bid(buyer_token, original_bid_id)
        res.skipped("Grabbed external bid; skipping")
        res.show()
        return res

    job_id = job["job_id"]
    res.note(f"job_id = {job_id[:8]}…  (provider grabbed successfully)")

    # Reject the job — should put bid back
    rj = requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                       json={"job_id": job_id, "reason": "edge test: intentional reject"},
                       verify=VERIFY_SSL)
    res.note(f"reject_job → HTTP {rj.status_code}")

    # Now check: does the buyer see any bid with the ORIGINAL bid_id?
    time.sleep(0.5)
    mb = requests.get(f"{RSE_API}/my_bids", headers=h(buyer_token), verify=VERIFY_SSL)
    bids = mb.json().get("bids", [])
    found_original = any(b["bid_id"] == original_bid_id for b in bids)
    all_bid_ids = [b["bid_id"][:8] for b in bids]
    res.note(f"Buyer's /my_bids after reject: {len(bids)} bid(s), ids={all_bid_ids}")
    res.note(f"Original bid_id still present: {found_original}")

    # Check whether start_address / end_address survived on any restored bid
    if bids:
        for b in bids:
            has_start = bool(b.get("start_address") or b.get("address"))
            res.note(f"  bid {b['bid_id'][:8]} has address info: {has_start}")
        restored = bids[0]
        start_addr = restored.get("start_address")
        res.note(f"  start_address on restored bid: {start_addr!r} (expected '123 Main St, Denver, CO 80202')")

    if not found_original and len(bids) >= 1:
        res.failed(
            "BUG CONFIRMED: original bid_id is gone after reject; a new bid appeared with a "
            "different UUID. The buyer (and passenger_app.wait_for_driver) can never find "
            "the restored bid because they're polling the original bid_id. "
            "Also: start_address / end_address are not restored in the new bid."
        )
    elif not found_original and len(bids) == 0:
        res.failed("BUG: bid was not restored at all after reject_job")
    else:
        res.passed("Original bid_id preserved after reject (unexpected — bug may be fixed)")

    # Cleanup any lingering bids
    for b in bids:
        cleanup_bid(buyer_token, b["bid_id"])
    res.show()
    return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 4
# ── grab_job: demand-type users can grab jobs (no user_type guard) ────────────
#
# The docs describe /grab_job as a supply-side endpoint for providers.
# A demand-type user (a passenger/buyer) should not be able to act as a
# provider and grab jobs.  This would let buyers claim their own bids,
# manipulate the job queue, and earn reputation without delivering services.
#
# handlers.py grab_job():
#   - Checks SEAT_VERIFICATION_ENABLED (currently False on production)
#   - No check of user_data['user_type'] == 'supply' anywhere
#
# Prediction: a demand-type user can call /grab_job and receive a 200 job.
# ══════════════════════════════════════════════════════════════════════════════

def test_demand_user_can_grab_job():
    res = EdgeTestResult("grab_job: demand-type user can grab supply jobs (no user_type guard)")
    ts = str(int(time.time()))[-5:]

    # Both accounts are demand type
    demand_buyer_token = register_and_login(f"et4buyer_{ts}", "demand")
    demand_prov_token  = register_and_login(f"et4demgrab_{ts}", "demand")  # demand posing as provider

    bid_id = post_bid(
        demand_buyer_token,
        "TEST-EDGE: online tutoring, high-school math, 1 hour",
        location_type="remote",
    )
    res.note(f"Bid posted by demand user {f'et4buyer_{ts}'[:14]}, bid_id={bid_id[:8]}…")

    gr = grab_job(demand_prov_token, "Online tutor, math, algebra, calculus, SAT prep",
                  location_type="remote")

    res.note(f"grab_job by demand-type user → HTTP {gr.status_code}")

    if gr.status_code == 200:
        job = gr.json()
        if job.get("buyer_username") == f"et4buyer_{ts}":
            res.failed(
                "BUG CONFIRMED: a demand-type user successfully grabbed a job (HTTP 200). "
                "No user_type enforcement exists in grab_job. Any buyer account can act "
                "as a provider, claim bids, accumulate reputation, and disrupt the marketplace."
            )
            res.note(f"job_id={job['job_id'][:8]}…  buyer={job['buyer_username']}  provider={job['provider_username']}")
            cleanup_job(demand_buyer_token, demand_prov_token, job["job_id"])
        else:
            # Grabbed external — return it, our bid still open
            requests.post(f"{RSE_API}/reject_job", headers=h(demand_prov_token),
                          json={"job_id": job["job_id"], "reason": "edge test return"}, verify=VERIFY_SSL)
            cleanup_bid(demand_buyer_token, bid_id)
            res.note("Grabbed external bid (couldn't verify against our bid); see note")
            res.failed("Cannot confirm — grabbed external bid. Run again in a quiet environment.")
    elif gr.status_code == 403:
        res.passed("Server correctly rejected demand-type user with 403")
        cleanup_bid(demand_buyer_token, bid_id)
    elif gr.status_code == 204:
        res.note("No matching bid found (204) — possible if our bid expired or LLM didn't match")
        res.skipped("204 returned; inconclusive (bid may not have matched)")
        cleanup_bid(demand_buyer_token, bid_id)
    else:
        res.failed(f"Unexpected status {gr.status_code}: {gr.text[:80]}")
        cleanup_bid(demand_buyer_token, bid_id)

    res.show()
    return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 5
# ── sign_job: rejected jobs can still be signed (no status guard) ─────────────
#
# When a provider calls reject_job, the job transitions to status='rejected'.
# The docs say sign_job is for completing a finished job and building reputation.
# Logically, a rejected job was never performed and should not be rateable.
#
# handlers.py sign_job() lines 914-926:
#   job = get_job(job_id)
#   if not job:  → 404
#   if not (is_buyer or is_provider):  → 403
#   if job.get(sign_field):  → 400 "Already signed"
#   # NO check: if job['status'] != 'accepted': return error
#
# Prediction: both parties can sign a rejected job, updating each other's
# reputation scores and incrementing completed_jobs — for a job never done.
# ══════════════════════════════════════════════════════════════════════════════

def test_sign_rejected_job():
    res = EdgeTestResult("sign_job: rejected job can be signed, boosting reputation for unperformed work")
    ts = str(int(time.time()))[-5:]

    buyer_token = register_and_login(f"et5b_{ts}", "demand")
    prov_token  = register_and_login(f"et5p_{ts}", "supply")

    # Check provider's initial completed_jobs count
    acct_before = requests.get(f"{RSE_API}/account", headers=h(prov_token), verify=VERIFY_SSL).json()
    jobs_before = acct_before.get("completed_jobs", 0)
    rep_before  = acct_before.get("reputation_score", 2.5)
    res.note(f"Provider before: completed_jobs={jobs_before}, reputation={rep_before}")

    bid_id = post_bid(buyer_token,
                      "TEST-EDGE: house cleaning, 3-bedroom, one-time deep clean",
                      location_type="physical",
                      address="200 Elm St, Denver, CO 80203")

    gr = grab_job(prov_token, "Residential cleaning, house cleaning, maid service, deep clean",
                  location_type="physical", address="200 Elm St, Denver, CO 80203")

    if gr.status_code != 200:
        cleanup_bid(buyer_token, bid_id)
        res.skipped(f"grab_job returned {gr.status_code}; skipping")
        res.show()
        return res

    job = gr.json()
    if job.get("buyer_username") != f"et5b_{ts}":
        requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                      json={"job_id": job["job_id"], "reason": "edge test skip"}, verify=VERIFY_SSL)
        cleanup_bid(buyer_token, bid_id)
        res.skipped("Grabbed external bid; skipping")
        res.show()
        return res

    job_id = job["job_id"]
    res.note(f"job_id={job_id[:8]}…  status after grab: accepted")

    # Provider rejects the job (never performed)
    rj = requests.post(f"{RSE_API}/reject_job", headers=h(prov_token),
                       json={"job_id": job_id, "reason": "edge test: intentional reject"},
                       verify=VERIFY_SSL)
    res.note(f"reject_job → HTTP {rj.status_code}")

    # Now try to sign the REJECTED job with the correct field name
    r_prov = requests.post(f"{RSE_API}/sign_job", headers=h(prov_token),
                           json={"job_id": job_id, "star_rating": 5}, verify=VERIFY_SSL)
    r_buyer = requests.post(f"{RSE_API}/sign_job", headers=h(buyer_token),
                            json={"job_id": job_id, "star_rating": 5}, verify=VERIFY_SSL)

    res.note(f"sign_job (provider, rejected job) → HTTP {r_prov.status_code}  {r_prov.text[:60]}")
    res.note(f"sign_job (buyer,    rejected job) → HTTP {r_buyer.status_code}  {r_buyer.text[:60]}")

    # Check reputation after signing
    time.sleep(0.3)
    acct_after = requests.get(f"{RSE_API}/account", headers=h(prov_token), verify=VERIFY_SSL).json()
    jobs_after = acct_after.get("completed_jobs", 0)
    rep_after  = acct_after.get("reputation_score", 2.5)
    res.note(f"Provider after:  completed_jobs={jobs_after}, reputation={rep_after}")

    if r_prov.status_code == 200 and r_buyer.status_code == 200:
        if jobs_after > jobs_before:
            res.failed(
                "BUG CONFIRMED: both parties successfully signed a rejected (never-performed) job. "
                f"Provider's completed_jobs went from {jobs_before} → {jobs_after} and "
                f"reputation from {rep_before} → {rep_after}. "
                "The sign_job handler has no guard on job['status'] — any rejected job "
                "can be signed, inflating reputation scores."
            )
        else:
            res.failed(
                "BUG CONFIRMED: sign_job accepted on a rejected job (HTTP 200 both sides), "
                "but completed_jobs didn't increment. Partial bug — ratings still written."
            )
    elif r_prov.status_code == 400 or r_buyer.status_code == 400:
        res.passed("Server correctly blocked signing a rejected job with 400")
    else:
        res.failed(f"Unexpected: prov={r_prov.status_code}, buyer={r_buyer.status_code}")

    # Clean up restored bid from reject_job
    mb = requests.get(f"{RSE_API}/my_bids", headers=h(buyer_token), verify=VERIFY_SSL).json()
    for b in mb.get("bids", []):
        cleanup_bid(buyer_token, b["bid_id"])

    res.show()
    return res


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSE edge-case integration tests")
    parser.add_argument("--local", action="store_true", help="Run against localhost:5003")
    args = parser.parse_args()

    if args.local:
        RSE_API = "http://localhost:5003"
        VERIFY_SSL = False

    print("══════════════════════════════════════════════════════════")
    print("  RSE Edge Case Tests")
    print(f"  Target: {RSE_API}")
    print("══════════════════════════════════════════════════════════")

    results = []
    for test_fn in [
        test_sign_job_rating_field_name,
        test_register_duplicate_status_code,
        test_reject_job_bid_id_orphan,
        test_demand_user_can_grab_job,
        test_sign_rejected_job,
    ]:
        try:
            r = test_fn()
            results.append(r)
        except Exception as e:
            print(f"\n  ERROR running {test_fn.__name__}: {e}")
        time.sleep(1)

    print("\n══════════════════════════════════════════════════════════")
    print("  Summary")
    print("══════════════════════════════════════════════════════════")
    for r in results:
        icon = {"PASS": "\033[92m✓\033[0m", "FAIL": "\033[91m✗\033[0m", "SKIP": "\033[93m—\033[0m"}.get(r.outcome, "?")
        print(f"  {icon}  {r.name}")
    passes = sum(1 for r in results if r.outcome == PASS)
    fails  = sum(1 for r in results if r.outcome == FAIL)
    skips  = sum(1 for r in results if r.outcome == SKIP)
    print(f"\n  {passes} passed  {fails} failed  {skips} skipped  ({len(results)} total)")

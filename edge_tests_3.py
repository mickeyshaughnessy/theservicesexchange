"""
Edge Case Integration Tests — Round 3
======================================
Five tests that should pass per docs/contract but fail in the implementation.

1. /nearby unrecognizable address → silent 200 empty (should be 400/useful error)
2. /exchange_data?location=X includes all remote bids regardless of X
3. sign_job accepts float ratings (e.g. 3.7) — docs say integer 1-5
4. grab_job: remote provider grabs hybrid bid with no distance filter
5. reject_job: rejecting provider can immediately re-grab the same bid

Usage:
  python edge_tests_3.py                  # https://rse-api.com:5003
  python edge_tests_3.py --local          # http://localhost:5003
"""

import requests
import time
import argparse
import config
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RSE_API  = "https://rse-api.com:5003"
VERIFY   = True
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


# ── Helpers ───────────────────────────────────────────────────────────────────

def h(token=None):
    return {"Authorization": f"Bearer {token}"} if token else {}

def register_and_login(username, user_type):
    requests.post(f"{RSE_API}/register", verify=VERIFY,
                  json={"username": username, "password": config.TEST_PASSWORD,
                        "user_type": user_type})
    r = requests.post(f"{RSE_API}/login", verify=VERIFY,
                      json={"username": username, "password": config.TEST_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]

def post_bid(token, service, price=100, location_type="remote",
             address=None, expiry=7200):
    payload = {"service": service, "price": price, "currency": "USD",
               "payment_method": "cash", "location_type": location_type,
               "end_time": int(time.time()) + expiry}
    if address:
        payload["address"] = address
    r = requests.post(f"{RSE_API}/submit_bid", headers=h(token),
                      json=payload, verify=VERIFY)
    assert r.status_code == 200, f"submit_bid failed: {r.status_code} {r.text}"
    return r.json()["bid_id"]

def grab_job(token, caps, location_type="remote", address=None, max_dist=200):
    body = {"capabilities": caps, "location_type": location_type,
            "max_distance": max_dist}
    if address:
        body["address"] = address
    return requests.post(f"{RSE_API}/grab_job", headers=h(token),
                         json=body, verify=VERIFY)

def cancel_bid(token, bid_id):
    requests.post(f"{RSE_API}/cancel_bid", headers=h(token),
                  json={"bid_id": bid_id}, verify=VERIFY)

def sign_and_cleanup(buyer_tok, prov_tok, job_id):
    for tok in (prov_tok, buyer_tok):
        requests.post(f"{RSE_API}/sign_job", headers=h(tok),
                      json={"job_id": job_id, "rating": 5}, verify=VERIFY)

def reject_job(token, job_id, reason="test"):
    return requests.post(f"{RSE_API}/reject_job", headers=h(token),
                         json={"job_id": job_id, "reason": reason}, verify=VERIFY)


class R:
    def __init__(self, name):
        self.name = name
        self.outcome = None
        self.notes = []

    def note(self, m):   self.notes.append(m)
    def passed(self, m=""): self.outcome = PASS; self.note(m) if m else None
    def failed(self, m=""): self.outcome = FAIL; self.note(m) if m else None
    def skipped(self, m=""): self.outcome = SKIP; self.note(m) if m else None

    def show(self):
        ic = {PASS: "\033[92m✓\033[0m", FAIL: "\033[91m✗\033[0m",
              SKIP: "\033[93m—\033[0m"}.get(self.outcome, "?")
        print(f"\n{ic} {self.name}")
        for n in self.notes:
            print(f"    {n}")


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 1
# ── /nearby with unrecognizable address returns silent 200 empty ──────────────
#
# Since the geocoding fix, geocode_address() returns (None, None) for
# addresses Nominatim can't resolve.  In nearby_services(), user_lat and
# user_lon then hold None.  calculate_distance(None, None, lat, lon) returns
# float('inf'), which is > any radius, so every bid is excluded silently.
#
# Result: {"services": []} with HTTP 200 — caller has no idea why.
# Expected: 400 "Could not geocode address: <address>"
# ══════════════════════════════════════════════════════════════════════════════

def test_nearby_bad_address_silent_empty():
    res = R("/nearby: unrecognizable address → silent 200 [] instead of a useful error")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e3t1b_{ts}", "demand")

    # Post a real bid at a well-known address so there IS something to find
    bid_id = post_bid(buyer_tok,
                      "TEST-EDGE3: pizza delivery, downtown Denver",
                      location_type="physical",
                      address="Downtown Denver, CO")
    res.note(f"Bid posted at 'Downtown Denver, CO', bid_id={bid_id[:8]}…")

    # Verify it IS visible from a nearby address with known coords
    r_good = requests.post(f"{RSE_API}/nearby", verify=VERIFY,
                           json={"address": "Denver, CO", "radius": 50})
    good_services = r_good.json().get("services", [])
    our_bid_visible = any(s["bid_id"] == bid_id for s in good_services)
    res.note(f"Visible from 'Denver, CO': {our_bid_visible} ({len(good_services)} services)")

    # Now call /nearby from a completely nonsensical address
    garbage = "xzqwxzqw-8675309-nonexistent-place-zzzz"
    r_bad = requests.post(f"{RSE_API}/nearby", verify=VERIFY,
                          json={"address": garbage, "radius": 50})
    res.note(f"GET /nearby from '{garbage}' → HTTP {r_bad.status_code}")
    res.note(f"Response body: {r_bad.text[:100]}")

    cancel_bid(buyer_tok, bid_id)

    if r_bad.status_code == 200 and r_bad.json().get("services") == []:
        res.failed(
            "BUG CONFIRMED: unrecognizable address geocodes to (None, None). "
            "nearby_services() passes None lat/lon to calculate_distance() which "
            "returns inf for every bid → all excluded → empty 200 with no error. "
            "Caller cannot distinguish 'no services near you' from 'bad address'."
        )
    elif r_bad.status_code == 400:
        res.passed("Server correctly returned 400 for unrecognizable address")
    else:
        res.failed(f"Unexpected: HTTP {r_bad.status_code} body={r_bad.text[:80]}")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 2
# ── /exchange_data?location=X includes all remote bids regardless of X ─────────
#
# handlers.py get_exchange_data():
#   if location_filter and bid.get('address'):
#       if location_filter.lower() not in bid['address'].lower():
#           continue
#
# Remote bids have address=None, so bid.get('address') is falsy.
# The entire location filter is skipped for remote bids.
# A search for location='Denver' returns Denver physical bids AND every
# remote bid in the exchange.
# ══════════════════════════════════════════════════════════════════════════════

def test_exchange_data_location_filter_ignores_remote():
    res = R("/exchange_data?location=Denver includes all remote bids (location filter bypass)")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e3t2b_{ts}", "demand")

    # Post a remote bid with a distinctive service name
    sentinel = f"TEST-EDGE3-REMOTE-SENTINEL-{ts}"
    remote_bid = post_bid(buyer_tok, sentinel,
                          location_type="remote")  # no address
    res.note(f"Remote bid posted (no address), bid_id={remote_bid[:8]}…")

    # Search by location=Tokyo — should NOT return our remote Denver-unrelated bid
    r = requests.get(f"{RSE_API}/exchange_data?location=Tokyo", verify=VERIFY)
    bids = r.json().get("active_bids", [])
    our_bid = next((b for b in bids if b.get("bid_id") == remote_bid), None)
    res.note(f"GET /exchange_data?location=Tokyo → {len(bids)} bids total")
    res.note(f"Our remote bid (no address) found in Tokyo results: {our_bid is not None}")

    cancel_bid(buyer_tok, remote_bid)

    if our_bid is not None:
        res.failed(
            "BUG CONFIRMED: remote bid (address=None) appears in "
            "/exchange_data?location=Tokyo results. "
            "get_exchange_data() checks `if location_filter and bid.get('address'):` "
            "— when address is None, the inner check is skipped entirely. "
            "All remote bids pass every location filter, polluting location-specific queries."
        )
    else:
        res.passed("Remote bid correctly excluded from location-filtered results")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 3
# ── sign_job accepts non-integer ratings (floats), corrupting reputation ────────
#
# Docs: POST /sign_job { "job_id": str, "rating": int (1–5) }
#
# handlers.py sign_job():
#   if star_rating < 1 or star_rating > 5:
#       return {"error": "Rating must be 1-5"}, 400
#
# Python: 3.7 < 1 → False, 3.7 > 5 → False → passes the check.
# The float is then stored: counterparty_data['stars'] += 3.7
# Subsequent reputation calculations produce fractional averages that
# the docs promise are integer-based.  A user rated 3.7 and then 4
# gets stars=7.7, total_ratings=2, avg=3.85 — stored as float,
# never the clean integer math the docs imply.
# ══════════════════════════════════════════════════════════════════════════════

def test_sign_job_accepts_float_rating():
    res = R("sign_job: float rating (e.g. 3.7) accepted — docs say integer 1–5")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e3t3b_{ts}", "demand")
    prov_tok  = register_and_login(f"e3t3p_{ts}", "supply")

    bid_id = post_bid(buyer_tok,
                      "TEST-EDGE3: remote data analysis, spreadsheet cleanup")

    gr = grab_job(prov_tok, "Data analyst, spreadsheet, Excel, data cleaning")
    if gr.status_code != 200:
        cancel_bid(buyer_tok, bid_id)
        res.skipped(f"grab_job {gr.status_code}; skipping")
        res.show(); return res

    job = gr.json()
    if job.get("buyer_username") != f"e3t3b_{ts}":
        reject_job(prov_tok, job["job_id"])
        cancel_bid(buyer_tok, bid_id)
        res.skipped("Grabbed external bid; skipping")
        res.show(); return res

    job_id = job["job_id"]

    # Check provider's reputation before
    acct_before = requests.get(f"{RSE_API}/account",
                               headers=h(prov_tok), verify=VERIFY).json()
    stars_before = acct_before.get("stars", 0)
    ratings_before = acct_before.get("total_ratings", 0)
    res.note(f"Provider before: stars={stars_before}, total_ratings={ratings_before}")

    # Buyer signs with a float rating
    float_rating = 3.7
    r_buyer = requests.post(f"{RSE_API}/sign_job", headers=h(buyer_tok), verify=VERIFY,
                            json={"job_id": job_id, "rating": float_rating})
    res.note(f"sign_job(rating={float_rating}) by buyer → HTTP {r_buyer.status_code}  {r_buyer.text[:60]}")

    # Provider signs normally to complete the job
    r_prov = requests.post(f"{RSE_API}/sign_job", headers=h(prov_tok), verify=VERIFY,
                           json={"job_id": job_id, "rating": 5})
    res.note(f"sign_job(rating=5) by provider → HTTP {r_prov.status_code}")

    time.sleep(0.3)
    acct_after = requests.get(f"{RSE_API}/account",
                              headers=h(prov_tok), verify=VERIFY).json()
    stars_after = acct_after.get("stars", 0)
    ratings_after = acct_after.get("total_ratings", 0)
    res.note(f"Provider after:  stars={stars_after}, total_ratings={ratings_after}")
    res.note(f"Stars delta: {stars_after - stars_before} (expected integer, got {type(stars_after - stars_before).__name__})")

    if r_buyer.status_code == 200:
        # Check if non-integer stars were stored
        delta = stars_after - stars_before
        if isinstance(delta, float) and delta != int(delta):
            res.failed(
                f"BUG CONFIRMED: float rating {float_rating} accepted (HTTP 200) and stored. "
                f"Provider's stars increased by {delta} (a float). "
                "The docs promise integer 1–5 ratings. Float ratings corrupt the "
                "stars accumulator and produce fractional reputation scores. "
                "Any client sending 3.7 stars instead of 4 will silently succeed."
            )
        else:
            res.failed(
                f"BUG (partial): float rating {float_rating} accepted (HTTP 200) "
                f"but stars delta={delta} — may be rounded. Check stars field directly."
            )
    elif r_buyer.status_code == 400:
        res.passed(f"Server correctly rejected float rating {float_rating} with 400")
    else:
        res.failed(f"Unexpected HTTP {r_buyer.status_code}: {r_buyer.text[:80]}")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 4
# ── grab_job remote provider grabs hybrid bid with no distance filter ──────────
#
# handlers.py grab_job() distance-check gate (lines ~823-833):
#   if bid['location_type'] in ['physical', 'hybrid'] and \
#      location_type in ['physical', 'hybrid']:
#       # run distance check
#
# When provider uses location_type='remote', the second condition is False.
# The distance check is NEVER run for any bid, including hybrid bids that
# have a physical component.
#
# A provider in "Tokyo" claiming remote capabilities can grab a hybrid bid
# posted in Denver — the 10,000-km distance is never checked.
# ══════════════════════════════════════════════════════════════════════════════

def test_remote_provider_grabs_hybrid_bid_without_distance_check():
    res = R("grab_job: remote provider grabs hybrid bid with no distance filter applied")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e3t4b_{ts}", "demand")
    prov_tok  = register_and_login(f"e3t4p_{ts}", "supply")

    # Post a HYBRID bid at a known-coords Denver address
    hybrid_address = "Downtown Denver, CO"
    bid_id = post_bid(buyer_tok,
                      "TEST-EDGE3: hybrid consulting session, in-person kickoff then remote follow-ups",
                      location_type="hybrid",
                      address=hybrid_address)
    res.note(f"Hybrid bid at '{hybrid_address}', bid_id={bid_id[:8]}…")

    # Provider grabs as REMOTE with max_distance=1 mile (would exclude Denver
    # if distance filtering were applied to hybrid bids for remote providers)
    # A remote provider provides NO address — they claim to be everywhere.
    gr = grab_job(prov_tok,
                  "Business consultant, strategy, hybrid engagements, remote-first",
                  location_type="remote",   # no address — "I'm remote"
                  max_dist=1)              # 1-mile radius — meaningless for remote
    res.note(f"grab_job(remote, max_distance=1) → HTTP {gr.status_code}")

    if gr.status_code == 200:
        job = gr.json()
        if job.get("buyer_username") == f"e3t4b_{ts}":
            res.note(f"job_id={job['job_id'][:8]}…  bid location_type was: hybrid")
            res.failed(
                "BUG CONFIRMED: remote provider grabbed a HYBRID bid with no distance "
                "check (max_distance=1 mile was ignored). "
                "grab_job distance gate: "
                "`if bid_type in ['physical','hybrid'] and provider_type in ['physical','hybrid']` "
                "— when provider_type='remote', the gate short-circuits to False so the "
                "distance check never runs for ANY bid, including hybrid ones that have "
                "a mandatory physical component."
            )
            sign_and_cleanup(buyer_tok, prov_tok, job["job_id"])
        else:
            reject_job(prov_tok, job["job_id"])
            cancel_bid(buyer_tok, bid_id)
            res.skipped("Grabbed external bid; skipping")
    elif gr.status_code == 204:
        cancel_bid(buyer_tok, bid_id)
        res.skipped("No match returned (LLM or location filtered out); skipping")
    else:
        cancel_bid(buyer_tok, bid_id)
        res.failed(f"Unexpected HTTP {gr.status_code}: {gr.text[:80]}")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 5
# ── reject_job: rejecting provider can immediately re-grab the same bid ────────
#
# reject_job() restores the bid to the exchange pool (same bid_id after our fix).
# There is no "do not show to provider X" list.  The next grab_job call by the
# same provider will find the same bid again, match it, and create a new job —
# potentially trapping the provider in a reject→regrab loop forever.
#
# Docs (taxi/README.md): "reject_job — returns the ride to the exchange for
# another driver".  The word "another" implies exclusion of the rejector,
# but this is not enforced in the code.
# ══════════════════════════════════════════════════════════════════════════════

def test_reject_then_regrab_same_bid():
    res = R("reject_job: rejecting provider can immediately re-grab the same bid")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e3t5b_{ts}", "demand")
    prov_tok  = register_and_login(f"e3t5p_{ts}", "supply")

    bid_id = post_bid(buyer_tok,
                      "TEST-EDGE3: remote translation, English to Spanish, 10 pages")

    # First grab
    gr1 = grab_job(prov_tok, "Spanish translator, English to Spanish, document translation")
    if gr1.status_code != 200:
        cancel_bid(buyer_tok, bid_id)
        res.skipped(f"First grab returned {gr1.status_code}; skipping")
        res.show(); return res

    job1 = gr1.json()
    if job1.get("buyer_username") != f"e3t5b_{ts}":
        reject_job(prov_tok, job1["job_id"])
        cancel_bid(buyer_tok, bid_id)
        res.skipped("Grabbed external bid on first try; skipping")
        res.show(); return res

    job1_id = job1["job_id"]
    res.note(f"First grab OK, job_id={job1_id[:8]}…")

    # Provider rejects the job → bid goes back to pool
    rj = reject_job(prov_tok, job1_id, "edge test: intentional first rejection")
    res.note(f"reject_job → HTTP {rj.status_code}")

    # Immediately try to grab again with the same provider
    time.sleep(0.5)
    gr2 = grab_job(prov_tok, "Spanish translator, English to Spanish, document translation")
    res.note(f"Second grab (same provider) → HTTP {gr2.status_code}")

    if gr2.status_code == 200:
        job2 = gr2.json()
        if job2.get("buyer_username") == f"e3t5b_{ts}":
            same_bid = (job2.get("bid_id") == bid_id)
            res.note(f"job2 bid_id matches original: {same_bid}")
            res.note(f"job2_id={job2['job_id'][:8]}…")
            res.failed(
                "BUG CONFIRMED: the same provider immediately re-grabbed the bid they "
                f"just rejected (same bid_id: {same_bid}). reject_job() restores the bid "
                "to the pool with no record of the rejector. Any subsequent grab_job by "
                "the same provider finds it again. The docs say 'returned to the exchange "
                "for another driver' — but the rejecting driver is not excluded."
            )
            sign_and_cleanup(buyer_tok, prov_tok, job2["job_id"])
        else:
            # Got a different external bid
            reject_job(prov_tok, job2["job_id"])
            # Try to cancel the restored bid
            cancel_bid(buyer_tok, bid_id)
            res.skipped("Second grab returned an external bid; inconclusive")
    elif gr2.status_code == 204:
        # Another provider grabbed it first, or LLM timing
        cancel_bid(buyer_tok, bid_id)
        res.note("204 on second grab — bid may have been taken or LLM miss")
        res.skipped("204 on second grab; inconclusive (busy environment)")
    else:
        cancel_bid(buyer_tok, bid_id)
        res.failed(f"Unexpected HTTP {gr2.status_code}: {gr2.text[:80]}")

    res.show(); return res


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    if args.local:
        RSE_API = "http://localhost:5003"
        VERIFY  = False

    print("══════════════════════════════════════════════════════════")
    print("  RSE Edge Case Tests — Round 3")
    print(f"  Target: {RSE_API}")
    print("══════════════════════════════════════════════════════════")

    results = []
    for fn in [
        test_nearby_bad_address_silent_empty,
        test_exchange_data_location_filter_ignores_remote,
        test_sign_job_accepts_float_rating,
        test_remote_provider_grabs_hybrid_bid_without_distance_check,
        test_reject_then_regrab_same_bid,
    ]:
        try:
            results.append(fn())
        except Exception as e:
            print(f"\n  ERROR in {fn.__name__}: {e}")
        time.sleep(0.5)

    print("\n══════════════════════════════════════════════════════════")
    print("  Summary")
    print("══════════════════════════════════════════════════════════")
    icons = {PASS: "\033[92m✓\033[0m", FAIL: "\033[91m✗\033[0m",
             SKIP: "\033[93m—\033[0m"}
    for r in results:
        print(f"  {icons.get(r.outcome,'?')}  {r.name}")
    print(f"\n  {sum(1 for r in results if r.outcome==PASS)} passed  "
          f"{sum(1 for r in results if r.outcome==FAIL)} failed  "
          f"{sum(1 for r in results if r.outcome==SKIP)} skipped  ({len(results)} total)")

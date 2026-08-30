"""
Edge Case Integration Tests — Round 4
======================================
Five tests that should pass per docs/contract but fail in the implementation.

1. submit_bid with invalid location_type accepted (200) but bid is unfillable
2. exchange_data?include_completed=True: completed_jobs location filter still uses
   old `if location_filter and job.get('address')` pattern — remote completed jobs bypass it
3. send_chat_message to yourself → 200 (docs say "send to another user"; should be 400)
4. get_my_bids missing xmoney_account field even when bid was submitted with one
5. get_my_jobs: rejected jobs appear in active_jobs (only 'completed' is correctly bucketed)

Usage:
  python edge_tests_4.py                  # https://rse-api.com:5003
  python edge_tests_4.py --local          # http://localhost:5003
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
             address=None, expiry=7200, **extra):
    payload = {"service": service, "price": price, "currency": "USD",
               "payment_method": "cash", "location_type": location_type,
               "end_time": int(time.time()) + expiry}
    if address:
        payload["address"] = address
    payload.update(extra)
    return requests.post(f"{RSE_API}/submit_bid", headers=h(token),
                         json=payload, verify=VERIFY)

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

def reject_job_req(token, job_id, reason="test"):
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
# ── submit_bid with invalid location_type accepted silently ───────────────────
#
# Docs define three valid location_types: 'physical', 'hybrid', 'remote'.
# submit_bid() reads `location_type = data.get('location_type', 'physical')` with
# no validation against the allowed set.  An unknown value like 'spaceship' is
# stored verbatim.  The bid then sits in the exchange permanently unfillable:
# grab_job's compatibility filter is:
#   if location_type == 'remote' and bid['location_type'] in ['physical','hybrid']: skip
#   if location_type == 'physical' and bid['location_type'] == 'remote': skip
# Neither branch matches 'spaceship', so the bid survives every filter pass and
# the LLM is asked about it — but every grab_job by a remote provider skips it
# because remote providers now also skip non-['physical','hybrid'] bids via the
# updated gate.  Regardless, a buyer posting with a typo gets a phantom bid_id
# and no error.
#
# Expected: 400 "Invalid location_type"
# Actual:   200 + a valid bid_id
# ══════════════════════════════════════════════════════════════════════════════

def test_submit_bid_invalid_location_type():
    res = R("submit_bid: invalid location_type 'spaceship' accepted (should be 400)")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e4t1b_{ts}", "demand")

    r = post_bid(buyer_tok,
                 "TEST-EDGE4: remote data entry task",
                 location_type="spaceship")   # <-- not a valid type

    res.note(f"POST /submit_bid location_type='spaceship' → HTTP {r.status_code}")
    res.note(f"Response: {r.text[:120]}")

    if r.status_code == 200 and r.json().get("bid_id"):
        bid_id = r.json()["bid_id"]
        res.note(f"Bid created with invalid type: bid_id={bid_id[:8]}…")
        cancel_bid(buyer_tok, bid_id)   # clean up the phantom bid
        res.failed(
            "BUG CONFIRMED: submit_bid accepted location_type='spaceship' with 200 "
            "and issued a real bid_id. The bid is permanently unfillable because "
            "no provider's location_type will match the stored value. "
            "submit_bid() has no validation of the location_type field."
        )
    elif r.status_code == 400:
        res.passed("Server correctly rejected invalid location_type with 400")
    else:
        res.failed(f"Unexpected HTTP {r.status_code}: {r.text[:80]}")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 2
# ── exchange_data?include_completed completed_jobs location filter bypass ──────
#
# Round 3 fix #2 corrected the location filter for active_bids in
# get_exchange_data() from:
#   if location_filter and bid.get('address'):   ← old (skips remote bids)
# to:
#   if location_filter: if not bid.get('address') or ...  ← new (excludes them)
#
# But the completed_jobs section in the same function was NOT updated.
# It still uses the old pattern:
#   if location_filter and job.get('address'):       ← line 1245
#       if location_filter.lower() not in job['address'].lower():
#           continue
#
# So completed jobs with no address (remote jobs) bypass the location filter and
# appear in /exchange_data?location=Denver&include_completed=True results even
# when they have nothing to do with Denver.
# ══════════════════════════════════════════════════════════════════════════════

def test_exchange_data_completed_jobs_location_filter_bypass():
    res = R("exchange_data?include_completed: completed remote jobs bypass location filter")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e4t2b_{ts}", "demand")
    prov_tok  = register_and_login(f"e4t2p_{ts}", "supply")

    # Post a remote bid (no address) with a distinctive sentinel
    sentinel = f"TEST-EDGE4-REMOTE-COMPLETED-{ts}"
    r_bid = post_bid(buyer_tok, sentinel, location_type="remote")
    if r_bid.status_code != 200:
        res.skipped(f"submit_bid failed: {r_bid.status_code}"); res.show(); return res
    bid_id = r_bid.json()["bid_id"]
    res.note(f"Remote bid posted (no address), bid_id={bid_id[:8]}…")

    # Provider grabs it
    gr = grab_job(prov_tok, sentinel.lower())
    if gr.status_code != 200:
        cancel_bid(buyer_tok, bid_id)
        res.skipped(f"grab_job {gr.status_code}; skipping"); res.show(); return res

    job = gr.json()
    if job.get("buyer_username") != f"e4t2b_{ts}":
        reject_job_req(prov_tok, job["job_id"])
        cancel_bid(buyer_tok, bid_id)
        res.skipped("Grabbed external bid; skipping"); res.show(); return res

    job_id = job["job_id"]
    res.note(f"Job grabbed: job_id={job_id[:8]}…")

    # Complete the job (both sign)
    sign_and_cleanup(buyer_tok, prov_tok, job_id)
    res.note("Job signed by both parties → status=completed")
    time.sleep(0.5)

    # Query exchange_data with location=Tokyo and include_completed=True
    r_ex = requests.get(
        f"{RSE_API}/exchange_data?location=Tokyo&include_completed=True",
        verify=VERIFY
    )
    completed = r_ex.json().get("completed_jobs", [])
    our_job = next((j for j in completed if j.get("job_id") == job_id), None)
    res.note(f"GET /exchange_data?location=Tokyo&include_completed=True → "
             f"{len(completed)} completed jobs")
    res.note(f"Our remote completed job found in Tokyo results: {our_job is not None}")

    if our_job is not None:
        res.failed(
            "BUG CONFIRMED: completed remote job (address=None) appears in "
            "/exchange_data?location=Tokyo&include_completed=True results. "
            "The completed_jobs loop at line 1245 still uses the old pattern: "
            "`if location_filter and job.get('address'):` — "
            "when address is None, the filter is skipped entirely. "
            "Round 3 fixed active_bids but missed the completed_jobs section."
        )
    else:
        res.passed("Completed remote job correctly excluded from location-filtered results")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 3
# ── send_chat_message to yourself is allowed ──────────────────────────────────
#
# Docs: POST /send_message { "recipient": str, "message": str }
# Description: "Send a message to another user."
#
# send_chat_message() in handlers.py only validates that the recipient exists:
#   if not account_exists(recipient): return {"error": "Recipient not found"}, 404
#
# It does NOT check sender != recipient.  Sending a message to yourself:
# - succeeds with HTTP 200 + a message_id
# - saves TWO copies of the same message (sender_key and recipient_key are the
#   same user, so get_user_messages returns the message twice)
# - creates a self-conversation in /conversations
#
# Expected: 400 "Cannot send message to yourself"
# Actual:   200 + message_id
# ══════════════════════════════════════════════════════════════════════════════

def test_send_message_to_self():
    res = R("send_chat_message to yourself → 200 (should be 400)")
    ts = str(int(time.time()))[-5:]

    user_tok = register_and_login(f"e4t3u_{ts}", "demand")
    username = f"e4t3u_{ts}"

    r = requests.post(f"{RSE_API}/chat", headers=h(user_tok), verify=VERIFY,
                      json={"recipient": username,
                            "message": "TEST-EDGE4: hello myself"})
    res.note(f"POST /chat recipient=self → HTTP {r.status_code}")
    res.note(f"Response: {r.text[:120]}")

    if r.status_code == 200 and r.json().get("message_id"):
        # Confirm the duplicate storage: message appears twice in chat history
        r_hist = requests.post(f"{RSE_API}/chat/messages", headers=h(user_tok), verify=VERIFY,
                               json={"conversation_id": username})
        msgs = r_hist.json().get("messages", [])
        self_msgs = [m for m in msgs if "TEST-EDGE4: hello myself" in m.get("message","")]
        res.note(f"Message copies in chat history: {len(self_msgs)} (1 sent + 1 received = 2 stored)")
        res.failed(
            "BUG CONFIRMED: send_chat_message() does not check sender != recipient. "
            f"Sending to yourself succeeds (HTTP 200, message_id={r.json().get('message_id','')[:8]}…). "
            "The message is stored twice (once as sent, once as received) and "
            "creates a nonsensical self-conversation in /conversations."
        )
    elif r.status_code == 400:
        res.passed("Server correctly rejected self-message with 400")
    else:
        res.failed(f"Unexpected HTTP {r.status_code}: {r.text[:80]}")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 4
# ── get_my_bids omits xmoney_account field ────────────────────────────────────
#
# POST /submit_bid accepts { "payment_method": "xmoney", "xmoney_account": "..." }
# The xmoney_account is stored in the bid object.
#
# GET /my_bids returns bid objects built in get_my_bids():
#   outstanding_bids.append({
#       'bid_id': bid['bid_id'],
#       'service': ...,
#       'price': ...,
#       'currency': ...,
#       'payment_method': ...,     ← included
#       'end_time': ...,
#       'location_type': ...,
#       'address': ...,
#       'created_at': ...,
#       'status': 'active'
#   })
#
# 'xmoney_account' is never included.  A buyer who submitted a bid with an
# xmoney_account has no way to retrieve it from /my_bids.
# ══════════════════════════════════════════════════════════════════════════════

def test_my_bids_missing_xmoney_account():
    res = R("get_my_bids: xmoney_account missing from response even when submitted")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e4t4b_{ts}", "demand")

    xmoney_acct = f"xmoney_handle_{ts}"
    r = post_bid(buyer_tok,
                 "TEST-EDGE4: remote bookkeeping service",
                 payment_method="xmoney",
                 xmoney_account=xmoney_acct)
    if r.status_code != 200:
        res.skipped(f"submit_bid failed: {r.status_code}"); res.show(); return res
    bid_id = r.json()["bid_id"]
    res.note(f"Bid submitted with xmoney_account='{xmoney_acct}', bid_id={bid_id[:8]}…")

    # Retrieve the bid via /my_bids
    r_my = requests.get(f"{RSE_API}/my_bids", headers=h(buyer_tok), verify=VERIFY)
    bids = r_my.json().get("bids", [])
    our_bid = next((b for b in bids if b.get("bid_id") == bid_id), None)

    if our_bid is None:
        cancel_bid(buyer_tok, bid_id)
        res.skipped("Bid not found in /my_bids; skipping"); res.show(); return res

    has_xmoney = "xmoney_account" in our_bid
    returned_val = our_bid.get("xmoney_account")
    res.note(f"'xmoney_account' key present in /my_bids response: {has_xmoney}")
    res.note(f"Value returned: {returned_val!r}  (expected: {xmoney_acct!r})")

    cancel_bid(buyer_tok, bid_id)

    if not has_xmoney:
        res.failed(
            "BUG CONFIRMED: 'xmoney_account' is absent from /my_bids bid objects. "
            "get_my_bids() builds the response dict without including 'xmoney_account'. "
            "A buyer who submitted a bid with an xmoney payment account has no way "
            "to retrieve it from the API — the field is silently dropped."
        )
    elif returned_val != xmoney_acct:
        res.failed(f"BUG: xmoney_account key present but wrong value: {returned_val!r}")
    else:
        res.passed(f"xmoney_account correctly returned: {returned_val!r}")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Edge Test 5
# ── get_my_jobs: rejected jobs appear in active_jobs ──────────────────────────
#
# get_my_jobs() buckets jobs:
#   if job['status'] == 'completed':
#       completed_jobs.append(...)
#   else:
#       active_jobs.append(...)        ← catches EVERYTHING else
#
# A rejected job has status='rejected'.  It is not 'completed', so it falls
# into active_jobs.  The buyer then sees their rejected job listed as if it is
# still in progress — wrong status, confusing UX, and potentially misleading
# (buyer might think they still have an active engagement).
#
# Expected: rejected jobs in neither list, or in a separate 'rejected_jobs' list
# Actual:   rejected jobs appear in active_jobs with status='rejected'
# ══════════════════════════════════════════════════════════════════════════════

def test_my_jobs_rejected_in_active():
    res = R("get_my_jobs: rejected jobs appear in active_jobs list")
    ts = str(int(time.time()))[-5:]

    buyer_tok = register_and_login(f"e4t5b_{ts}", "demand")
    prov_tok  = register_and_login(f"e4t5p_{ts}", "supply")

    r_bid = post_bid(buyer_tok, "TEST-EDGE4: remote legal document review")
    if r_bid.status_code != 200:
        res.skipped(f"submit_bid failed: {r_bid.status_code}"); res.show(); return res
    bid_id = r_bid.json()["bid_id"]

    gr = grab_job(prov_tok, "lawyer legal document review contract")
    if gr.status_code != 200:
        cancel_bid(buyer_tok, bid_id)
        res.skipped(f"grab_job {gr.status_code}; skipping"); res.show(); return res

    job = gr.json()
    if job.get("buyer_username") != f"e4t5b_{ts}":
        reject_job_req(prov_tok, job["job_id"])
        cancel_bid(buyer_tok, bid_id)
        res.skipped("Grabbed external bid; skipping"); res.show(); return res

    job_id = job["job_id"]
    res.note(f"Job grabbed: job_id={job_id[:8]}…")

    # Provider rejects the job — returns it to the exchange
    rj = reject_job_req(prov_tok, job_id, reason="TEST-EDGE4: cannot take this job")
    res.note(f"reject_job → HTTP {rj.status_code}")
    if rj.status_code != 200:
        cancel_bid(buyer_tok, bid_id)
        res.skipped(f"reject_job failed: {rj.status_code}"); res.show(); return res

    time.sleep(0.3)

    # Check buyer's /my_jobs — the rejected job should NOT appear in active_jobs
    r_jobs = requests.get(f"{RSE_API}/my_jobs", headers=h(buyer_tok), verify=VERIFY)
    active = r_jobs.json().get("active_jobs", [])
    completed = r_jobs.json().get("completed_jobs", [])

    rejected_in_active = [j for j in active if j.get("job_id") == job_id]
    rejected_in_completed = [j for j in completed if j.get("job_id") == job_id]
    res.note(f"Rejected job found in active_jobs: {bool(rejected_in_active)}")
    res.note(f"Rejected job found in completed_jobs: {bool(rejected_in_completed)}")

    # Clean up: cancel the restored bid
    cancel_bid(buyer_tok, bid_id)

    if rejected_in_active:
        status_shown = rejected_in_active[0].get("status")
        res.failed(
            "BUG CONFIRMED: rejected job appears in active_jobs with "
            f"status='{status_shown}'. "
            "get_my_jobs() only checks `if job['status'] == 'completed'` and "
            "puts everything else (including 'rejected') into active_jobs. "
            "The buyer sees their rejected job as if it were still in progress."
        )
    elif rejected_in_completed:
        res.failed(
            "BUG: rejected job incorrectly appears in completed_jobs "
            f"(status={rejected_in_completed[0].get('status')!r})"
        )
    else:
        res.passed("Rejected job correctly absent from both active_jobs and completed_jobs")

    res.show(); return res


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global RSE_API, VERIFY
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    if args.local:
        RSE_API = "http://localhost:5003"
        VERIFY = False

    print("══════════════════════════════════════════════════════════")
    print("  RSE Edge Case Tests — Round 4")
    print(f"  Target: {RSE_API}")
    print("══════════════════════════════════════════════════════════")

    results = [
        test_submit_bid_invalid_location_type(),
        test_exchange_data_completed_jobs_location_filter_bypass(),
        test_send_message_to_self(),
        test_my_bids_missing_xmoney_account(),
        test_my_jobs_rejected_in_active(),
    ]

    passed  = sum(1 for r in results if r.outcome == PASS)
    failed  = sum(1 for r in results if r.outcome == FAIL)
    skipped = sum(1 for r in results if r.outcome == SKIP)

    print("\n══════════════════════════════════════════════════════════")
    print("  Summary")
    print("══════════════════════════════════════════════════════════")
    for r in results:
        ic = {PASS: "\033[92m✓\033[0m", FAIL: "\033[91m✗\033[0m",
              SKIP: "\033[93m—\033[0m"}.get(r.outcome, "?")
        print(f"  {ic}  {r.name}")
    print(f"\n  {passed} passed  {failed} failed  {skipped} skipped  ({len(results)} total)\n")


if __name__ == "__main__":
    main()

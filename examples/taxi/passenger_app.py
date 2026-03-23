#!/usr/bin/env python3
"""
Demand-side taxi integration — The Services Exchange
=====================================================
This reference app shows how a passenger-facing app (or a mobility platform
acting on a passenger's behalf) publishes a ride request to the exchange and
waits for a driver to accept it.

The exchange is a general-purpose service marketplace.  From the exchange's
point of view a "ride request" is just a bid whose 'service' field happens to
describe a taxi trip.  No taxi-specific schema is required — the LLM matching
engine on the supply side reads the natural-language description and decides
whether each driver can fulfill it.

Quick-start
-----------
1.  pip install requests
2.  Set RSE_USERNAME / RSE_PASSWORD env vars (or edit CREDENTIALS below).
3.  python passenger_app.py

Full lifecycle demonstrated here:
    register (first run only) → login → post bid → poll for driver →
    job accepted → sign & rate driver
"""

import os
import sys
import time
import requests

# ── Configuration ─────────────────────────────────────────────────────────────

RSE_API     = "https://rse-api.com:5003"   # swap to http://localhost:5003 for local dev
VERIFY_SSL  = True                          # set False if using a self-signed cert locally

# Credentials for the passenger account.  In production these come from your
# user-auth system; here we read from env vars or fall back to hardcoded values
# for the demo.
CREDENTIALS = {
    "username": os.environ.get("RSE_USERNAME", "demo_passenger"),
    "password": os.environ.get("RSE_PASSWORD", "ChangeMe123!"),
}


# ── Step 0: Account setup (run once per user) ─────────────────────────────────

def register(username: str, password: str) -> bool:
    """
    Create a demand-side account on the exchange.
    Only needed once.  Returns True on success, False if the username is taken
    (in which case just call login() instead).
    """
    r = requests.post(f"{RSE_API}/register", verify=VERIFY_SSL, json={
        "username": username,
        "password": password,
        "user_type": "demand",   # passengers are on the demand side
    })
    if r.status_code == 201:
        print(f"[RSE] Account created: {username}")
        return True
    if r.status_code == 409:
        print(f"[RSE] Account already exists: {username}")
        return False
    r.raise_for_status()


def login(username: str, password: str) -> str:
    """
    Authenticate and return a bearer token.
    Tokens are valid for 24 hours.  Cache and reuse; refresh on 401.
    """
    r = requests.post(f"{RSE_API}/login", verify=VERIFY_SSL, json={
        "username": username,
        "password": password,
    })
    r.raise_for_status()
    token = r.json()["access_token"]
    print(f"[RSE] Logged in as {username}")
    return token


# ── Step 1: Post a ride request as a bid ──────────────────────────────────────

def post_ride_request(
    token: str,
    pickup: str,
    dropoff: str,
    passengers: int,
    fare_usd: float,
    notes: str = "",
    expiry_seconds: int = 300,   # how long the request stays open (5 min default)
) -> str:
    """
    Translate a passenger's ride request into an exchange bid and return the bid_id.

    Key design decisions
    --------------------
    service
        A plain-English description of the trip.  The exchange's LLM matching
        engine reads this and compares it against each driver's stated
        capabilities.  You don't need to conform to any schema — write whatever
        a driver would need to know to decide whether to take the job.

    price
        The fare the passenger is offering.  Drivers on the exchange will see
        this when deciding whether to grab the job.  Set it to the fare your
        pricing engine computes; the exchange sorts available drivers by
        reputation alignment and then price.

    location_type = "physical"
        Tells the exchange this is an in-person service so it can filter
        drivers by proximity.

    start_address / end_address
        Optional structured fields the exchange stores alongside the bid so
        the matched driver can navigate without parsing the service string.
    """
    service_description = (
        f"Taxi ride: {pickup} → {dropoff}.  "
        f"{passengers} passenger{'s' if passengers != 1 else ''}.  "
        + (f"Notes: {notes}  " if notes else "")
        + "Licensed taxi or rideshare vehicle required."
    )

    payload = {
        "service":        service_description,
        "price":          fare_usd,
        "currency":       "USD",
        "payment_method": "cash",            # or "xmoney", "paypal", etc.
        "location_type":  "physical",
        "start_address":  pickup,            # pickup coordinates (stored for driver)
        "end_address":    dropoff,           # dropoff coordinates
        "end_time":       int(time.time()) + expiry_seconds,
    }

    r = requests.post(
        f"{RSE_API}/submit_bid",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    bid_id = r.json()["bid_id"]
    print(f"[RSE] Ride request posted (bid_id={bid_id[:8]}…)  "
          f"${fare_usd:.2f} | {pickup} → {dropoff}")
    return bid_id


# ── Step 2: Poll until a driver accepts ───────────────────────────────────────

def wait_for_driver(token: str, bid_id: str, timeout_seconds: int = 270) -> dict | None:
    """
    Polls the exchange until a driver grabs the bid.

    When a driver calls /grab_job the exchange atomically:
      • removes the bid  →  it disappears from /my_bids
      • creates a job record  →  it appears in /my_jobs

    So we watch for the bid to vanish from /my_bids and then fetch the job
    from /my_jobs.  Returns the job dict on success, None on timeout.
    """
    print(f"[RSE] Waiting for a driver (timeout={timeout_seconds}s) …")
    deadline = time.time() + timeout_seconds
    poll_interval = 5   # seconds between polls — be polite to the API

    while time.time() < deadline:
        # Check whether the bid still exists
        r = requests.get(
            f"{RSE_API}/my_bids",
            headers={"Authorization": f"Bearer {token}"},
            verify=VERIFY_SSL,
        )
        r.raise_for_status()
        active_bids = r.json().get("bids", [])
        still_open = any(b["bid_id"] == bid_id for b in active_bids)

        if not still_open:
            # Bid was consumed — a driver grabbed it.  Find the resulting job.
            job = _find_job_for_bid(token, bid_id)
            if job:
                print(f"[RSE] Driver accepted!  job_id={job['job_id'][:8]}…  "
                      f"driver={job['provider_username']}")
                return job
            # Edge case: bid cancelled or expired between polls.  Keep waiting briefly.

        time.sleep(poll_interval)

    print("[RSE] Timed out waiting for a driver.")
    return None


def _find_job_for_bid(token: str, bid_id: str) -> dict | None:
    """Return the job that was created from this bid, if it exists."""
    r = requests.get(
        f"{RSE_API}/my_jobs",
        headers={"Authorization": f"Bearer {token}"},
        verify=VERIFY_SSL,
    )
    if r.status_code != 200:
        return None
    data = r.json()
    for job in data.get("active_jobs", []):
        if job.get("bid_id") == bid_id:
            return job
    return None


# ── Step 3: Cancel if no driver found ─────────────────────────────────────────

def cancel_ride_request(token: str, bid_id: str) -> None:
    """Cancel an open bid (e.g. passenger changed their mind or no driver found)."""
    r = requests.post(
        f"{RSE_API}/cancel_bid",
        headers={"Authorization": f"Bearer {token}"},
        json={"bid_id": bid_id},
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        print(f"[RSE] Bid {bid_id[:8]}… cancelled.")
    else:
        print(f"[RSE] Cancel returned {r.status_code}: {r.text}")


# ── Step 4: Rate the driver after the ride ────────────────────────────────────

def complete_ride(token: str, job_id: str, driver_rating: int) -> None:
    """
    Passenger signs the job and rates the driver (1–5 stars).

    The job is marked completed once BOTH the passenger and driver have signed.
    The exchange uses ratings to build reputation scores that influence future
    matching (higher-reputation drivers are prioritised for higher-reputation
    passengers).
    """
    assert 1 <= driver_rating <= 5, "Rating must be 1–5"
    r = requests.post(
        f"{RSE_API}/sign_job",
        headers={"Authorization": f"Bearer {token}"},
        json={"job_id": job_id, "rating": driver_rating},
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    print(f"[RSE] Ride signed.  Driver rated {driver_rating}/5.")


# ── Demo: end-to-end passenger flow ───────────────────────────────────────────

def main():
    username = CREDENTIALS["username"]
    password = CREDENTIALS["password"]

    # ── Account setup (idempotent — safe to call every run) ───────────────────
    register(username, password)   # no-op if account already exists
    token = login(username, password)

    # ── Book a ride ───────────────────────────────────────────────────────────
    # In a real app these values come from the passenger's UI / GPS.
    bid_id = post_ride_request(
        token      = token,
        pickup     = "355 Main Street, San Francisco, CA 94105",
        dropoff    = "SFO International Terminal, San Francisco, CA 94128",
        passengers = 2,
        fare_usd   = 45.00,
        notes      = "Two large bags.  Quiet ride preferred.",
        expiry_seconds = 300,   # cancel automatically after 5 min if no driver
    )

    # ── Wait for a driver ─────────────────────────────────────────────────────
    job = wait_for_driver(token, bid_id, timeout_seconds=270)

    if job is None:
        # Nobody accepted in time — cancel and retry / surge-price / etc.
        cancel_ride_request(token, bid_id)
        print("No driver found.  Consider raising the fare or retrying.")
        sys.exit(1)

    # ── Ride is happening ─────────────────────────────────────────────────────
    print(f"\nDriver details:")
    print(f"  Username    : {job['provider_username']}")
    print(f"  Reputation  : {job['provider_reputation']:.1f}/5.0")
    print(f"  Pickup at   : {job.get('start_address', job.get('address', 'see job record'))}")
    print(f"  Drop-off at : {job.get('end_address', 'N/A')}")
    print(f"  Fare        : {job['currency']} {job['price']:.2f}")
    print(f"  Payment     : {job['payment_method']}")
    print()

    # In production: push job details to the passenger's phone, track ETA, etc.
    # Here we just simulate the ride completing.
    print("(Simulating ride…)")
    time.sleep(3)

    # ── Rate the driver ───────────────────────────────────────────────────────
    complete_ride(token, job["job_id"], driver_rating=5)
    print("Ride complete.")


if __name__ == "__main__":
    main()

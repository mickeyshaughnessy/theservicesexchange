#!/usr/bin/env python3
"""
Supply-side taxi integration — The Services Exchange
=====================================================
This reference app shows how a taxi company or autonomous-vehicle fleet
(Waymo, Tesla, a traditional cab company, etc.) connects to the exchange as a
supply-side partner and monetises spare vehicle capacity.

Concept
-------
Your fleet has vehicles that are idle or between jobs.  Instead of waiting
for rides to come in through your own app, you broadcast availability to the
exchange and let its matching engine find passengers who need a ride right now.

From the exchange's point of view your vehicle is a "service provider" whose
capabilities happen to describe a taxi or rideshare operation.  You call
/grab_job on a polling loop; when a matching passenger bid exists the exchange
atomically assigns it to you and returns the full job record, including the
pickup address and fare.

No taxi-specific schema is required on either side — the LLM matching engine
reads plain-English capability descriptions and decides whether your vehicle
can fulfill each passenger's request.

Quick-start
-----------
1.  pip install requests
2.  Set RSE_USERNAME / RSE_PASSWORD env vars (or edit CREDENTIALS below).
3.  Edit VEHICLE_CAPABILITIES and CURRENT_LOCATION for your fleet.
4.  python driver_app.py

Full lifecycle demonstrated here:
    register (first run only) → login → poll for rides → job accepted →
    optionally reject → sign & rate passenger
"""

import os
import sys
import time
import requests

# ── Configuration ─────────────────────────────────────────────────────────────

RSE_API     = "https://rse-api.com:5003"   # swap to http://localhost:5003 for local dev
VERIFY_SSL  = True                          # set False if using a self-signed cert locally

# Credentials for the driver / fleet account on the exchange.
CREDENTIALS = {
    "username": os.environ.get("RSE_USERNAME", "acme_taxi_fleet"),
    "password": os.environ.get("RSE_PASSWORD", "ChangeMe123!"),
}

# ── What your vehicle(s) can do ───────────────────────────────────────────────
#
# Write a plain-English description of your vehicle capabilities.  This string
# is sent to the exchange's LLM matching engine, which compares it against
# every open passenger bid to decide whether you're a fit.
#
# Tips:
#   • Include vehicle type, licensing, and any special capabilities.
#   • Mention service areas if you only cover certain zones.
#   • Be honest about capacity (passengers, luggage).
#   • You can update this dynamically per vehicle if you have a mixed fleet.
#
VEHICLE_CAPABILITIES = (
    "Licensed taxi and rideshare driver.  Insured, background-checked. "
    "Comfortable 4-door sedan, up to 4 passengers, trunk space for 3 large bags. "
    "Serving greater San Francisco Bay Area.  Available for airport runs, "
    "point-to-point trips, and hourly hire."
)

# Current GPS position of the vehicle (or dispatch hub for a fleet).
# The exchange uses this to filter bids by distance before running LLM matching,
# so only nearby passengers are considered.
CURRENT_LOCATION = {
    "address":      "Market Street & 4th Street, San Francisco, CA 94103",
    "max_distance": 20,   # miles — only consider passengers within this radius
}

# How often to check the exchange for new rides (seconds).
# Don't poll faster than 15 s; the exchange rate-limits /grab_job per seat.
POLL_INTERVAL = 20


# ── Step 0: Account setup (run once per driver / fleet account) ───────────────

def register(username: str, password: str) -> bool:
    """
    Create a supply-side account on the exchange.
    Only needed once.  Returns True on success, False if the account exists.
    """
    r = requests.post(f"{RSE_API}/register", verify=VERIFY_SSL, json={
        "username": username,
        "password": password,
        "user_type": "supply",   # drivers/fleets are on the supply side
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


def set_wallet(token: str, wallet_address: str) -> None:
    """
    Link an Ethereum wallet address to the account.

    The exchange uses ERC-721 RSE Seat NFTs (on Base L2) to gate supply-side
    access.  Partners are issued a seat NFT; link the holding wallet once with
    this call.  If seat verification is currently disabled on the exchange this
    call is a no-op but it is still good practice — it ensures your integration
    keeps working when verification is turned on.

    Contract: 0x151fEB62F0D3085617a086130cc67f7f18Ce33CE (Base mainnet)
    """
    r = requests.post(
        f"{RSE_API}/set_wallet",
        headers={"Authorization": f"Bearer {token}"},
        json={"wallet_address": wallet_address},
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        print(f"[RSE] Wallet linked: {wallet_address[:10]}…")
    else:
        print(f"[RSE] set_wallet returned {r.status_code}: {r.text} (non-fatal)")


# ── Step 1: Poll the exchange for matching rides ───────────────────────────────

def grab_next_ride(token: str) -> dict | None:
    """
    Ask the exchange for the best available passenger bid that matches this
    vehicle's capabilities and location.

    The exchange runs a four-step selection algorithm:
      1. Location filter  — bids within max_distance of the vehicle
      2. Capability match — LLM decides whether the vehicle fits the trip
      3. Reputation sort  — prefer passengers whose reputation matches yours
      4. Price sort       — within a reputation tier, highest fare first

    Returns the job dict (200 OK) or None if there are no matching bids (204).
    Raises on unexpected errors.

    Important: when this call returns a job, the bid is atomically removed
    from the exchange.  No other driver will see it.  You must either complete
    the job (sign_job) or reject it (reject_job) — don't just discard it.
    """
    payload = {
        "capabilities": VEHICLE_CAPABILITIES,
        "location_type": "physical",
        "address":       CURRENT_LOCATION["address"],
        "max_distance":  CURRENT_LOCATION["max_distance"],
    }

    r = requests.post(
        f"{RSE_API}/grab_job",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        verify=VERIFY_SSL,
    )

    if r.status_code == 200:
        return r.json()          # job assigned
    if r.status_code == 204:
        return None              # no matching rides right now
    if r.status_code == 403:
        # Seat verification failed (wallet not linked or NFT missing).
        # See set_wallet() above.
        raise PermissionError(f"Seat verification failed: {r.json().get('error')}")

    r.raise_for_status()


# ── Step 2: Inspect the job and decide whether to take it ─────────────────────

def should_accept(job: dict) -> bool:
    """
    Implement your accept/reject logic here.

    The job dict contains everything you need:
      job["service"]             — passenger's full ride description
      job["price"]               — offered fare in job["currency"]
      job["start_address"]       — pickup address (may be in 'address' for older bids)
      job["end_address"]         — dropoff address
      job["buyer_reputation"]    — passenger reputation score (0.0–5.0; 2.5 = new user)
      job["location_type"]       — "physical" for in-person rides
      job["payment_method"]      — "cash", "xmoney", "paypal", etc.

    Examples of reasons to reject:
      • Pickup is too far from current position after all
      • Fare is below your minimum acceptable
      • Passenger reputation is below your threshold
      • Dropoff is in a zone you don't serve
    """
    # Example policy: minimum $10 fare, passenger reputation ≥ 1.5
    fare = job.get("price", 0)
    passenger_rep = job.get("buyer_reputation", 2.5)

    if fare < 10.00:
        print(f"  [policy] Fare ${fare:.2f} below minimum — rejecting.")
        return False
    if passenger_rep < 1.5:
        print(f"  [policy] Passenger reputation {passenger_rep:.1f} too low — rejecting.")
        return False
    return True


# ── Step 3: Reject a job (puts it back on the exchange) ───────────────────────

def reject_ride(token: str, job_id: str, reason: str = "Vehicle unavailable") -> None:
    """
    Reject a job.  The exchange restores it as a new bid so another driver
    can pick it up.  Use this if your vehicle becomes unavailable after
    grabbing the job (breakdown, driver change of shift, etc.).
    """
    r = requests.post(
        f"{RSE_API}/reject_job",
        headers={"Authorization": f"Bearer {token}"},
        json={"job_id": job_id, "reason": reason},
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        print(f"[RSE] Job {job_id[:8]}… rejected and returned to exchange.")
    else:
        print(f"[RSE] reject_job returned {r.status_code}: {r.text}")


# ── Step 4: Complete the ride and rate the passenger ──────────────────────────

def complete_ride(token: str, job_id: str, passenger_rating: int) -> None:
    """
    Sign the completed job and rate the passenger (1–5 stars).

    The job is marked fully complete once BOTH sides have signed.  The
    exchange uses ratings to build reputation scores used in future matching.

    Call this after you have dropped the passenger off and collected payment.
    In a fleet integration you would call this automatically when the driver
    taps "End ride" in your in-vehicle UI.
    """
    assert 1 <= passenger_rating <= 5, "Rating must be 1–5"
    r = requests.post(
        f"{RSE_API}/sign_job",
        headers={"Authorization": f"Bearer {token}"},
        json={"job_id": job_id, "rating": passenger_rating},
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    print(f"[RSE] Ride signed.  Passenger rated {passenger_rating}/5.")


# ── Demo: polling dispatch loop ───────────────────────────────────────────────
#
# In production this loop runs in the background for each available vehicle.
# When a job is returned you hand it off to your dispatch / navigation system.
# The loop exits after handling one ride for clarity; remove the `break` to
# run continuously.

def dispatch_loop(token: str, max_rides: int = 1) -> None:
    """
    Poll the exchange for rides and handle them one by one.

    max_rides: stop after this many completed rides (set to None for ∞).
    """
    rides_completed = 0
    print(f"[RSE] Polling for rides every {POLL_INTERVAL}s …  (Ctrl-C to stop)")

    while True:
        try:
            job = grab_next_ride(token)

            if job is None:
                # No matching rides right now — wait and try again.
                print(f"[RSE] No rides available.  Checking again in {POLL_INTERVAL}s …")
                time.sleep(POLL_INTERVAL)
                continue

            # ── A ride has been assigned ──────────────────────────────────────
            print(f"\n[RSE] Ride assigned!  job_id={job['job_id'][:8]}…")
            print(f"  Passenger  : {job['buyer_username']}  "
                  f"(reputation {job['buyer_reputation']:.1f}/5.0)")
            print(f"  Pickup     : {job.get('start_address', job.get('address', 'N/A'))}")
            print(f"  Drop-off   : {job.get('end_address', 'N/A')}")
            print(f"  Service    : {job['service']}")
            print(f"  Fare       : {job['currency']} {job['price']:.2f}  "
                  f"via {job['payment_method']}")
            print()

            # ── Accept or reject ──────────────────────────────────────────────
            if not should_accept(job):
                reject_ride(token, job["job_id"], reason="Policy rejection")
                time.sleep(5)   # brief pause before looking for the next ride
                continue

            print(f"[dispatch] Accepted.  Navigate to: "
                  f"{job.get('start_address', job.get('address'))}")

            # In production: push pickup address to in-vehicle nav, notify driver, etc.
            # Here we simulate the ride taking a few seconds.
            print("[dispatch] Simulating ride …")
            time.sleep(3)

            # ── Complete the ride ─────────────────────────────────────────────
            complete_ride(token, job["job_id"], passenger_rating=5)
            rides_completed += 1
            print(f"[RSE] Rides completed this session: {rides_completed}")

            if max_rides is not None and rides_completed >= max_rides:
                print("[RSE] Reached max_rides limit.  Stopping.")
                break

            # Brief pause before hunting for the next ride.
            time.sleep(POLL_INTERVAL)

        except PermissionError as e:
            print(f"[RSE] Access denied — check seat NFT setup: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n[RSE] Dispatch loop stopped by operator.")
            break
        except requests.HTTPError as e:
            print(f"[RSE] HTTP error: {e} — retrying in 30s …")
            time.sleep(30)
        except Exception as e:
            print(f"[RSE] Unexpected error: {e} — retrying in 30s …")
            time.sleep(30)


def main():
    username = CREDENTIALS["username"]
    password = CREDENTIALS["password"]

    # ── Account setup (idempotent — safe to call every run) ───────────────────
    register(username, password)   # no-op if account already exists
    token = login(username, password)

    # ── Link your RSE Seat NFT wallet (do this once per account) ─────────────
    # Replace with the wallet address that holds your seat NFT.
    # Contact partners@theservicesexchange.com to receive a seat allocation.
    # Comment this out after the first run if you prefer.
    SEAT_WALLET = os.environ.get("RSE_WALLET_ADDRESS", "")
    if SEAT_WALLET:
        set_wallet(token, SEAT_WALLET)
    else:
        print("[RSE] No RSE_WALLET_ADDRESS set — seat NFT not linked.  "
              "This is fine while SEAT_VERIFICATION_ENABLED=False.")

    # ── Start polling for rides ───────────────────────────────────────────────
    # max_rides=1 for this demo; remove the argument (or set None) to run forever.
    dispatch_loop(token, max_rides=1)


if __name__ == "__main__":
    main()

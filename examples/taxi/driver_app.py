#!/usr/bin/env python3
"""
Supply-side taxi agent — The Services Exchange (D5 reference)
=============================================================
Fleet operator account + scoped agent token for the vehicle process.

Flow
----
  operator login → set_wallet (optional) → create/reuse agent token
  → poll /grab_job as agent → job channel status posts → sign_job

Agent scopes used
-----------------
  history:read  jobs:grab  jobs:write  chat:write  chat:read

Env
---
  RSE_USERNAME / RSE_PASSWORD     fleet operator credentials
  RSE_WALLET_ADDRESS             optional seat NFT wallet
  RSE_AGENT_TOKEN                optional: reuse an existing agent token
  RSE_AGENT_LABEL                default "taxi-vehicle-1"
  RSE_API                        default https://rse-api.com:5003
"""

from __future__ import annotations

import os
import re
import sys
import time
import requests


class RateLimited(Exception):
    def __init__(self, wait_secs: int):
        self.wait_secs = wait_secs
        super().__init__(f"rate-limited — retry in {wait_secs}s")


RSE_API = os.environ.get("RSE_API", "https://rse-api.com:5003")
VERIFY_SSL = os.environ.get("RSE_VERIFY_SSL", "1") != "0"

CREDENTIALS = {
    "username": os.environ.get("RSE_USERNAME", "acme_taxi_fleet"),
    "password": os.environ.get("RSE_PASSWORD", "ChangeMe123!"),
}

VEHICLE_CAPABILITIES = (
    "Licensed taxi and rideshare driver.  Insured, background-checked. "
    "Comfortable 4-door sedan, up to 4 passengers, trunk space for 3 large bags. "
    "Serving greater San Francisco Bay Area.  Available for airport runs, "
    "point-to-point trips, and hourly hire."
)

CURRENT_LOCATION = {
    "address": "Market Street & 4th Street, San Francisco, CA 94103",
    "max_distance": 20,
}

# Must match server GRAB_JOB_COOLDOWN_SECONDS (default 900). For demos use a
# dedicated supply account per vehicle, or set server cooldown lower in config.
POLL_INTERVAL = int(os.environ.get("RSE_GRAB_COOLDOWN", "900"))

AGENT_SCOPES = [
    "history:read",
    "jobs:grab",
    "jobs:write",
    "chat:write",
    "chat:read",
]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(username: str, password: str) -> bool:
    r = requests.post(
        f"{RSE_API}/register",
        verify=VERIFY_SSL,
        json={"username": username, "password": password, "user_type": "supply"},
    )
    if r.status_code == 201:
        print(f"[RSE] Account created: {username}")
        return True
    if r.status_code == 409:
        print(f"[RSE] Account already exists: {username}")
        return False
    r.raise_for_status()
    return False


def login(username: str, password: str) -> str:
    r = requests.post(
        f"{RSE_API}/login",
        verify=VERIFY_SSL,
        json={"username": username, "password": password},
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    print(f"[RSE] Operator logged in as {username} (type={r.json().get('user_type')})")
    return token


def set_wallet(operator_token: str, wallet_address: str) -> None:
    r = requests.post(
        f"{RSE_API}/set_wallet",
        headers=_auth(operator_token),
        json={"wallet_address": wallet_address},
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        body = r.json()
        print(
            f"[RSE] Wallet linked: {wallet_address[:10]}… "
            f"seat_status={body.get('seat_status')} "
            f"public_id={(body.get('identity') or {}).get('public_id')}"
        )
    else:
        print(f"[RSE] set_wallet returned {r.status_code}: {r.text} (non-fatal)")


def ensure_agent_token(operator_token: str) -> str:
    """
    Return a bearer token for the vehicle process.
    Prefer RSE_AGENT_TOKEN if set; otherwise create a new agent (token shown once).
    """
    existing = os.environ.get("RSE_AGENT_TOKEN", "").strip()
    if existing:
        print("[RSE] Using RSE_AGENT_TOKEN from environment")
        return existing

    label = os.environ.get("RSE_AGENT_LABEL", "taxi-vehicle-1")
    r = requests.post(
        f"{RSE_API}/agents",
        headers=_auth(operator_token),
        json={"label": label, "scopes": AGENT_SCOPES},
        verify=VERIFY_SSL,
    )
    if r.status_code == 403:
        print(f"[RSE] Agent create forbidden: {r.text}")
        print("[RSE] Falling back to operator token (human session).")
        return operator_token
    r.raise_for_status()
    data = r.json()
    agent_token = data["agent_token"]
    print(f"[RSE] Agent created: id={data['agent_id'][:8]}… label={label}")
    print(f"[RSE] SAVE agent_token (shown once): {agent_token}")
    print("[RSE] Tip: export RSE_AGENT_TOKEN=… for subsequent runs")
    return agent_token


def grab_next_ride(token: str) -> dict | None:
    payload = {
        "capabilities": VEHICLE_CAPABILITIES,
        "location_type": "physical",
        "address": CURRENT_LOCATION["address"],
        "max_distance": CURRENT_LOCATION["max_distance"],
    }
    r = requests.post(
        f"{RSE_API}/grab_job",
        headers=_auth(token),
        json=payload,
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        return r.json()
    if r.status_code == 204:
        return None
    if r.status_code == 403:
        raise PermissionError(f"Grab forbidden: {r.json().get('error')}")
    if r.status_code == 429:
        err = r.json().get("error", "")
        m = re.search(r"wait (\d+)s", err)
        wait = int(m.group(1)) if m else POLL_INTERVAL
        raise RateLimited(wait)
    r.raise_for_status()
    return None


def post_channel(
    token: str,
    job_id: str,
    body: str,
    *,
    message_type: str = "agent_structured",
    payload: dict | None = None,
    client_message_id: str | None = None,
) -> dict | None:
    """Post ride status to the job channel (passenger sees this in Job chat)."""
    r = requests.post(
        f"{RSE_API}/jobs/{job_id}/messages",
        headers=_auth(token),
        json={
            "body": body,
            "message_type": message_type,
            "payload": payload or {},
            "client_message_id": client_message_id,
        },
        verify=VERIFY_SSL,
    )
    if r.status_code in (200, 201):
        print(f"[channel] → {body}")
        return r.json()
    print(f"[channel] post {r.status_code}: {r.text}")
    return None


def poll_channel(token: str, job_id: str, since_ts: int = 0) -> list:
    r = requests.get(
        f"{RSE_API}/jobs/{job_id}/messages",
        headers=_auth(token),
        params={"since_ts": since_ts, "limit": 50},
        verify=VERIFY_SSL,
    )
    if r.status_code != 200:
        return []
    return r.json().get("messages") or []


def should_accept(job: dict) -> bool:
    fare = job.get("price", 0)
    passenger_rep = job.get("buyer_reputation", 2.5)
    if fare < 10.00:
        print(f"  [policy] Fare ${fare:.2f} below minimum — rejecting.")
        return False
    if passenger_rep < 1.5:
        print(f"  [policy] Passenger reputation {passenger_rep:.1f} too low — rejecting.")
        return False
    return True


def reject_ride(token: str, job_id: str, reason: str = "Vehicle unavailable") -> None:
    r = requests.post(
        f"{RSE_API}/reject_job",
        headers=_auth(token),
        json={"job_id": job_id, "reason": reason},
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        print(f"[RSE] Job {job_id[:8]}… rejected and returned to exchange.")
    else:
        print(f"[RSE] reject_job returned {r.status_code}: {r.text}")


def complete_ride(token: str, job_id: str, passenger_rating: int) -> None:
    assert 1 <= passenger_rating <= 5
    r = requests.post(
        f"{RSE_API}/sign_job",
        headers=_auth(token),
        json={"job_id": job_id, "rating": passenger_rating},
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    print(f"[RSE] Ride signed.  Passenger rated {passenger_rating}/5.")


def execute_ride(token: str, job: dict) -> None:
    """
    Simulate navigation + drop-off while streaming structured status on the job channel.
    """
    job_id = job["job_id"]
    pickup = job.get("start_address") or job.get("address") or "pickup"
    dropoff = job.get("end_address") or "dropoff"

    # Confirm channel membership (lazy-create on first system message from grab)
    r = requests.get(
        f"{RSE_API}/jobs/{job_id}/channel",
        headers=_auth(token),
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        meta = r.json()
        print(f"[channel] state={meta.get('state')} members={meta.get('members')}")
    else:
        print(f"[channel] meta {r.status_code}: {r.text}")

    last_ts = 0
    steps = [
        ("en_route", f"En route to pickup: {pickup}", {"status": "en_route", "eta_min": 8}),
        ("arrived", f"Arrived at pickup: {pickup}", {"status": "arrived"}),
        ("onboard", "Passenger onboard — departing for dropoff", {"status": "in_trip"}),
        ("complete", f"Arrived at dropoff: {dropoff}", {"status": "completed"}),
    ]
    for i, (cid, body, payload) in enumerate(steps):
        post_channel(
            token,
            job_id,
            body,
            message_type="agent_structured",
            payload=payload,
            client_message_id=f"taxi-{job_id[:8]}-{cid}",
        )
        # Drain any passenger messages
        msgs = poll_channel(token, job_id, since_ts=last_ts)
        for m in msgs:
            if m.get("sender") not in (None, "system") and m.get("message_type") != "system":
                print(f"[channel] ← {m.get('sender')}: {m.get('body')}")
            last_ts = max(last_ts, int(m.get("sent_at") or 0))
        time.sleep(1 if i < len(steps) - 1 else 0)

    complete_ride(token, job_id, passenger_rating=5)


def dispatch_loop(token: str, max_rides: int | None = 1) -> None:
    rides_completed = 0
    last_grab_time = 0.0
    print(f"[RSE] Agent dispatch loop (grab cooldown {POLL_INTERVAL}s) …")

    while True:
        try:
            elapsed = time.monotonic() - last_grab_time
            remaining = POLL_INTERVAL - elapsed
            if remaining > 0 and last_grab_time > 0:
                print(f"[RSE] Waiting {remaining:.0f}s for rate-limit window …")
                time.sleep(remaining)

            last_grab_time = time.monotonic()
            job = grab_next_ride(token)

            if job is None:
                print("[RSE] No matching rides right now.")
                # First call also starts the cooldown window on the server;
                # keep local last_grab_time so we don't hammer after 204.
                continue

            print(f"\n[RSE] Ride assigned!  job_id={job['job_id'][:8]}…")
            print(f"  Passenger  : {job['buyer_username']}  (rep {job.get('buyer_reputation', 0):.1f})")
            print(f"  Pickup     : {job.get('start_address', job.get('address', 'N/A'))}")
            print(f"  Drop-off   : {job.get('end_address', 'N/A')}")
            print(f"  Fare       : {job.get('currency', 'USD')} {job.get('price')}")
            print()

            if not should_accept(job):
                reject_ride(token, job["job_id"], reason="Policy rejection")
                continue

            try:
                execute_ride(token, job)
            except Exception as work_err:
                print(f"[dispatch] Ride failed: {work_err}")
                reject_ride(token, job["job_id"], reason=f"Execution error: {work_err}")
                continue

            end_addr = job.get("end_address") or job.get("address")
            if end_addr and end_addr != "N/A":
                CURRENT_LOCATION["address"] = end_addr
                print(f"[dispatch] Position updated → {end_addr}")

            rides_completed += 1
            print(f"[RSE] Rides completed this session: {rides_completed}")
            if max_rides is not None and rides_completed >= max_rides:
                print("[RSE] Reached max_rides. Stopping.")
                break

        except RateLimited as e:
            print(f"[RSE] Rate limited — wait {e.wait_secs}s.")
            last_grab_time = time.monotonic()
            time.sleep(e.wait_secs + 2)
        except PermissionError as e:
            print(f"[RSE] Access denied: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n[RSE] Stopped.")
            break
        except requests.HTTPError as e:
            print(f"[RSE] HTTP error: {e} — retry in 30s")
            time.sleep(30)
        except Exception as e:
            print(f"[RSE] Unexpected: {e} — retry in 30s")
            time.sleep(30)


def main() -> None:
    username = CREDENTIALS["username"]
    password = CREDENTIALS["password"]

    register(username, password)
    operator_token = login(username, password)

    seat_wallet = os.environ.get("RSE_WALLET_ADDRESS", "")
    if seat_wallet:
        set_wallet(operator_token, seat_wallet)
    else:
        print(
            "[RSE] No RSE_WALLET_ADDRESS — seat not linked "
            "(OK while SEAT_VERIFICATION_ENABLED=False)."
        )

    # Vehicle process uses agent token for grab + channel + sign
    agent_token = ensure_agent_token(operator_token)
    dispatch_loop(agent_token, max_rides=1)


if __name__ == "__main__":
    main()

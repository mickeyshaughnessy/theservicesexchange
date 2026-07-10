#!/usr/bin/env python3
"""
Demand-side taxi passenger — The Services Exchange (D5 reference)
=================================================================
Posts a ride bid, waits for a driver/agent grab, watches the job channel
for agent_structured status updates, then signs the job.

Env
---
  RSE_USERNAME / RSE_PASSWORD
  RSE_API  (default https://rse-api.com:5003)
"""

from __future__ import annotations

import os
import sys
import time
import requests

RSE_API = os.environ.get("RSE_API", "https://rse-api.com:5003")
VERIFY_SSL = os.environ.get("RSE_VERIFY_SSL", "1") != "0"

CREDENTIALS = {
    "username": os.environ.get("RSE_USERNAME", "demo_passenger"),
    "password": os.environ.get("RSE_PASSWORD", "ChangeMe123!"),
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(username: str, password: str) -> bool:
    r = requests.post(
        f"{RSE_API}/register",
        verify=VERIFY_SSL,
        json={"username": username, "password": password, "user_type": "demand"},
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
    data = r.json()
    print(f"[RSE] Logged in as {username} (type={data.get('user_type')})")
    return data["access_token"]


def post_ride_request(
    token: str,
    pickup: str,
    dropoff: str,
    passengers: int,
    fare_usd: float,
    notes: str = "",
    expiry_seconds: int = 300,
) -> str:
    service_description = (
        f"Taxi ride: {pickup} → {dropoff}.  "
        f"{passengers} passenger{'s' if passengers != 1 else ''}.  "
        + (f"Notes: {notes}  " if notes else "")
        + "Licensed taxi or rideshare vehicle required."
    )
    payload = {
        "service": service_description,
        "price": fare_usd,
        "currency": "USD",
        "payment_method": "cash",
        "location_type": "physical",
        "start_address": pickup,
        "end_address": dropoff,
        "address": pickup,
        "end_time": int(time.time()) + expiry_seconds,
    }
    r = requests.post(
        f"{RSE_API}/submit_bid",
        headers=_auth(token),
        json=payload,
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    bid_id = r.json()["bid_id"]
    print(
        f"[RSE] Ride request posted (bid_id={bid_id[:8]}…)  "
        f"${fare_usd:.2f} | {pickup} → {dropoff}"
    )
    return bid_id


def wait_for_driver(token: str, bid_id: str, timeout_seconds: int = 270) -> dict | None:
    print(f"[RSE] Waiting for a driver (timeout={timeout_seconds}s) …")
    deadline = time.time() + timeout_seconds
    poll_interval = 5

    while time.time() < deadline:
        r = requests.get(f"{RSE_API}/my_bids", headers=_auth(token), verify=VERIFY_SSL)
        r.raise_for_status()
        still_open = any(b["bid_id"] == bid_id for b in r.json().get("bids", []))
        if not still_open:
            job = _find_job_for_bid(token, bid_id)
            if job:
                print(
                    f"[RSE] Driver accepted!  job_id={job['job_id'][:8]}…  "
                    f"driver={job['provider_username']}"
                )
                return job
        time.sleep(poll_interval)

    print("[RSE] Timed out waiting for a driver.")
    return None


def _find_job_for_bid(token: str, bid_id: str) -> dict | None:
    r = requests.get(f"{RSE_API}/my_jobs", headers=_auth(token), verify=VERIFY_SSL)
    if r.status_code != 200:
        return None
    for job in r.json().get("active_jobs", []):
        if job.get("bid_id") == bid_id:
            return job
    return None


def cancel_ride_request(token: str, bid_id: str) -> None:
    r = requests.post(
        f"{RSE_API}/cancel_bid",
        headers=_auth(token),
        json={"bid_id": bid_id},
        verify=VERIFY_SSL,
    )
    if r.status_code == 200:
        print(f"[RSE] Bid {bid_id[:8]}… cancelled.")
    else:
        print(f"[RSE] Cancel returned {r.status_code}: {r.text}")


def watch_ride_channel(token: str, job_id: str, timeout_seconds: int = 120) -> None:
    """
    Poll the job channel for driver/agent status (agent_structured) and
    post a short passenger note once the channel is open.
    """
    print(f"[channel] Watching job {job_id[:8]}… for vehicle updates")
    # Join/read meta
    r = requests.get(
        f"{RSE_API}/jobs/{job_id}/channel",
        headers=_auth(token),
        verify=VERIFY_SSL,
    )
    if r.status_code != 200:
        print(f"[channel] cannot open: {r.status_code} {r.text}")
        return
    meta = r.json()
    print(f"[channel] state={meta.get('state')} members={meta.get('members')}")

    # Passenger message to the vehicle
    requests.post(
        f"{RSE_API}/jobs/{job_id}/messages",
        headers=_auth(token),
        json={
            "body": "I'm at the curb with two bags — blue jacket.",
            "message_type": "user",
            "client_message_id": f"pax-hello-{job_id[:8]}",
        },
        verify=VERIFY_SSL,
    )

    last_ts = 0
    deadline = time.time() + timeout_seconds
    seen = set()
    while time.time() < deadline:
        r = requests.get(
            f"{RSE_API}/jobs/{job_id}/messages",
            headers=_auth(token),
            params={"since_ts": last_ts, "limit": 50},
            verify=VERIFY_SSL,
        )
        if r.status_code != 200:
            time.sleep(2)
            continue
        data = r.json()
        for m in data.get("messages") or []:
            mid = m.get("message_id")
            if mid in seen:
                continue
            seen.add(mid)
            last_ts = max(last_ts, int(m.get("sent_at") or 0))
            mtype = m.get("message_type") or "user"
            sender = m.get("sender")
            body = m.get("body")
            payload = m.get("payload") or {}
            if mtype == "system":
                print(f"[channel] [system] {body}")
            elif mtype == "agent_structured":
                status = payload.get("status") or mtype
                print(f"[channel] [vehicle:{status}] {body}")
                if status in ("completed", "arrived_dropoff"):
                    # mark read and return — ride simulation finished on supply side
                    requests.post(
                        f"{RSE_API}/jobs/{job_id}/messages/read",
                        headers=_auth(token),
                        json={"last_read_ts": last_ts},
                        verify=VERIFY_SSL,
                    )
                    return
            else:
                print(f"[channel] [{sender}] {body}")
        time.sleep(2)

    print("[channel] Watch timeout — continuing to sign.")


def complete_ride(token: str, job_id: str, driver_rating: int) -> None:
    assert 1 <= driver_rating <= 5
    r = requests.post(
        f"{RSE_API}/sign_job",
        headers=_auth(token),
        json={"job_id": job_id, "rating": driver_rating},
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    print(f"[RSE] Ride signed.  Driver rated {driver_rating}/5.")


def main() -> None:
    username = CREDENTIALS["username"]
    password = CREDENTIALS["password"]

    register(username, password)
    token = login(username, password)

    bid_id = post_ride_request(
        token=token,
        pickup="355 Main Street, San Francisco, CA 94105",
        dropoff="SFO International Terminal, San Francisco, CA 94128",
        passengers=2,
        fare_usd=45.00,
        notes="Two large bags.  Quiet ride preferred.",
        expiry_seconds=300,
    )

    job = wait_for_driver(token, bid_id, timeout_seconds=270)
    if job is None:
        cancel_ride_request(token, bid_id)
        print("No driver found.  Consider raising the fare or retrying.")
        sys.exit(1)

    print("\nDriver details:")
    print(f"  Username    : {job['provider_username']}")
    print(f"  Reputation  : {job.get('provider_reputation', 0):.1f}/5.0")
    print(f"  Seat stamp  : {job.get('provider_seat_token_id')}")
    print(f"  Pickup      : {job.get('start_address', job.get('address'))}")
    print(f"  Drop-off    : {job.get('end_address')}")
    print(f"  Fare        : {job.get('currency')} {job.get('price')}")
    print()

    # Live vehicle updates via job channel (agent_structured from driver agent)
    watch_ride_channel(token, job["job_id"], timeout_seconds=90)

    complete_ride(token, job["job_id"], driver_rating=5)
    print("Ride complete.  Check portfolio.html for history.")


if __name__ == "__main__":
    main()

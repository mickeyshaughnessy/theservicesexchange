# Taxi Integration Examples

Two reference apps showing how to connect a taxi or rideshare operation to
The Services Exchange as a demand-side (passenger) or supply-side (driver /
fleet) partner.

---

## How the exchange works for taxi

The exchange is a general-purpose service marketplace.  Taxi is just one
service category — the same API handles home cleaners, lawyers, HVAC
technicians, and anything else.

| Concept | Exchange term | Who uses it |
|---|---|---|
| Passenger books a ride | **Bid** (`POST /submit_bid`) | Demand side |
| Driver / fleet picks up a job | **Grab** (`POST /grab_job`) | Supply side |
| Both sides confirm completion | **Sign** (`POST /sign_job`) | Both |

**Matching is LLM-powered.**  There is no schema to conform to.  The
passenger writes a plain-English ride description; the driver writes a
plain-English capability description; the exchange's LLM reads both and
decides whether they're a fit.  A structured dispatch protocol is not needed.

---

## Files

| File | Description |
|---|---|
| `passenger_app.py` | Demand side — passenger books a ride, waits for a driver, rates on completion |
| `driver_app.py` | Supply side — driver / fleet polls for rides, accepts or rejects, rates on completion |

---

## Quick start

```bash
pip install requests

# Passenger (demand side)
RSE_USERNAME=my_passenger RSE_PASSWORD=secret python passenger_app.py

# Driver / fleet (supply side)
RSE_USERNAME=my_fleet RSE_PASSWORD=secret \
RSE_WALLET_ADDRESS=0xYourWallet python driver_app.py
```

Both scripts default to `https://rse-api.com:5003`.  For local development:

```python
RSE_API = "http://localhost:5003"
VERIFY_SSL = False
```

---

## API reference (taxi-relevant endpoints)

All endpoints return JSON.  Authenticated endpoints require
`Authorization: Bearer <token>` from `POST /login`.

### Account setup (run once)

```
POST /register
  { "username": str, "password": str, "user_type": "demand" | "supply" }
  → 201 Created

POST /login
  { "username": str, "password": str }
  → { "access_token": str }

POST /set_wallet                         (supply side only)
  { "wallet_address": "0x..." }
  → 200 OK
```

### Demand side (passenger)

```
POST /submit_bid
  {
    "service":        str,        # plain-English ride description
    "price":          float,      # fare offered (USD)
    "currency":       "USD",
    "payment_method": "cash" | "xmoney" | "paypal",
    "location_type":  "physical",
    "start_address":  str,        # pickup address
    "end_address":    str,        # dropoff address
    "end_time":       int         # Unix timestamp — request expires at this time
  }
  → { "bid_id": str }

GET /my_bids
  → { "bids": [ { "bid_id": str, "service": str, ... } ] }
  # Bid disappears from this list when a driver grabs it.

POST /cancel_bid
  { "bid_id": str }
  → 200 OK
```

### Supply side (driver / fleet)

```
POST /grab_job
  {
    "capabilities": str,          # plain-English description of vehicle / driver
    "location_type": "physical",
    "address":      str,          # current vehicle location
    "max_distance": int           # miles — only show rides within this radius
  }
  → 200 { job record }            # ride assigned — handle it
  → 204 No Content                # no matching rides right now — poll again later

POST /reject_job
  { "job_id": str, "reason": str }
  → 200 OK                        # ride returned to exchange for another driver
```

### Both sides (after the ride)

```
POST /sign_job
  { "job_id": str, "rating": int (1–5) }
  → 200 OK
  # Job is fully complete once both passenger and driver have signed.
```

---

## Job record fields

When `POST /grab_job` returns 200 the body is a job record:

```json
{
  "job_id":              "uuid",
  "bid_id":              "uuid",
  "service":             "Taxi ride: 355 Main St → SFO …",
  "price":               45.00,
  "currency":            "USD",
  "payment_method":      "cash",
  "location_type":       "physical",
  "start_address":       "355 Main Street, San Francisco, CA 94105",
  "end_address":         "SFO International Terminal, San Francisco, CA 94128",
  "address":             "355 Main Street, San Francisco, CA 94105",
  "buyer_username":      "demo_passenger",
  "provider_username":   "acme_taxi_fleet",
  "buyer_reputation":    2.5,
  "provider_reputation": 2.5,
  "accepted_at":         1700000000
}
```

---

## Seat NFT access (supply side)

Supply-side partners receive an RSE Seat NFT (ERC-721 on Base L2).  Link
your holding wallet once with `POST /set_wallet`.  The exchange reads the
chain to verify your seat on every `/grab_job` call (read-only — no gas cost
to you).

Contact **partners@theservicesexchange.com** to request a seat allocation.

Contract address: `0x151fEB62F0D3085617a086130cc67f7f18Ce33CE` (Base mainnet)

---

## Integration checklist

**Demand (passenger app)**
- [ ] Create one `demand` account per user (or per organisation for B2B)
- [ ] Cache the auth token (24 h TTL); refresh on 401
- [ ] Include `start_address` + `end_address` in every ride bid for structured pickup/dropoff
- [ ] Set `end_time` to a reasonable expiry (300 s is a sensible default for on-demand rides)
- [ ] Poll `/my_bids` to detect driver acceptance; then fetch `/my_jobs` for driver details
- [ ] Always cancel bids that expire without a match so they don't linger in the exchange

**Supply (driver / fleet app)**
- [ ] Create one `supply` account per driver or per fleet
- [ ] Call `POST /set_wallet` once to link your seat NFT wallet
- [ ] Keep VEHICLE_CAPABILITIES current — if you add vehicle types, update the string
- [ ] Don't poll `/grab_job` faster than every 15 s (rate limit per seat)
- [ ] Always handle the job you grab: call `sign_job` or `reject_job` — never discard
- [ ] Call `sign_job` after every completed ride to build your reputation score

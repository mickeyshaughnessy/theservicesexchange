# Taxi Integration Examples (D5 — agent + job channel)

Two reference apps for rideshare-style integration with The RSE.

| File | Side | Auth |
|------|------|------|
| `passenger_app.py` | Demand (passenger) | Human session token |
| `driver_app.py` | Supply (fleet / vehicle) | **Operator login → agent token** for grab/channel/sign |

There is no taxi-specific schema. Passengers post plain-English bids; vehicles send plain-English capabilities; the exchange matches with LLM + location + reputation.

---

## End-to-end (agent era)

```text
Passenger (demand)           The RSE                      Taxi agent (supply token)
     |                           |                                    |
     | submit_bid "ride A→B"     |                                    |
     |-------------------------->|                                    |
     |                           |          grab_job (agent token)    |
     |                           |<-----------------------------------|
     |                           | job + channel                      |
     |  job channel messages     |  agent_structured: en_route …      |
     |<------------------------->|<---------------------------------->|
     | sign_job                  |            sign_job                |
     |-------------------------->|<-----------------------------------|
```

---

## Quick start

```bash
pip install requests

# Terminal 1 — passenger
RSE_USERNAME=my_passenger RSE_PASSWORD='YourPass123!' \
  python passenger_app.py

# Terminal 2 — fleet / vehicle agent
RSE_USERNAME=my_fleet RSE_PASSWORD='YourPass123!' \
RSE_WALLET_ADDRESS=0xYourSeatWallet \   # optional
  python driver_app.py

# Reuse agent token on next driver runs:
export RSE_AGENT_TOKEN='…from first create…'
python driver_app.py
```

Defaults: API `https://rse-api.com:5003`. Local:

```bash
export RSE_API=http://localhost:5003
export RSE_VERIFY_SSL=0
```

---

## Driver agent details

1. Operator account (`user_type=supply`) registers/logs in.
2. Optional `POST /set_wallet` for seat identity (`public_id` → `seat:{id}`).
3. `POST /agents` with scopes:
   - `history:read`, `jobs:grab`, `jobs:write`, `chat:write`, `chat:read`
4. Vehicle process uses **agent** bearer token for:
   - `POST /grab_job`
   - `GET/POST /jobs/{id}/messages` (status: `en_route`, `arrived`, `in_trip`, `completed`)
   - `POST /sign_job` / `POST /reject_job`
5. Agent cannot create agents, change wallet, or hit undeclared routes (default-deny).

`/grab_job` is limited per **operator account** (server `GRAB_JOB_COOLDOWN_SECONDS`, default **900s**).  
Client wait: `RSE_GRAB_COOLDOWN` (default 900).

**Fleet DX tips**
- Use **one supply account per vehicle** (or accept 15‑min spacing per account).
- Create the agent once and reuse with `export RSE_AGENT_TOKEN=…` (avoids create/list cache confusion).
- `GET /agents` now force-refreshes account meta; still prefer caching the token client-side.
- Non-prod only: lower `GRAB_JOB_COOLDOWN_SECONDS` in server `config.py` for load tests.

---

## Passenger channel

After a driver grabs the bid, the passenger app:

- Opens `GET /jobs/{id}/channel`
- Posts a curb note on the channel
- Polls for `agent_structured` vehicle status
- Signs when the ride simulation finishes

Web UI: account panel → **Job chat** (same channel).

---

## Identity & history

| Party | Public identity |
|-------|-----------------|
| Passenger | username |
| Fleet | `seat:{token_id}` when seat valid, else username |
| Vehicle messages | `agent_id` on channel posts |

Portfolio / export: site `portfolio.html`, APIs `GET /portfolio/{user}`, `GET /export/history`, `GET /export/proof/{job_id}`.

---

## Checklist

**Demand**
- [ ] `demand` account per passenger (or org)
- [ ] `start_address` + `end_address` on every bid
- [ ] Short `end_time` for on-demand (e.g. 300s)
- [ ] Cancel unmatched bids
- [ ] Watch job channel; sign after ride

**Supply**
- [ ] `supply` operator account
- [ ] Agent token with grab + chat scopes
- [ ] Optional seat wallet
- [ ] Honor grab cooldown
- [ ] Always sign or reject — never drop a grabbed job
- [ ] Stream status on the job channel

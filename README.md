# The RSE

Open marketplace for robot labor. Buyers post requests; providers call `/grab_job`.

Live API: **https://rse-api.com:5003** · Docs: **https://rse-api.com:5003/api_docs.html** · Site: **https://therobotservicesexchange.com**

## How it works

1. **Buyers** register and post a bid (`POST /bid`) — service, price, location. One-shot or recurring (`recurring` + `cadence` + spending limits). Settlement hints optional (Stripe / XMoney / PayPal). Autobidding only on `/bid`; legacy `/submit_bid` is one-shot.
2. **Providers** register, call `/grab_job` (optional `geohash` whitelist region).
3. Match by capability + reputation; both sides complete and rate via `/sign_job`.

## Seats

A seat is a **number**, an **owner name**, and a **private 12-word phrase**. Mickey Shaughnessy is the registrar (assign, transfer, revoke). Call or text [+1 530 219 0940](tel:+15302190940) ([SMS](sms:+15302190940)), or email [therobotservicesexchange@proton.me](mailto:therobotservicesexchange@proton.me).

Founding book (this issuance): seats **1–1000** owner **Dr. Aftab**; seats **1001–11000** owner **Amanda Jean**. Transfer keeps the phrase; Mickey updates the owner.

When `SEAT_VERIFICATION_ENABLED` is on (currently **off**):

- **Remote** `/grab_job` (software bots) does **not** need a seat.
- **Physical / hybrid** must send the seat number, the owner name, and a daily hash of the phrase:

```python
import hashlib
from datetime import datetime, timezone
day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
secret = hashlib.sha256(f"{phrase}|{day}".encode()).hexdigest()
# POST /grab_job  { "seat": { "id": 1, "owner": "Dr. Aftab", "secret": secret }, ... }
```

The server accepts today, yesterday, and tomorrow (UTC) so midnight timezone skew does not fail the grab. Never send the phrase itself.

Admin (Mickey): `GET/POST /admin/seats*` or the Seats tab on `admin.html`. `GET /admin/seats/export?owner=Dr.%20Aftab` returns phrases for that holder.

## Deploy

See **[DEPLOYMENT_NOTES.md](DEPLOYMENT_NOTES.md)** — short playbook:

```bash
git push origin main
./deploy.sh
```

Optional Grok job (suggests 3 next features): `./scripts/prod/suggest_next_features.sh`

## Running Locally

### Requirements

- Python 3.8+
- `pip install -r requirements.txt`

### Configuration

Copy `config_example.py` to `config.py` and fill in your values. `config.py` is gitignored — never commit it.

```bash
cp config_example.py config.py
# edit config.py with your API keys and DO Spaces credentials
```

### Start the API

```bash
python api_server.py
# or in production:
gunicorn -c gunicorn_config.py api_server:application
```

### Integration Tests

```bash
python int_tests.py
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /register | — | Create account |
| POST | /login | — | Get access token |
| GET | /account | ✓ | Account info + seat status |
| POST | /bid | ✓ | Post a service request or create recurring subscription bid (autobidding) |
| POST | /submit_bid | ✓ | Legacy one-shot bid (no recurring) |
| GET/POST | /auto_bids | ✓ | List / manage recurring templates; process due posts |
| POST | /grab_job | ✓ + seat | Claim a matching job |
| POST | /sign_job | ✓ | Complete and rate a job |
| POST | /reject_job | ✓ | Reject an assigned job |
| GET | /nearby | — | Services near a location |
| GET | /exchange_data | — | Active bids + market stats |
| GET | /stats | — | Platform statistics |
| POST | /chat | ✓ | Direct message |
| GET | /chat/conversations | ✓ | List conversations |
| POST | /chat/messages | ✓ | Conversation history |
| POST | /chat/reply | ✓ | Reply in a thread |
| POST | /chat/read | ✓ | Mark DMs read |
| GET | /jobs/{id}/channel | ✓ | Job-scoped channel |
| GET/POST | /jobs/{id}/messages | ✓ | Job channel history / post |
| POST | /jobs/{id}/messages/read | ✓ | Mark job channel read |
| POST | /bulletin | ✓ | Post to community board |
| GET | /bulletin/feed | — | Community bulletin feed |
| GET/POST | /jobs/{id}/party* | ✓ | Job parties (co-providers / co-buyers) |
| GET/POST | /campaigns* | mixed | Bulk campaigns, commits, sponsors |
| GET | /my_campaigns | ✓ | Campaigns you own or committed to |
| POST | /follow · /unfollow | ✓ | Follow graph |
| GET | /friends · /follows | ✓ | Friends / follow lists |
| POST/GET | /endorsements* | mixed | Operator endorsements |
| POST | /contacts/match | ✓ | Contact discovery |

The website is for people bidding for work. Supply (`/grab_job`, `/reject_job`, seats) and cooperation/comms above are **API-only** at rse-api.com — see `api_docs.html` and `openapi.yaml`.

## Buy a Robot catalog

The [Buy a Robot](https://therobotservicesexchange.com/robots.html) page loads a static JSON DB, in order:

1. Same-origin [`catalog/robots.json`](catalog/robots.json) (deployed with the site)
2. DigitalOcean Spaces mirror: `https://mithril-media.sfo3.digitaloceanspaces.com/theservicesexchange/catalog/robots.json`
3. Tiny embedded seed if both fail

Canonical seed also lives at `data/catalog/robots.json`. Robot images are under Spaces `…/robots/`.

```bash
# Seed / re-upload catalog JSON to Spaces (+ refresh catalog/robots.json)
python3 scripts/catalog/upload_robots_catalog.py

# Ensure every robot has a public image (reuse existing or generate placeholders)
python3 scripts/catalog/sync_robot_images.py

# Weekly merge (web crawl + optional Grok/X enrichment) then upload
python3 scripts/catalog/update_robots_catalog.py
```

On production, install Grok Build + crontab with:

```bash
bash scripts/prod/setup_prod_grok_and_cron.sh
# Prefer API key on server: XAI_API_KEY in /etc/rse/catalog.env
# Or COPY_GROK_AUTH=1 to scp ~/.grok/auth.json (owner-only 600)
```

## Seat admin

Mickey manages seats in `admin.html` (Seats tab) or:

```
GET  /admin/seats
POST /admin/seats/assign    { "username", "seat_id"? }
POST /admin/seats/transfer  { "seat_id", "to_username" }
POST /admin/seats/revoke    { "seat_id" }
POST /admin/seats/unrevoke  { "seat_id" }
```

## Project Structure

```
├── api_server.py         Flask API server
├── handlers.py           Business logic
├── seats.py              Central seat registry (Mickey assigns / transfers)
├── config_example.py     Config template (copy to config.py)
├── requirements.txt
├── int_tests.py          Integration tests
└── admin.html            Hiring + seat registry
```

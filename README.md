# The RSE

Open marketplace for robot labor. Buyers post requests; providers call `/grab_job`.

Live API: **https://rse-api.com:5003** · Docs: **https://rse-api.com:5003/api_docs.html** · Site: **https://therobotservicesexchange.com**

## How it works

1. **Buyers** register and post a bid (`POST /bid`) — service, price, location. One-shot or recurring (`recurring` + `cadence` + spending limits). Settlement hints optional (Stripe / XMoney / PayPal / Phantom). Autobidding only on `/bid`; legacy `/submit_bid` is one-shot.
2. **Providers** register, link a wallet (`/set_wallet`), call `/grab_job` (optional `geohash` whitelist region).
3. Match by capability + reputation; both sides complete and rate via `/sign_job`.

## Seat NFTs

`/grab_job` requires an ERC-721 seat on Base (chain 8453).

- Contract: [`0x151fEB62F0D3085617a086130cc67f7f18Ce33CE`](https://basescan.org/address/0x151fEB62F0D3085617a086130cc67f7f18Ce33CE)
- 100 seats · message [@MichaelSha10041](https://x.com/MichaelSha10041) on X with your wallet

```bash
curl -X POST https://rse-api.com:5003/set_wallet \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"wallet_address": "0xYourAddress"}'
```

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
# edit config.py with your API keys, DO Spaces credentials, ETH private key
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
| POST | /set_wallet | ✓ | Link Ethereum wallet |
| POST | /bid | ✓ | Post a service request or create recurring subscription bid (autobidding) |
| POST | /submit_bid | ✓ | Legacy one-shot bid (no recurring) |
| GET/POST | /auto_bids | ✓ | List / manage recurring templates; process due posts |
| POST | /grab_job | ✓ + seat | Claim a matching job |
| POST | /sign_job | ✓ | Complete and rate a job |
| POST | /reject_job | ✓ | Reject an assigned job |
| GET | /nearby | — | Services near a location |
| GET | /exchange_data | — | Active bids + market stats |
| GET | /stats | — | Platform statistics |

Chat, bulletin, job parties, campaigns, endorsements, and the follow graph are **deprecated** (HTTP **410**). The core loop is bid → grab_job → sign_job.

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

## Smart Contract

The RSESeat ERC-721 contract is in `contracts/`. It is built with Hardhat and OpenZeppelin 5.x.

```bash
cd contracts
npm install
npm test          # run 39 tests
npm run compile
```

Deploy to Base mainnet:
```bash
# set ETH_PRIVATE_KEY in contracts/.env (see contracts/.env.example)
npm run deploy:base
```

## Seat Admin CLI

Management scripts are in `seat_admin/`:

```bash
cd seat_admin
python info.py                          # contract info + supply
python mint.py 0xWalletAddress          # mint a seat
python check.py 0xWalletAddress         # check seat status
python revoke.py <tokenId>              # revoke a seat
python unrevoke.py <tokenId>            # restore a seat
python list_seats.py                    # list all seats
```

## Project Structure

```
├── api_server.py         Flask API server
├── handlers.py           Business logic
├── seat_verification.py  On-chain NFT seat verification (Base L2)
├── config_example.py     Config template (copy to config.py)
├── requirements.txt
├── int_tests.py          Integration tests
├── contracts/            Hardhat project: RSESeat ERC-721
│   ├── contracts/RSESeat.sol
│   ├── test/RSESeat.test.ts  (39 tests)
│   └── scripts/deploy.ts
├── seat_admin/           Python CLI for seat management
│   ├── mint.py, revoke.py, check.py, list_seats.py, info.py
│   ├── generate_metadata.py
│   └── upload_metadata.py
└── abi/RSESeat.json      Contract ABI for seat_verification.py
```

# The RSE Mobile App

Status: **v1 demand-side Android app shipped** (API-only Capacitor shell).

## What it is

- **App ID:** `com.rse.app`
- **Location:** `mobile/`
- **Content:** Bundled SPA in `mobile/www/` (not the marketing website)
- **Backend:** **https://rse-api.com:5003** only
- **Role:** Demand (buyer) — register/login with `user_type: demand`, post requests, track jobs, rate completion

Unlike GreenDial (which loads the live site in a WebView), this app is **independent of theservicesexchange.com**. All marketplace calls use Bearer tokens against the public API (see `openapi.yaml` / `api_docs.html`).

## User flows (v1)

1. Register or log in (demand only)
2. Post a service request (`POST /submit_bid`)
3. View / cancel open bids (`GET /my_bids`, `POST /cancel_bid`)
4. View active & completed jobs (`GET /my_jobs`)
5. Sign and rate when work is done (`POST /sign_job`)
6. Account snapshot (`GET /account`)

## Download

- Homepage top-left: **Download The RSE App** → `apk/The-RSE-1.0.0.apk`
- Build docs: `mobile/README.md`

## Out of scope (v1)

- Supply / grab_job / seats
- Campaigns, parties, bulletin
- iOS / App Store
- Play Store listing (AAB pipeline ready via `npm run bundle`)

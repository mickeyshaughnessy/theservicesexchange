# The RSE Mobile App

Status: **v1.3.0 demand-side Android app shipped** (contacts discovery + prior v1.2 features).

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
3. View / delete open bids (`GET /my_bids`, `POST /cancel_bid`)
4. View active & completed jobs (`GET /my_jobs`)
5. Sign and rate when work is done (`POST /sign_job`)
6. Nearby discovery (`POST /nearby`) — GPS or address, radius 1–50 mi
7. Product feedback board (`GET/POST /feedback`, `POST /feedback/{id}/reply`)
8. Account: stats, edit profile (`GET/POST /profile`), share link (`GET /profile/share_link` → `profile.html?pid=…`), log out
9. Auto-update (Android): fetch `apk/version.json`, download newer APK, system install prompt

## Auto-update

Sideloaded releases self-update via native `AppUpdate` plugin + hosted `https://theservicesexchange.com/apk/version.json`.  
See `mobile/README.md` § Auto-update for shipping steps.

## Branding (app only)

Robot mascot art ships **only** in the mobile app (not the website):

| Asset | Use |
|-------|-----|
| `mobile/branding/robot-full.png` | Auth hero, splash source |
| `mobile/branding/robot-avatar.png` | Header avatar, circular mark |
| `mobile/www/robot-*.png` | Bundled SPA copies |
| Android mipmaps / splash | Generated from `mobile/resources/` |

## Download

- Homepage top-left: **Download The RSE App** → `apk/The-RSE-1.4.0.apk`
- Play AAB: `mobile/dist/The-RSE-1.4.0.aab` (see `mobile/PLAY_STORE.md`)
- Update manifest: `apk/version.json` and `GET /app/version` on the API
- Build docs: `mobile/README.md`

## Out of scope (v1)

- Supply / grab_job / seats
- Campaigns, parties, bulletin
- iOS / App Store
- Play Store production listing (pipeline + docs: `mobile/PLAY_STORE.md`; privacy: `/privacy-app.html`)

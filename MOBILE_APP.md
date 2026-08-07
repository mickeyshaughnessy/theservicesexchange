# The RSE Mobile App

Demand-side Android app (`com.rse.app`). Code in `mobile/`; SPA in `mobile/www/`. API: **https://rse-api.com:5003** only — not a WebView of the marketing site.

## Flows

1. Register / log in (demand)
2. Post request (`POST /submit_bid`); manage bids (`/my_bids`, `/cancel_bid`)
3. Jobs: active/completed (`/my_jobs`), sign & rate (`/sign_job`)
4. Nearby (`POST /nearby`) · feedback board · profile / share link
5. Sideload auto-update via `apk/version.json`

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

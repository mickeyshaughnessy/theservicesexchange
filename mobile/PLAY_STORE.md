# Google Play Store — The RSE (`com.rse.app`)

This guide starts the Play listing. **You** complete Console account, identity verification, and payments; this repo provides the **AAB**, privacy policy, and form answers.

| Field | Value |
|-------|--------|
| Application ID | `com.rse.app` |
| Display name | The RSE |
| Default language | English (US) |
| Category | Business (or Productivity) |
| Free / paid | Free |
| Privacy policy URL | **https://theservicesexchange.com/privacy-app.html** |
| Support URL | https://theservicesexchange.com/feedback.html |
| Marketing site | https://theservicesexchange.com |

---

## 1. One-time Console setup (human)

1. Open [Google Play Console](https://play.google.com/console) with a Google account.
2. Pay the one-time developer registration fee if not already registered.
3. Complete **Account details**, **Identity verification**, and **Payments profile** (even for free apps).
4. **Create app** → name **The RSE** → app/game: App → free → declarations as appropriate.
5. Accept Play policies / US export / ads declarations (this app does **not** currently show ads).

---

## 2. App signing

- Local upload keystore: `mobile/android/keystore/rse-upload.jks` (gitignored).
- Prefer **Play App Signing**: upload the AAB; Google holds the app signing key; keep your upload key backed up offline.
- Never lose `keystore.properties` / `.jks` — you need them for every update.

---

## 3. Build the release AAB (this repo)

```bash
export JAVA_HOME="/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
export ANDROID_HOME="$HOME/Android/sdk"
cd mobile
npm install
npx cap sync android
npm run bundle
# Output:
# android/app/build/outputs/bundle/release/app-release.aab
```

Copy for archives:

```bash
mkdir -p dist ../apk
cp android/app/build/outputs/bundle/release/app-release.aab dist/The-RSE-<versionName>.aab
```

Each Play upload must increase `versionCode` in `android/app/build.gradle`.

---

## 4. Store listing (draft copy)

**Short description** (≤80 chars):

> Request robot labor. Post jobs, track work, rate providers — demand app for The RSE.

**Full description**:

```
The RSE is the demand-side Android app for The Robot Services Exchange — an open marketplace for robot labor and operators.

• Post priced service requests
• Track open requests, active jobs, and completed work
• Rate providers when work is done
• Nearby map of open physical jobs (with privacy-aware pins)
• Account profile with shareable public link
• Optional contact discovery (opt-in, hashed identifiers only)
• Recurring auto-requests for routines like yardcare or cleaning
• Product feedback board

The app talks only to the public RSE API (rse-api.com). Payment for completed work is settled off-platform between you and the provider; the exchange does not escrow funds.

Privacy dials let you control how precise your location and profile appear on public surfaces.
```

**Graphics** (create in Console or design tools):

| Asset | Spec |
|-------|------|
| App icon | 512×512 PNG (from `mobile/resources/icon.png` / store icon) |
| Feature graphic | 1024×500 |
| Phone screenshots | min 2, up to 8 (1080×1920 or similar) |
| 7" / 10" tablet | optional |

Capture screenshots from an emulator or device: Auth, Request, Jobs, Nearby map, Account.

---

## 5. Data safety form (answers)

| Question | Answer |
|----------|--------|
| Collects personal info? | **Yes** |
| Location | Approximate (and precise if user grants GPS) — for Nearby; optional |
| Personal info | Name/username, email/phone if user opts into contact discovery or profile contact fields |
| Financial | No card numbers collected in-app today (payment method is free text for off-platform settlement) |
| Photos | Optional avatar upload only if user uses avatar API |
| Contacts | Yes, **optional**, user-initiated import / discovery |
| App activity | In-app interactions / marketplace posts |
| App info & performance | Crash/diagnostics via server logs |
| Device IDs | Not used for ads; standard auth tokens only |
| Data encrypted in transit? | **Yes** (HTTPS) |
| Users can request deletion? | **Yes** (Feedback / support) |
| Sold? | **No** |
| Shared for ads? | **No** |

Declare purposes: App functionality, Account management, Analytics (limited server logs).

---

## 6. Permissions justification (Console)

| Permission | Why |
|------------|-----|
| `INTERNET` | API + Mapbox tiles |
| `ACCESS_COARSE/FINE_LOCATION` | Optional Nearby “Use my location” |
| `READ_CONTACTS` | Optional Find friends import |
| `REQUEST_INSTALL_PACKAGES` | Sideload auto-update only; **Play installs skip APK self-update** and use Play updates |

If Play rejects `REQUEST_INSTALL_PACKAGES`, remove it from a Play-specific product flavor in a follow-up PR.

---

## 7. Content rating

Complete the IARC questionnaire in Console:

- No violence, sexual content, or gambling in-app.
- User-generated text (service descriptions, feedback) — select user-generated content if asked.
- Not primarily a social network; marketplace + optional discovery.

---

## 8. Release tracks

1. **Internal testing** — add your Gmail as tester; upload AAB; smoke-test login, bid, nearby, contacts permission.
2. **Closed testing** — optional wider group.
3. **Production** — after policy review.

Sideload APKs on the website can continue in parallel; Play builds report `fromPlayStore` and open the store listing for updates.

---

## 9. Checklist before first production submit

- [ ] Privacy policy live at https://theservicesexchange.com/privacy-app.html
- [ ] AAB built & signed (`versionCode` ≥ current Play)
- [ ] Store listing text + 2+ screenshots + feature graphic
- [ ] Data safety completed
- [ ] Content rating completed
- [ ] Target API meets Play requirement (currently compile/target **36**)
- [ ] Internal test install verified
- [ ] Support contact / feedback URL works

---

## 10. After approval

- Prefer Play as primary distribution link on the website when ready.
- Bump `versionCode` for every release; update `apk/version.json` for **sideload** users only.
- Stripe / in-app purchases (if ever) require Play Billing where applicable — marketplace job payments remain off-platform unless product changes.

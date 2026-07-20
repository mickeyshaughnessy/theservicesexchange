# The RSE Android (Capacitor)

Native Android shell that loads a **bundled demand-side SPA** from `www/`.  
The app talks **only** to **https://rse-api.com:5003** — it does **not** load theservicesexchange.com.

| | |
|---|---|
| **Application ID** | `com.rse.app` |
| **Display name** | The RSE |
| **Role** | Demand (buyer) only |
| **API** | `https://rse-api.com:5003` |

## Prerequisites

```bash
# JDK 21 required (Capacitor Android compiles with source 21)
brew install openjdk@21
export JAVA_HOME="/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"

# Android SDK
export ANDROID_HOME="$HOME/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
```

Create `android/local.properties` if missing:

```
sdk.dir=/Users/YOU/Android/sdk
```

## Signing (release APK)

`android/keystore.properties` and `android/keystore/*.jks` are **gitignored**.

```bash
mkdir -p android/keystore
keytool -genkeypair -v \
  -keystore android/keystore/rse-upload.jks \
  -alias rse \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass 'CHANGE_ME' \
  -keypass 'CHANGE_ME' \
  -dname "CN=The RSE, OU=Mobile, O=The Services Exchange, L=Colorado, ST=CO, C=US"
```

`android/keystore.properties`:

```
storeFile=keystore/rse-upload.jks
storePassword=CHANGE_ME
keyAlias=rse
keyPassword=CHANGE_ME
```

**Back up the keystore and passwords offline.**

## Build release APK

```bash
cd mobile
npm install
npx cap sync android
npm run assemble
# Output:
# android/app/build/outputs/apk/release/app-release.apk

mkdir -p ../apk ../mobile/dist
# Match versionName from android/app/build.gradle
cp android/app/build/outputs/apk/release/app-release.apk ../apk/The-RSE-1.1.0.apk
cp android/app/build/outputs/apk/release/app-release.apk dist/The-RSE-1.1.0.apk
# Update ../apk/version.json (versionCode, versionName, apkUrl, sha256) then deploy
```

## Auto-update (sideloaded APK)

The Android shell includes a native `AppUpdate` plugin. On launch the SPA:

1. Reads installed `versionCode` / `versionName`
2. Fetches `https://theservicesexchange.com/apk/version.json` (no-cache)
3. If remote `versionCode` is higher, downloads `apkUrl` and opens the system installer

**Android always shows a system Install confirmation** — fully silent install is not allowed for normal consumer apps. The download and installer launch are automatic.

### Shipping a new version

1. Bump **both** in `android/app/build.gradle`:
   - `versionCode` (integer, must increase every release)
   - `versionName` (e.g. `1.1.0`)
2. Build the release APK and copy to `apk/The-RSE-<versionName>.apk` (and `mobile/dist/` if desired).
3. Update `apk/version.json` **on the live website** (same deploy as the APK):

```json
{
  "versionCode": 2,
  "versionName": "1.1.0",
  "apkUrl": "https://theservicesexchange.com/apk/The-RSE-1.1.0.apk",
  "apkFile": "The-RSE-1.1.0.apk",
  "mandatory": false,
  "minSupportedVersionCode": 1,
  "releaseNotes": "What changed",
  "sha256": null
}
```

Optional `sha256` (hex) verifies the download before install:

```bash
shasum -a 256 apk/The-RSE-1.1.0.apk
```

4. Deploy `apk/version.json` + the new APK to the site. Existing app installs check on next cold start.

**Note:** Builds **without** this feature must install the first auto-update-capable APK once manually (website download). After that, later `versionCode` bumps self-update.

`mandatory: true` blocks the “Later” dismiss path for that `versionCode`.

Debug install (USB):

```bash
cd android && ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Project layout

```
mobile/
  capacitor.config.json   # appId + local webDir (no remote website URL)
  www/                    # demand SPA (API client)
  resources/              # icon/splash sources
  android/                # Capacitor Android project
```

## Regenerating launcher icons

```bash
cp ../icons/icon-512.png resources/icon.png
cp ../icons/icon-512.png resources/splash.png
npm run assets
npx cap sync android
```

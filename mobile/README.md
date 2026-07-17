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
cp android/app/build/outputs/apk/release/app-release.apk ../apk/The-RSE-1.0.0.apk
cp android/app/build/outputs/apk/release/app-release.apk dist/The-RSE-1.0.0.apk
```

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

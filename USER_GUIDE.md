# Flight Price Tracker — User Guide

Track flight prices, get alerts when fares drop, and open booking links — from your browser, iPhone home screen, or Android app.

**Live app (if deployed):** https://flightpricetracker-production.up.railway.app

---

## What this app does

- **Track routes** — Save origin, destination, dates, passengers, currency, and stop preference.
- **Check prices** — Tap **Refresh now** or wait for automatic checks (3× per day on the server).
- **Get alerts** — Email and/or push (Android) when a price drops below your last recorded price.
- **Book flights** — Open a booking link in your browser for the best quote found.
- **Private accounts** — Each user sees only their own routes.

---

## Choose how to use it

| Platform | Cost | Push alerts | How to install |
|----------|------|-------------|----------------|
| **Web browser** | Free | Email only | Open the Railway URL in any browser |
| **iPhone** | Free | Email only | Safari → Share → **Add to Home Screen** |
| **Android** | Free | Push + email | Install the APK (see [Android build guide](frontend/ANDROID_BUILD.txt)) |

> **iPhone note:** A native App Store / sideloaded iOS app requires a paid Apple Developer account ($99/year). The free path is the **web app** added to your home screen. See [frontend/IOS_BUILD.txt](frontend/IOS_BUILD.txt).

---

## 1. Create an account

1. Open the app (browser, home-screen icon, or APK).
2. On the sign-in screen, tap **Create account**.
3. Enter your **email** and a **password** (minimum 8 characters).
4. Tap **Register**.

You stay signed in until you log out or the session expires (default: 7 days).

**Sign in later:** Use the same email and password on **Sign in**.

---

## 2. Add a route to track

1. After login, tap **+ Add route** (or the add control on the routes screen).
2. Fill in:
   - **From** — Type a city or airport (e.g. `Sofia`, `SOF`). Pick from suggestions.
   - **To** — Same for destination (e.g. `London`, `LHR`).
   - **Depart** — Outbound date.
   - **Return** — Leave empty for one-way.
   - **Passengers** — Number of travelers.
   - **Currency** — USD, EUR, GBP, BGN, HUF, JPY, etc.
   - **Stops** — Any, direct only, or with layover.
3. Tap **Save** (or **Add**).

The route appears under **Your routes** with the latest price when available.

---

## 3. Refresh prices

### Manual refresh

Tap **Refresh now** on the main screen. The app asks the server to check all your active routes and update prices.

Status messages examples:

- `Checked 2 route(s). No drops.`
- `Checked 2 route(s). 1 price drop(s) detected!`
- `Refresh failed.` — See [Troubleshooting](#troubleshooting).

### Automatic checks

When the backend runs on Railway (or your server) with the scheduler enabled, prices are checked **3 times per day** at UTC hours **08:00, 14:00, and 20:00**. You do not need your phone or PC on for this.

---

## 4. Book a flight

1. Open a route from your list.
2. Tap **Book flight** (or the booking action).
3. Your browser opens with a link to book the quoted fare (provider depends on which API returned the best price).

Prices are indicative — always confirm on the airline or agency site before paying.

---

## 5. Notifications

Open **Settings** (gear icon) to control alerts separately:

| Setting | What it does |
|---------|----------------|
| **Email alerts** | Sends price-drop emails to your alert address |
| **Push alerts** | Sends instant notifications on Android |
| **Email for alerts** | Destination inbox (defaults to your account email) |

Both channels are **on by default**. Turn either off without affecting the other.

### Android (push)

1. Use a release APK built with Firebase configured (`google-services.json` on the build machine).
2. After sign-in, allow **notifications** when prompted.
3. Keep **Push alerts** enabled in Settings. The app registers your device with the server.

If you deny OS permission, you can still use the app; only push is disabled.

### Email

If the server admin configured **Resend** or SMTP (`RESEND_API_KEY` or SMTP settings on Railway), you receive email when a price drops and **Email alerts** is on in Settings.

### iPhone / web

Push is **not** available on iPhone without a paid native iOS build. Use **email alerts** or install the **Android APK** for push.

---

## 6. Edit or remove a route

1. Tap a route to open its details.
2. Change dates, passengers, currency, or stops, then save.
3. To stop tracking, delete the route from the detail screen.

Inactive or past routes may show no price until dates are updated.

---

## 7. Settings (developer / local testing only)

Production builds (Railway URL or release APK) connect automatically — you do **not** need to set an API URL.

If you run a **debug APK** against your own PC:

1. Open **Settings** (gear icon).
2. Set **API base URL**, for example:
   - Emulator: `http://10.0.2.2:8000/api`
   - Phone on same Wi‑Fi: `http://YOUR_PC_IP:8000/api`
3. Save and tap **Refresh now**.

---

## 8. iPhone — Add to Home Screen (step by step)

1. Open **Safari** (not Chrome — Add to Home Screen works best in Safari).
2. Go to: `https://flightpricetracker-production.up.railway.app` (or your deployed URL).
3. Sign in or register.
4. Tap the **Share** button (square with arrow).
5. Scroll and tap **Add to Home Screen**.
6. Name it **Flight Tracker** → **Add**.
7. Launch from your home screen — it opens full-screen like an app.

---

## 9. Android — Install the APK (step by step)

1. Build or obtain `app-release.apk` (see [frontend/ANDROID_BUILD.txt](frontend/ANDROID_BUILD.txt)).
2. Copy the APK to your phone (USB, cloud, or download from GitHub Releases if you publish one).
3. On the phone: enable **Install unknown apps** for your file manager or browser.
4. Open the APK → **Install**.
5. Open **Flight Tracker** → register or sign in.
6. Allow notifications if you want push alerts.

The release APK is preconfigured to use the production Railway API — no manual API URL needed.

---

## Troubleshooting

### “Failed to load routes” or “Refresh failed”

| Cause | Fix |
|-------|-----|
| No internet | Connect to Wi‑Fi or mobile data |
| Server down | Check `https://YOUR-URL.up.railway.app/api/health` in a browser — should return `{"status":"ok"}` |
| Wrong API URL (debug build) | Settings → correct `http://IP:8000/api` or production `https://.../api` |
| Session expired | Sign in again |

### App opens to a blank screen (Android)

- Reinstall a freshly built APK (`npm run cap:apk:release` after `npm run build`).
- Ensure you are not opening `index.html` from the filesystem — use the installed APK or the HTTPS web URL.

### No real prices / mock data

The server admin must set `FLIGHT_API_MODE=live` and add **RapidAPI** and/or **SerpApi** keys on Railway. Without keys, the backend uses mock quotes for testing.

### Push not working (Android)

- Confirm `google-services.json` was present when the APK was built.
- Confirm Railway has `FCM_CREDENTIALS_JSON` set (Firebase service account JSON, one line).
- Sign out and sign in again; accept notification permission.
- Check Railway logs for `POST /api/devices/register` after login.

### iPhone has no push

Expected without Apple Developer. Use email alerts or Android for push.

### Two users see each other’s routes

They should not — routes are per account. If this happens, report a bug; ensure each person uses their own login.

---

## Privacy and data

- Passwords are stored hashed on the server.
- Routes and price history are tied to your user account.
- FCM tokens (Android push) are stored to send you alerts.
- Booking links open third-party sites; their privacy policies apply.

---

## For administrators

To deploy your own instance or configure APIs, push notifications, and the scheduler, see:

- [DEPLOY.md](DEPLOY.md) — Railway, Docker, environment variables
- [frontend/FIREBASE_SETUP.txt](frontend/FIREBASE_SETUP.txt) — Firebase for Android push
- [frontend/ANDROID_BUILD.txt](frontend/ANDROID_BUILD.txt) — Build the APK
- [frontend/IOS_BUILD.txt](frontend/IOS_BUILD.txt) — iPhone without Apple Developer fee

---

## Quick reference

| Action | Where |
|--------|--------|
| Add route | Main screen → Add |
| Refresh all prices | **Refresh now** |
| Book | Route detail → Book flight |
| Log out | Settings or account menu |
| Health check | `GET /api/health` on your server |

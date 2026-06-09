# Cloud Deployment Guide

Deploy the Flight Price Tracker API + SPA to **Railway** (recommended).

## 1. Prerequisites

- Railway account: https://railway.app
- GitHub repository (this project)
- Optional: RapidAPI and SerpApi keys for real flight prices

## 2. Push to GitHub (first time)

```bash
cd FlightPriceTracker
git init
git add .
git commit -m "Initial commit: Flight Price Tracker"
gh repo create FlightPriceTracker --public --source=. --remote=origin --push
```

Or create the repo manually on GitHub, then:

```bash
git remote add origin https://github.com/YOUR_USER/FlightPriceTracker.git
git branch -M main
git push -u origin main
```

## 3. Create Railway project

1. Go to https://railway.app → **New Project** → **Deploy from GitHub repo**
2. Select `FlightPriceTracker` and authorize Railway if prompted
3. In the project, click **+ New** → **Database** → **PostgreSQL**
4. Click the web service → **Settings** → confirm **Dockerfile** build (root `Dockerfile`)
5. **Variables** tab → add env vars below; link `DATABASE_URL` from Postgres:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`

## 4. Environment variables

Set these on the web service (not Postgres):

```env
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
JWT_SECRET=<generate-a-long-random-string>
JWT_EXPIRE_HOURS=168
FLIGHT_API_MODE=live
RAPIDAPI_KEY=
SERPAPI_KEY=
CORS_ORIGINS=*
NOTIFICATIONS_ENABLED=true
RESEND_API_KEY=
FCM_CREDENTIALS_PATH=
SCHEDULER_ENABLED=true
SCHEDULER_HOURS=8,14,20
```

**PostgreSQL URL:** Railway provides `DATABASE_URL` as `postgresql://...`. SQLAlchemy + psycopg3 accept this format. If needed, prefix with `postgresql+psycopg://` (same connection string after the scheme).

**Real prices:** Set `RAPIDAPI_KEY` and/or `SERPAPI_KEY` and use `FLIGHT_API_MODE=live` (not `mock`). If mode is `mock`, keys are ignored. Without keys, mock providers are used.

**Skyscanner:** Requires a RapidAPI subscription to [Skyscanner Flights](https://rapidapi.com/skyscanner/api/skyscanner-flights). The client resolves IATA codes to Skyscanner PlaceIds automatically.

**Verify production:** `python backend/scripts/smoke_test_production.py` (set `PRODUCTION_URL` if needed).

**Verify Skyscanner locally:** `python backend/scripts/smoke_test_skyscanner.py` (needs `RAPIDAPI_KEY` in `.env`).

## 5. Deploy

Railway builds the Dockerfile (frontend + backend) and exposes HTTPS.

Your API base URL will be:

```
https://<your-service>.up.railway.app/api
```

Health check: `GET /api/health`

## 6. iPhone (no Apple Developer fee)

Open Safari on your iPhone:

```
https://<your-service>.up.railway.app
```

Tap **Share → Add to Home Screen**. The app runs full-screen from your home screen (PWA). Push notifications are not available on iPhone without a paid Apple Developer account and a native build; use Android for push or rely on email alerts.

See `frontend/IOS_BUILD.txt` for details.

## 7. Mobile app build (Android APK)

Set production API URL before building APK:

```env
# frontend/.env.production
VITE_API_BASE_URL=https://<your-service>.up.railway.app/api
```

```bash
cd frontend
npm run cap:apk
```

## 8. Firebase push (optional)

1. Firebase Console → service account → generate private key (JSON)
2. On Railway, set **`FCM_CREDENTIALS_JSON`** to the **entire Firebase JSON on one line** (must start with `{`)
   - From a `Railway_log/FCM_CRED.json` export: `python backend/scripts/extract_railway_fcm.py`
   - Paste contents of `Railway_log/FCM_RAILWAY_ONELINE.txt` (not the whole env export file)
3. Or set `FCM_CREDENTIALS_PATH` if you mount the JSON file in the container
4. Add `google-services.json` to `frontend/android/app/` and rebuild APK (`npm run cap:apk:release`)

## 9. Verify

- Register two users via the app — each sees only their routes
- Scheduler runs on the server (check logs at UTC 8/14/20)
- Price refresh works from phone without PC running

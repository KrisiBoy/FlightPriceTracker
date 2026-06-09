# Flight Price Tracker

Minimalist flight price tracker with FastAPI backend, Capacitor Android app, multi-user auth, and scheduled price-drop alerts.

## Stack

- **Backend:** Python, FastAPI, SQLModel, APScheduler
- **Frontend:** Vite, Tailwind CSS, Capacitor 7
- **Deploy:** Docker → [Railway](https://railway.app) (see [DEPLOY.md](DEPLOY.md))

## Local development

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm install
npm run build
```

Open http://localhost:8000

## Android APK

See [frontend/ANDROID_BUILD.txt](frontend/ANDROID_BUILD.txt)

## Railway deploy

1. Push this repo to GitHub
2. Railway → New Project → Deploy from GitHub
3. Add PostgreSQL + set variables from [DEPLOY.md](DEPLOY.md)

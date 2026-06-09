"""Extract Firebase credentials from Railway_log/FCM_CRED.json for Railway and local .env."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_PATH = PROJECT_ROOT / "Railway_log" / "FCM_CRED.json"
ONELINE_PATH = PROJECT_ROOT / "Railway_log" / "FCM_RAILWAY_ONELINE.txt"
SERVICE_ACCOUNT_PATH = PROJECT_ROOT / "Railway_log" / "firebase-service-account.json"
ENV_PATH = PROJECT_ROOT / ".env"

ENV_KEYS_FROM_EXPORT = (
    "APP_ENV",
    "FLIGHT_API_MODE",
    "RAPIDAPI_KEY",
    "SERPAPI_KEY",
    "JWT_SECRET",
    "JWT_EXPIRE_HOURS",
    "NOTIFICATIONS_ENABLED",
    "EMAIL_PROVIDER",
    "RESEND_API_KEY",
    "SMTP_FROM_EMAIL",
    "SMTP_PORT",
    "SCHEDULER_ENABLED",
    "SCHEDULER_HOURS",
    "CORS_ORIGINS",
)


def main() -> None:
    if not EXPORT_PATH.is_file():
        print(f"Missing export file: {EXPORT_PATH}", file=sys.stderr)
        sys.exit(1)

    export = json.loads(EXPORT_PATH.read_text(encoding="utf-8"))
    raw_fcm = export.get("FCM_CREDENTIALS_JSON", "").strip()
    if not raw_fcm:
        print("FCM_CREDENTIALS_JSON missing from export", file=sys.stderr)
        sys.exit(1)

    fcm = json.loads(raw_fcm)
    oneline = json.dumps(fcm, separators=(",", ":"))

    ONELINE_PATH.write_text(oneline, encoding="utf-8")
    SERVICE_ACCOUNT_PATH.write_text(json.dumps(fcm, indent=2), encoding="utf-8")

    env_lines: list[str] = []
    if ENV_PATH.is_file():
        env_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    def set_env_line(key: str, value: str) -> None:
        nonlocal env_lines
        line = f"{key}={value}"
        replaced = False
        for index, existing in enumerate(env_lines):
            if existing.startswith(f"{key}="):
                env_lines[index] = line
                replaced = True
                break
        if not replaced:
            env_lines.append(line)

    for key in ENV_KEYS_FROM_EXPORT:
        if key in export and export[key] != "":
            set_env_line(key, str(export[key]))
    set_env_line("FCM_CREDENTIALS_JSON", oneline)

    ENV_PATH.write_text("\n".join(env_lines).rstrip() + "\n", encoding="utf-8")

    print(f"Wrote Railway paste value: {ONELINE_PATH}")
    print(f"Wrote service account JSON: {SERVICE_ACCOUNT_PATH}")
    print(f"Updated local env: {ENV_PATH}")
    print()
    print("Railway: web service -> Variables -> FCM_CREDENTIALS_JSON")
    print("Paste the entire contents of FCM_RAILWAY_ONELINE.txt (one line, starts with {).")


if __name__ == "__main__":
    main()

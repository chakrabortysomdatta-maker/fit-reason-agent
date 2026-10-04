"""Change the demo login passwords to the values in .env (NEHA_PASSWORD, CHHAYA_PASSWORD). Touches nothing else.

Usage:  python scripts/set_passwords.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client  # noqa: E402

from core.config import settings  # noqa: E402

LOGINS = [("neha@dhaga-demo.test", "NEHA_PASSWORD", "Neha"),
          ("chhaya.gupta@dhaga-demo.test", "CHHAYA_PASSWORD", "Ms Chhaya Gupta")]

if __name__ == "__main__":
    if not settings.supabase_url or not settings.supabase_service_key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    admin = create_client(settings.supabase_url, settings.supabase_service_key)
    users = {u.email: u.id for u in admin.auth.admin.list_users()}
    for email, var, name in LOGINS:
        password = os.getenv(var, "")
        if len(password) < 8:
            sys.exit(f"{var} in .env must be at least 8 characters.")
        if email not in users:
            sys.exit(f"No login found for {name}. Run scripts/setup_db.py once first.")
        admin.auth.admin.update_user_by_id(users[email], {"password": password})
        print(f"password updated: {name}")

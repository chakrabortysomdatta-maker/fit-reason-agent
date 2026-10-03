"""One-time setup: create tables, views and access rules, load sample data, create the two demo logins.

Usage:  python scripts/setup_db.py            (safe to re-run: sample data is reloaded from scratch)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg  # noqa: E402
from supabase import create_client  # noqa: E402

import sample_data  # noqa: E402
from core.config import settings  # noqa: E402

LOAD_ORDER = [
    ("vendors", "vendor_id, name, city"),
    ("size_charts", "chart_id, size, bust_in, waist_in, length_in"),
    ("category_size_medians", "product_type, size, bust_in, waist_in, length_in"),
    ("skus", "sku_id, style_id, vendor_id, category, product_type, name, colour, fabric, price_inr, chart_id, status, launched_on"),
    ("customers", "customer_id, city, tier, phone_masked"),
    ("orders", "order_id, customer_id, placed_at, payment_mode, fc, courier, pin_zone, order_value_inr, status"),
    ("order_lines", "line_id, order_id, sku_id, size, qty, price_inr"),
    ("order_events", "order_id, status, at"),
    ("returns", "return_id, line_id, reason_dropdown, other_text, raised_at, status, refund_amount_inr, refunded_at"),
    ("tickets", "ticket_id, channel, customer_id, order_id, body, created_at"),
    ("stage_targets", "stage, target_days"),
    ("transit_targets", "pin_zone, max_days"),
    ("category_weights", "category, weight"),
    ("policies", "policy_key, body"),
    ("app_settings", "key, value"),
]
WIPE = ["draft_reviews", "guidance_drafts", "issue_actions", "issue_titles", "item_tags", "runs", "tickets", "returns",
        "order_events", "order_lines", "orders", "customers", "skus", "size_charts", "category_size_medians", "vendors",
        "stage_targets", "transit_targets", "category_weights", "policies", "app_settings"]

USERS = [
    ("neha@dhaga-demo.test", "NEHA_PASSWORD", "Neha", "category_head"),
    ("chhaya.gupta@dhaga-demo.test", "CHHAYA_PASSWORD", "Ms Chhaya Gupta", "cx_reviewer"),
]


def run_sql(conn) -> None:
    for name in ["01_schema.sql", "02_views.sql", "03_security.sql"]:
        conn.execute((ROOT / "db" / name).read_text(encoding="utf-8"))
        print(f"applied {name}")


def load_sample(conn) -> None:
    data = sample_data.generate()
    conn.execute("truncate " + ", ".join(WIPE) + " restart identity cascade")
    for table, cols in LOAD_ORDER:
        with conn.cursor().copy(f"copy {table} ({cols}) from stdin") as cp:
            for row in data[table]:
                cp.write_row(row)
        print(f"loaded {len(data[table]):5} {table}")


def create_users(conn) -> None:
    import os

    admin = create_client(settings.supabase_url, settings.supabase_service_key)
    existing = {u.email: u.id for u in admin.auth.admin.list_users()}
    for email, pw_var, name, role in USERS:
        password = os.getenv(pw_var)
        if not password:
            sys.exit(f"Set {pw_var} in .env first.")
        if email in existing:
            uid = existing[email]
            admin.auth.admin.update_user_by_id(uid, {"password": password})
        else:
            uid = admin.auth.admin.create_user({"email": email, "password": password, "email_confirm": True}).user.id
        conn.execute("insert into profiles (user_id, display_name, role) values (%s,%s,%s) "
                     "on conflict (user_id) do update set display_name = excluded.display_name, role = excluded.role",
                     (uid, name, role))
        print(f"login ready: {name} ({role})")


if __name__ == "__main__":
    missing = [k for k in ("supabase_url", "supabase_service_key", "supabase_db_url") if not getattr(settings, k)]
    if missing:
        sys.exit("Missing in .env: " + ", ".join(m.upper() for m in missing))
    with psycopg.connect(settings.supabase_db_url, autocommit=True) as conn:
        run_sql(conn)
        load_sample(conn)
        create_users(conn)
        print("order stages:", conn.execute("select refresh_order_stages()").fetchone()[0])
    print("Database ready. Next: python scripts/run_pipeline.py")

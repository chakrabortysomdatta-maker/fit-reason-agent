"""Sign-in and the per-user Supabase client. Queries run as the signed-in user, so row-level security applies."""
from typing import Optional

import streamlit as st
from supabase import Client, create_client

from core.config import settings

# Usernames shown on the login screen -> Supabase Auth emails (created by scripts/setup_db.py)
USERNAMES = {"neha": "neha@dhaga-demo.test", "chhaya.gupta": "chhaya.gupta@dhaga-demo.test"}

ROLE_SCREENS = {
    "category_head": ["queue", "scorecard"],
    "supply_chain": ["scorecard"],
    "cx_reviewer": ["guidance"],
}
ROLE_LABEL = {
    "category_head": "Category Head",
    "cx_reviewer": "CX reviewer · shadow mode",
    "supply_chain": "Supply Chain",
}


def _anon() -> Client:
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def sign_in(username: str, password: str) -> Optional[str]:
    """Returns an error message, or None on success."""
    email = USERNAMES.get(username.strip().lower(), username.strip())
    client = _anon()
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        return "Wrong username or password."
    client.postgrest.auth(res.session.access_token)
    profile = client.table("profiles").select("display_name, role").eq("user_id", res.user.id).execute().data
    if not profile:
        return "This account has no role yet. Ask the admin to set one up."
    st.session_state.user = {
        "id": res.user.id,
        "name": profile[0]["display_name"],
        "role": profile[0]["role"],
        "access_token": res.session.access_token,
        "refresh_token": res.session.refresh_token,
    }
    return None


DEMO_ROLES = {"neha": ("neha", "neha_password"), "chhaya": ("chhaya.gupta", "chhaya_password")}


def demo_sign_in(who: str) -> Optional[str]:
    """Demo mode: sign in server-side as Neha or Ms Chhaya Gupta. The password never reaches the browser,
    and the database still applies that person's access rules."""
    username, attr = DEMO_ROLES.get(who, DEMO_ROLES["neha"])
    return sign_in(username, getattr(settings, attr))


def sign_out() -> None:
    st.session_state.pop("user", None)


def user() -> Optional[dict]:
    return st.session_state.get("user")


def db() -> Client:
    """A Supabase client acting as the signed-in user."""
    u = user()
    client = _anon()
    if u:
        try:
            client.auth.set_session(u["access_token"], u["refresh_token"])
            session = client.auth.get_session()
            if session and session.access_token != u["access_token"]:  # token was refreshed
                u["access_token"], u["refresh_token"] = session.access_token, session.refresh_token
        except Exception:
            pass
        client.postgrest.auth(u["access_token"])
    return client


def require(screen: str) -> dict:
    """Stop the page unless the signed-in role may see this screen."""
    u = user()
    if not u:
        st.stop()
    if screen not in ROLE_SCREENS.get(u["role"], []):
        st.error("You don't have access to this screen.")
        st.stop()
    return u


def fetch_all(table: str, columns: str = "*", page: int = 1000) -> list[dict]:
    """Supabase returns at most 1,000 rows per request; read every page."""
    client, rows, start = db(), [], 0
    while True:
        chunk = client.table(table).select(columns).range(start, start + page - 1).execute().data
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        start += page

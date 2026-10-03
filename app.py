"""Fit-Reason Agent: Streamlit entry point. Sign in, then see only the screens your role allows."""
import streamlit as st

from core.config import settings
from core.session import ROLE_SCREENS, sign_in, user
from core.ui import CSS

st.set_page_config(page_title="Fit-Reason · Dhaga & Co.", page_icon="🧵", layout="wide",
                   initial_sidebar_state="auto")
st.markdown(CSS, unsafe_allow_html=True)

PERSONAS = {
    "neha": ("Neha", "Category Head", "Analyses why orders come back and which vendors cause delays.",
             "Priority queue · Delay scorecard"),
    "chhaya.gupta": ("Ms Chhaya Gupta", "CX reviewer · shadow mode",
                     "Rates suggested Hinglish replies before any customer sees one.", "Guidance review"),
}


def login_page() -> None:
    st.markdown("### Dhaga & Co. · Fit-Reason")
    st.markdown("## Sign in")
    st.caption("Choose your role. You will only see the screens your role needs.")
    if not settings.supabase_url or not settings.supabase_anon_key:
        st.error("The app is not connected to its database yet (SUPABASE_URL / SUPABASE_ANON_KEY missing).")
        st.stop()

    who = st.radio("Role", list(PERSONAS), horizontal=True, label_visibility="collapsed",
                   format_func=lambda k: f"{PERSONAS[k][0]} · {PERSONAS[k][1]}")
    name, role, blurb, screens = PERSONAS[who]
    st.info(f"**{name}** — {blurb}\n\nYou will see: {screens}.")
    with st.form("login"):
        username = st.text_input("Username", value=who)
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button(f"Sign in as {name}", type="primary", use_container_width=True)
    if submitted:
        err = sign_in(username, password)
        if err:
            st.error(err)
        else:
            st.rerun()
    st.caption("Internal pilot · nothing is sent to customers · sample data")


PAGES = {
    "queue": st.Page("views/queue.py", title="Priority queue", icon=":material/list:", url_path="queue"),
    "scorecard": st.Page("views/scorecard.py", title="Delay scorecard", icon=":material/local_shipping:",
                         url_path="scorecard"),
    "guidance": st.Page("views/guidance.py", title="Guidance review", icon=":material/chat:", url_path="guidance"),
}

u = user()
if not u:
    st.navigation([st.Page(login_page, title="Sign in", icon=":material/login:")], position="hidden").run()
else:
    allowed = [PAGES[s] for s in ROLE_SCREENS.get(u["role"], [])]
    st.sidebar.markdown("**Dhaga & Co.**  \n### Fit-Reason")
    st.sidebar.caption(f"Signed in: {u['name']} · {len(allowed)} screen{'s' if len(allowed) != 1 else ''}")
    st.sidebar.caption("Shadow mode · internal only · sample data")
    st.navigation(allowed).run()

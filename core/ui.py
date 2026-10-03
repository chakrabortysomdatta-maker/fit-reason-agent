"""Shared look: colours from the UX design, user badge, KPI tiles. Layout stacks on phones."""
import html

import streamlit as st

from core.session import ROLE_LABEL, sign_out, user

TEAL, INK, MUTED, RED, AMBER, GREEN = "#0E6B63", "#1B1F1D", "#5B625E", "#A61B1B", "#8A4206", "#1E6B35"
AVATAR = {"category_head": TEAL, "cx_reviewer": AMBER, "supply_chain": "#3D4440"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
html, body, [class*="st-"], .stMarkdown { font-family: 'IBM Plex Sans', system-ui, sans-serif; }
.block-container { padding-top: 1.2rem; max-width: 1280px; }
[data-testid="stSidebar"] { background: #17211F; }
[data-testid="stSidebar"] * { color: #E6EBE8 !important; }
.fr-badge { display:flex; align-items:center; gap:10px; justify-content:flex-end; }
.fr-avatar { width:36px; height:36px; border-radius:18px; color:#fff; display:flex; align-items:center;
             justify-content:center; font-weight:600; font-size:13px; flex:none; }
.fr-who { display:flex; flex-direction:column; line-height:1.2; }
.fr-who b { font-size:14px; } .fr-who span { font-size:12px; color:#5B625E; }
.fr-kpi { background:#fff; border:1px solid #DADDD8; border-radius:8px; padding:12px 14px; height:100%; }
.fr-kpi .l { font-size:12px; color:#5B625E; } .fr-kpi .v { font-size:24px; font-weight:600; }
.fr-kpi .n { font-size:12px; color:#5B625E; }
.fr-banner { padding:10px 14px; border-radius:8px; background:#FDF1E3; border:1px solid #E9C48F; color:#6E3605;
             font-size:14px; margin-bottom:8px; }
.fr-chip { display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:500;
           background:#F0F1EE; color:#3D4440; margin:0 4px 4px 0; }
.fr-quote { background:#F4F5F2; border-radius:6px; padding:8px 12px; margin-bottom:8px; }
.fr-quote .q { font-size:14px; } .fr-quote .m { font-size:12px; color:#5B625E; }
.fr-reply { background:#F4F5F2; border-radius:6px; padding:12px 14px; font-size:16px; line-height:1.55; }
.fr-struck { text-decoration: line-through; color:#5B625E; }
.fr-mono { font-family:'IBM Plex Mono', monospace; }
@media (max-width: 640px) { .fr-kpi .v { font-size:20px; } .block-container { padding-left:12px; padding-right:12px; } }
</style>
"""


def setup_page(title: str) -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str = "") -> None:
    """Page title on the left, signed-in person on the right (wraps under the title on a phone)."""
    u = user()
    left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        st.markdown(f"## {html.escape(title)}")
        if subtitle:
            st.caption(subtitle)
    with right:
        initials = "".join(w[0] for w in u["name"].replace("Ms ", "").split()[:2]).upper()
        st.markdown(
            f"""<div class="fr-badge" aria-label="Signed in as {html.escape(u['name'])}">
                 <div class="fr-avatar" style="background:{AVATAR.get(u['role'], TEAL)}">{initials}</div>
                 <div class="fr-who"><b>{html.escape(u['name'])}</b><span>{ROLE_LABEL.get(u['role'], u['role'])}</span></div>
               </div>""",
            unsafe_allow_html=True,
        )
        if st.button("Sign out", key="signout", use_container_width=False):
            sign_out()
            st.rerun()


def kpis(items: list[tuple[str, str, str]], color: dict | None = None) -> None:
    """items = [(label, value, note)]. Two per row on phones, all in one row on desktop."""
    cols = st.columns(len(items))
    for col, (label, value, note) in zip(cols, items):
        c = (color or {}).get(label, INK)
        col.markdown(f"""<div class="fr-kpi"><div class="l">{html.escape(label)}</div>
                         <div class="v" style="color:{c}">{html.escape(str(value))}</div>
                         <div class="n">{html.escape(note)}</div></div>""", unsafe_allow_html=True)


def chips(*labels: str) -> str:
    return "".join(f'<span class="fr-chip">{html.escape(str(l))}</span>' for l in labels if l)


def quote(text: str, meta: str) -> None:
    st.markdown(f'<div class="fr-quote"><div class="q">"{html.escape(text)}"</div>'
                f'<div class="m">{html.escape(meta)}</div></div>', unsafe_allow_html=True)


def shadow_note() -> None:
    st.sidebar.markdown("**Shadow mode** · internal only · sample data")

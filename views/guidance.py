"""Guidance review (shadow mode): suggested replies in the customer's language, rated by a CX reviewer. Nothing is sent."""
import html
import json

import streamlit as st

from core import garments
from core.session import db, require
from core.ui import AMBER, GREEN, RED, chips, header

u = require("guidance")
client = db()

header("Guidance review", "Rate each suggestion. Ratings decide when replies can go to customers.")
st.markdown('<div class="fr-banner"><b>Shadow mode.</b> Suggestions are rated here and never sent. '
            'Go-live needs 2 weeks of ≥ 90% "Send as-is" and zero wrong facts.</div>', unsafe_allow_html=True)

STATUS = {"drafted": ("Drafted", GREEN), "needs_human": ("Needs a person", RED), "unclassified": ("Unclassified", RED)}

# ---- live box
with st.form("try"):
    c1, c2, c3 = st.columns([5, 2, 1], vertical_alignment="bottom")
    message = c1.text_input("Try a customer message", placeholder="size chart mein M likha tha par bahut tight hai, kya L mil sakta hai?")
    order_hint = c2.text_input("Order ID (optional)", placeholder="DH-48213")
    run = c3.form_submit_button("Run", type="primary", use_container_width=True)
if run and message.strip():
    from core.llm import ModelCallsDisabled
    from core.pipeline import try_message

    with st.spinner("Reading the message, pulling facts, drafting and checking…"):
        try:
            result = try_message(message.strip(), order_hint.strip() or None)
            st.session_state.selected_draft = str(result["draft_id"])
        except ModelCallsDisabled as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"The system could not process this message: {exc}")

# ---- list + detail
drafts = client.table("guidance_drafts").select("*").order("created_at", desc=True).limit(60).execute().data
reviews = client.table("draft_reviews").select("draft_id,rating,at").execute().data
rated = {r["draft_id"] for r in reviews}
# Suggestions waiting for a rating first, then the ones handed to a person, then rated ones.
drafts.sort(key=lambda d: (d["draft_id"] in rated, d["status"] != "drafted"))
if not drafts:
    st.info("No suggestions yet. Run the reading pipeline, or try a message above.")
    st.stop()

left, right = st.columns([2, 3], gap="medium")
with left:
    to_rate = sum(1 for d in drafts if d["status"] == "drafted" and d["draft_id"] not in rated)
    st.markdown(f"#### Messages · {to_rate} to rate")
    ids = [d["draft_id"] for d in drafts]
    default = st.session_state.get("selected_draft")
    idx = ids.index(default) if default in ids else 0

    def label(i):
        d = drafts[ids.index(i)]
        s = "Rated" if i in rated else STATUS[d["status"]][0]
        text = d["message_text"] if len(d["message_text"]) < 70 else d["message_text"][:67] + "…"
        order = d["facts"].get("order") if isinstance(d["facts"], dict) else None
        ref = f"{order['order_id']} · " if isinstance(order, dict) else ""
        return f"{text}  ·  {ref}{(d['category'] or '—').replace('_', ' ')} · {s}"

    with st.container(height=560, border=False):  # the list scrolls on its own; the reply stays in view
        chosen = st.radio("Messages", ids, index=idx, format_func=label, label_visibility="collapsed")
    st.session_state.selected_draft = chosen

with right:
    d = next(x for x in drafts if x["draft_id"] == chosen)
    st.markdown(f"**Customer wrote** · {d['ticket_id'] or 'typed in Try a message'}")
    st.markdown(f"<p style='font-size:17px'>“{html.escape(d['message_text'])}”</p>", unsafe_allow_html=True)
    order = d["facts"].get("order") if isinstance(d["facts"].get("order"), dict) else None
    if order:
        kind = next((k for w, k in [("kurt", "kurta"), ("anarkali", "kurta"), ("frock", "frock"), ("dress", "dress"),
                                    ("palazzo", "palazzo"), ("dupatta", "dupatta"), ("shirt", "kids_shirt"),
                                    ("tee", "tshirt")] if w in order["product"].lower()), "kurta")
        st.markdown(f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">'
                    f'{garments.svg(kind, None, 44)}<div><b>{html.escape(order["product"])}</b><br>'
                    f'<span style="color:#5B625E;font-size:13px">Order {order["order_id"]} · size '
                    f'{order.get("size_bought", "—")}</span></div></div>', unsafe_allow_html=True)
    st.markdown(chips((d["category"] or "—").replace("_", " "), d["language"]), unsafe_allow_html=True)

    with st.expander("Facts the reply may use (from Dhaga's records, not the model)", expanded=False):
        facts = d["facts"] or {}
        order = facts.get("order")
        if isinstance(order, dict):
            st.markdown("**Order**  \n" + "  \n".join(f"{k.replace('_', ' ')}: {v}" for k, v in order.items()))
        elif order:
            st.write(order)
        if facts.get("size_chart_inches"):
            st.markdown("**Size chart (inches)**  \n" + "  \n".join(
                f"{size}: " + ", ".join(f"{k.replace('_in', '')} {v}" for k, v in m.items())
                for size, m in facts["size_chart_inches"].items()))
        if facts.get("return"):
            st.markdown("**Return**  \n" + "  \n".join(f"{k.replace('_', ' ')}: {v}" for k, v in facts["return"].items()))
        if facts.get("policies"):
            st.markdown("**Policies**  \n" + "  \n".join(f"{k}: {v}" for k, v in facts["policies"].items()))

    attempts = d["attempts"] if isinstance(d["attempts"], list) else json.loads(d["attempts"] or "[]")
    if d["status"] == "drafted":
        st.markdown(f"**Suggested reply** · <span style='color:{GREEN};font-weight:600'>✓ Fact-check passed</span>",
                    unsafe_allow_html=True)
        st.markdown(f"<div class='fr-reply'>{html.escape(d['reply'])}</div>", unsafe_allow_html=True)
        st.caption(f"Cost ₹{float(d['cost_inr']):.2f} · not a canned reply")

        st.markdown("**Your rating**")
        mine = [r for r in reviews if r["draft_id"] == d["draft_id"]]
        if mine:
            st.success(f"Rated: {mine[-1]['rating'].replace('_', ' ')}. Nothing was sent to the customer.")
        note = st.text_area("Note or corrected reply (optional)", key=f"note-{d['draft_id']}", height=80)
        b1, b2, b3 = st.columns(3)
        rating = None
        if b1.button("Send as-is", key="r1", use_container_width=True, type="primary"):
            rating = "send_as_is"
        if b2.button("Needs edit", key="r2", use_container_width=True):
            rating = "needs_edit"
        if b3.button("Wrong", key="r3", use_container_width=True):
            rating = "wrong"
        if rating:
            try:
                client.table("draft_reviews").insert({"draft_id": d["draft_id"], "rating": rating,
                                                      "edited_text": note or None, "reviewer_name": u["name"]}).execute()
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save the rating: {exc}")
    else:
        for n, a in enumerate(attempts, 1):
            st.markdown(f"<div class='fr-quote'><div class='m'><b>Attempt {n} · rejected</b></div>"
                        f"<div class='q fr-struck'>{html.escape(a.get('reply') or '')}</div>"
                        f"<div class='m' style='color:{RED}'>{html.escape(' · '.join(a.get('problems') or []))}</div></div>",
                        unsafe_allow_html=True)
        st.error(f"**{STATUS[d['status']][0]}:** {d['needs_human_reason'] or 'no safe reply possible'}. "
                 "No suggestion is offered for rating.")
        st.button("Assign to an agent", type="primary")

    week = [r for r in reviews]
    if week:
        share = round(100 * sum(r["rating"] == "send_as_is" for r in week) / len(week))
        st.caption(f"Nothing is sent to customers. Rated so far: {len(week)} · {share}% Send as-is")

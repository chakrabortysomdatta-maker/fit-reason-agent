"""Neha's priority queue: grouped issues, worst first, with the evidence and her actions."""
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from core.session import db, require
from core.ui import AMBER, GREEN, RED, chips, header, kpis, quote

u = require("queue")
client = db()

CATEGORY_LABEL = {"fit": "Fit", "quality": "Quality", "colour_mismatch": "Colour", "wismo": "WISMO"}
ACTIONS = {"fix": "Fix size chart / listing", "escalate": "Escalate to vendor", "monitor": "Monitor",
           "wrong_tag": "Wrong tag"}


def load():
    issues = client.table("v_issues").select("*").execute().data
    tags = client.table("item_tags").select("source,item_id,category,route").execute().data
    returns = client.table("returns").select("return_id,reason_dropdown").execute().data
    run = client.table("runs").select("cost_inr,finished_at,items").eq("kind", "tag").eq("status", "done") \
        .order("started_at", desc=True).limit(1).execute().data
    return issues, tags, returns, run


issues, tags, returns, run = load()
last = run[0] if run else None
when = ""
if last and last.get("finished_at"):
    when = datetime.fromisoformat(last["finished_at"]).astimezone(timezone.utc).strftime("%d %b, %H:%M UTC")
header("Priority queue", f"{len(tags)} returns and tickets read" + (f" · last run {when}" if when else ""))

if not issues:
    st.info("No issues yet. Run the reading pipeline to tag returns and tickets.")
    st.stop()

# ---- KPI strip (all arithmetic here, in code)
return_tags = {t["item_id"]: t for t in tags if t["source"] == "return"}
specific = sum(1 for r in returns if r["reason_dropdown"] != "Other"
               or (return_tags.get(r["return_id"], {}).get("route") == "trusted"
                   and return_tags[r["return_id"]]["category"] != "other"))
before = sum(1 for r in returns if r["reason_dropdown"] != "Other")
pct = round(100 * specific / len(returns)) if returns else 0
open_issues = [i for i in issues if not i["monitor"]]
check_tag = [t for t in tags if t["route"] == "check_tag"]
unclassified = [t for t in tags if t["route"] == "unclassified"]
kpis([
    ("Returns with a specific reason", f"{pct}%", f"was {round(100 * before / len(returns)) if returns else 0}% before tagging"),
    ("Open issues", str(len(open_issues)), f"{len(issues) - len(open_issues)} more on Monitor"),
    ("Check tag (unsure)", str(len(check_tag)), "waiting for a person"),
    ("Unclassified", str(len(unclassified)), "failed twice · shown, not dropped"),
    ("Last run's model cost", f"₹{last['cost_inr']:.2f}" if last else "—", f"{last['items']} items" if last else ""),
], color={"Unclassified": RED if unclassified else None, "Returns with a specific reason": GREEN})
st.write("")

# ---- ranked issues
issues.sort(key=lambda i: (i["monitor"], -(i["score"] or 0)))
df = pd.DataFrame([{
    "#": n + 1,
    "Issue": i["title"],
    "Category": CATEGORY_LABEL.get(i["category"], i["category"]),
    "Vendor": f"{i['vendor_id']} {i['vendor_city'] or ''}".strip() if i["vendor_id"] else "—",
    "Items 7d": i["items_7d"],
    "Trend": f"{float(i['trend']):.1f}×",
    "Score": "Monitor" if i["monitor"] else int(i["score"]),
    "Last action": (i["last_action"] or "").replace("_", " "),
} for n, i in enumerate(issues)])

left, right = st.columns([3, 2], gap="medium")
with left:
    st.markdown("#### Issues, ranked by score")
    st.caption("score = items in 7 days × category weight × trend × urgency · fewer than 5 items stay on Monitor")
    picked = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun",
                          selection_mode="single-row", key="issues",
                          column_config={"Issue": st.column_config.TextColumn(width="large")})
    rows = picked.selection.rows if picked and picked.selection else []
    sel = issues[rows[0]] if rows else issues[0]

with right:
    st.markdown(f"<span style='color:#0E6B63;font-weight:600;font-size:12px'>"
                f"{'MONITOR' if sel['monitor'] else 'SCORE ' + str(int(sel['score']))}</span>", unsafe_allow_html=True)
    st.markdown(f"### {sel['title']}")
    st.markdown(chips(f"{sel['items_7d']} items this week", f"{sel['from_returns']} returns",
                      f"{sel['from_tickets']} tickets", sel["vendor_id"], *(sel["skus"] or [])[:3]),
                unsafe_allow_html=True)

    # size chart vs category median for the first SKU (fit issues)
    if sel["category"] == "fit" and sel["skus"]:
        sku = client.table("skus").select("chart_id,product_type").eq("sku_id", sel["skus"][0]).execute().data
        if sku:
            chart = client.table("size_charts").select("*").eq("chart_id", sku[0]["chart_id"]).execute().data
            med = client.table("category_size_medians").select("*").eq("product_type", sku[0]["product_type"]).execute().data
            med_by = {m["size"]: m for m in med}
            gaps = []
            for c in chart:
                m = med_by.get(c["size"], {})
                for dim in ("bust_in", "waist_in", "length_in"):
                    if c.get(dim) is not None and m.get(dim) is not None:
                        gaps.append((dim, c["size"], float(c[dim]), float(m[dim])))
            if gaps:
                dim = max({g[0] for g in gaps}, key=lambda d: max(abs(g[2] - g[3]) for g in gaps if g[0] == d))
                rows_ = [g for g in gaps if g[0] == dim]
                st.markdown(f"**Size chart vs category median ({dim.replace('_in', '')}, inches)**")
                st.dataframe(pd.DataFrame({
                    "Size": [g[1] for g in rows_],
                    sel["vendor_id"] or "Vendor": [g[2] for g in rows_],
                    "Median": [g[3] for g in rows_],
                    "Gap": [f"{g[2] - g[3]:+.1f}" for g in rows_],
                }), hide_index=True, use_container_width=True)

    # customer quotes (evidence)
    q = client.table("item_tags").select("source,item_id,sku_id,evidence_span").eq("route", "trusted") \
        .eq("category", sel["category"])
    q = q.eq("sub_tag", sel["sub_tag"]) if sel["sub_tag"] else q.is_("sub_tag", "null")
    q = q.eq("vendor_id", sel["vendor_id"]) if sel["vendor_id"] else q.is_("vendor_id", "null")
    ev = q.order("tagged_at", desc=True).limit(3).execute().data
    st.markdown(f"**What customers said ({len(ev)} of {sel['items_7d']})**")
    for e in ev:
        if e["source"] == "return":
            r = client.table("returns").select("other_text").eq("return_id", e["item_id"]).execute().data
            text = r[0]["other_text"] if r else e["evidence_span"]
        else:
            t = client.table("tickets").select("body").eq("ticket_id", e["item_id"]).execute().data
            text = t[0]["body"] if t else e["evidence_span"]
        quote(text, f"{'Return' if e['source'] == 'return' else 'Ticket'} · {e['item_id']} · {e['sku_id'] or ''}")

    c1, c2 = st.columns(2)
    clicked = None
    for i, (key, label) in enumerate(ACTIONS.items()):
        col = c1 if i % 2 == 0 else c2
        if col.button(label if key != "escalate" else f"Escalate to {sel['vendor_id'] or 'vendor'}",
                      key=f"act-{key}", type="primary" if key == "fix" else "secondary", use_container_width=True):
            clicked = key
    if clicked:
        try:
            client.table("issue_actions").insert({"issue_key": sel["issue_key"], "action": clicked,
                                                  "actor_name": u["name"]}).execute()
            st.success(f"Saved: {ACTIONS[clicked]} · by {u['name']}")
        except Exception as exc:
            st.error(f"Could not save the action: {exc}")
    if not sel["monitor"]:
        st.caption(f"{int(sel['score'])} = {sel['items_7d']} items × weight {float(sel['weight']):g} × trend "
                   f"{float(sel['trend']):.1f} × urgency {1 + 0.5 * float(sel['share_high']):.2f}")

# ---- unsure tags, shown not hidden
with st.expander(f"Check tag: {len(check_tag)} unsure · Unclassified: {len(unclassified)}"):
    unsure = check_tag + unclassified
    if unsure:
        ids_r = [t["item_id"] for t in unsure if t["source"] == "return"]
        ids_t = [t["item_id"] for t in unsure if t["source"] == "ticket"]
        texts = {r["return_id"]: r["other_text"] for r in
                 (client.table("returns").select("return_id,other_text").in_("return_id", ids_r).execute().data if ids_r else [])}
        texts.update({t["ticket_id"]: t["body"] for t in
                      (client.table("tickets").select("ticket_id,body").in_("ticket_id", ids_t).execute().data if ids_t else [])})
        st.dataframe(pd.DataFrame([{"Item": t["item_id"], "Text": texts.get(t["item_id"], ""),
                                    "Guess": t["category"] or "—", "Status": t["route"].replace("_", " ")}
                                   for t in unsure]), hide_index=True, use_container_width=True)
    else:
        st.write("Nothing waiting.")

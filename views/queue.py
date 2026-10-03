"""Neha's priority queue: grouped issues, worst first, with the evidence and her actions."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from core import icons
from core.session import db, fetch_all, require
from core.ui import AMBER, GREEN, RED, chips, header, kpis, quote

u = require("queue")
client = db()

CATEGORY_LABEL = {"fit": "Fit", "quality": "Quality", "colour_mismatch": "Colour", "wismo": "WISMO"}
ACTIONS = {"fix": "Fix size chart / listing", "escalate": "Escalate to vendor", "monitor": "Monitor",
           "wrong_tag": "Wrong tag"}


def load():
    issues = client.table("v_issues").select("*").execute().data
    tags = fetch_all("item_tags", "source,item_id,category,route")
    returns = fetch_all("returns", "return_id,reason_dropdown")
    skus = {s["sku_id"]: s for s in fetch_all("skus", "sku_id,product_type,name")}
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    run = client.table("runs").select("cost_inr,finished_at,items,kind").gte("started_at", since) \
        .order("started_at", desc=True).execute().data
    return issues, tags, returns, run, skus


issues, tags, returns, run, skus = load()
last = next((r for r in run if r["kind"] == "tag" and r.get("finished_at")), None)
week_cost = sum(float(r["cost_inr"]) for r in run)
week_items = sum(r["items"] for r in run if r["kind"] == "tag")
when = ""
if last:
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
    ("Model cost, last 7 days", f"₹{week_cost:.2f}", f"{week_items} items read · Groq"),
], color={"Unclassified": RED if unclassified else None, "Returns with a specific reason": GREEN})
st.write("")

# ---- ranked issues
issues.sort(key=lambda i: (i["monitor"], -(i["score"] or 0)))
def issue_icon(i):
    """Garment icon for product issues; vendor / warehouse / courier icon for delivery issues."""
    if i["category"] == "wismo":
        return icons.STAGE_ICON.get(i["sub_tag"], "📦")
    types = [skus[s]["product_type"] for s in (i["skus"] or []) if s in skus]
    return icons.for_product(types[0]) if types else "🛍️"


def products(i):
    if i["category"] == "wismo":
        return {"stock_wait": "Vendor stock", "fulfilment": "Warehouse", "transit": "Courier"}.get(i["sub_tag"], "Delivery")
    types = sorted({skus[s]["product_type"] for s in (i["skus"] or []) if s in skus})
    return ", ".join(f"{icons.for_product(t)} {t.replace('_', ' ').title()}" for t in types) or "—"


df = pd.DataFrame([{
    "#": n + 1,
    "Issue": f"{issue_icon(i)}  {i['title']}",
    "Product": products(i),
    "Category": f"{icons.CATEGORY_ICON.get(i['category'], '')} {CATEGORY_LABEL.get(i['category'], i['category'])}",
    "Vendor / courier": f"{i['vendor_id']} {i['vendor_city'] or ''}".strip() if i["vendor_id"] else "—",
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
    st.markdown(f"### {issue_icon(sel)} {sel['title']}")
    st.markdown(chips(f"{sel['items_7d']} items this week", f"{sel['from_returns']} returns",
                      f"{sel['from_tickets']} tickets", sel["vendor_id"],
                      *[f"{icons.for_product(skus.get(s, {}).get('product_type'))} {s}" for s in (sel["skus"] or [])[:3]]),
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
                dims = [d for d in ("bust_in", "waist_in", "length_in") if any(g[0] == d for g in gaps)]
                dim = max(dims, key=lambda d: max(abs(g[2] - g[3]) for g in gaps if g[0] == d))  # ties: bust first
                rows_ = [g for g in gaps if g[0] == dim]
                st.markdown(f"**Size chart vs category median ({dim.replace('_in', '')}, inches)**")
                st.dataframe(pd.DataFrame({
                    "Size": [g[1] for g in rows_],
                    sel["vendor_id"] or "Vendor": [g[2] for g in rows_],
                    "Median": [g[3] for g in rows_],
                    "Gap": [f"{g[2] - g[3]:+.1f}" for g in rows_],
                }), hide_index=True, use_container_width=True)

    # customer quotes (evidence)
    quotes = []
    if sel["category"] == "wismo":
        col = {"stock_wait": "vendor_id", "fulfilment": "fc", "transit": "courier"}[sel["sub_tag"]]
        late = client.table("v_order_stages").select("order_id").eq(col, sel["vendor_id"]) \
            .eq("blamed_stage", sel["sub_tag"]).execute().data
        ids = [o["order_id"] for o in late]
        if ids:
            for w in client.table("v_wismo_orders").select("ticket_id,order_id,body").in_("order_id", ids) \
                    .order("created_at", desc=True).limit(3).execute().data:
                quotes.append((w["body"], f"Ticket · {w['ticket_id']} · {w['order_id']}"))
    else:
        q = client.table("item_tags").select("source,item_id,sku_id,evidence_span").eq("route", "trusted") \
            .eq("category", sel["category"])
        q = q.eq("sub_tag", sel["sub_tag"]) if sel["sub_tag"] else q.is_("sub_tag", "null")
        q = q.eq("vendor_id", sel["vendor_id"]) if sel["vendor_id"] else q.is_("vendor_id", "null")
        for e in q.order("tagged_at", desc=True).limit(3).execute().data:
            if e["source"] == "return":
                r = client.table("returns").select("other_text").eq("return_id", e["item_id"]).execute().data
                text = r[0]["other_text"] if r else e["evidence_span"]
            else:
                t = client.table("tickets").select("body").eq("ticket_id", e["item_id"]).execute().data
                text = t[0]["body"] if t else e["evidence_span"]
            quotes.append((text, f"{'Return' if e['source'] == 'return' else 'Ticket'} · {e['item_id']} · {e['sku_id'] or ''}"))
    st.markdown(f"**What customers said ({len(quotes)} of {sel['items_7d']})**")
    for text, meta in quotes:
        quote(text, meta)

    c1, c2 = st.columns(2)
    clicked = None
    for i, (key, label) in enumerate(ACTIONS.items()):
        col = c1 if i % 2 == 0 else c2
        if col.button(label if key != "escalate" else f"Escalate to {sel['vendor_id'] or 'owner'}",
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

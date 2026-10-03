"""Delay scorecard: vendors judged on stock wait, couriers on transit, with the orders behind every number."""
import pandas as pd
import streamlit as st

from core.session import db, require
from core.ui import RED, header, kpis

u = require("scorecard")
client = db()

stages = client.table("v_order_stages").select(
    "order_id,vendor_id,courier,pin_zone,placed_at,stock_at,handed_at,delivered_at,stock_wait_days,fulfilment_days,"
    "transit_days,stock_target,fulfilment_target,transit_target,stock_over,fulfilment_over,transit_over,is_late,"
    "days_late,blamed_stage").execute().data
vendors = client.table("v_vendor_scorecard").select("*").execute().data
couriers = client.table("v_courier_scorecard").select("*").execute().data
wismo = client.table("v_wismo_orders").select("ticket_id,order_id,body").execute().data

header("Delay scorecard", f"Last 4 weeks · {len(stages)} orders · {len(wismo)} WISMO tickets linked to their orders")
if not stages:
    st.info("No order data yet.")
    st.stop()

df = pd.DataFrame(stages)
late = df[df["is_late"]]
recurring = sum(1 for v in vendors if v["recurring"]) + sum(1 for c in couriers if c["recurring"])
kpis([
    ("Delivered on time", f"{round(100 * (1 - df['is_late'].mean()))}%", "against stage targets"),
    ("Average days late", f"{late['days_late'].astype(float).mean():.1f}" if len(late) else "0", "late orders only"),
    ("WISMO tickets per 100 orders", f"{round(100 * len(wismo) / len(df))}", "linked tickets"),
    ("Recurring offenders", str(recurring), "late above 15% in 3 of 4 weeks"),
], color={"Recurring offenders": RED if recurring else None})
st.write("")

left, right = st.columns([3, 2], gap="medium")
with left:
    st.markdown("#### Vendors · judged only on stock wait")
    st.caption("Target: stock available within 0.5 days of the order")
    vendors.sort(key=lambda v: (-int(v["recurring"]), -(v["pct_late"] or 0)))
    vdf = pd.DataFrame([{"Vendor": v["vendor_id"], "City": v["city"], "Orders": v["orders"],
                         "% late": f"{int(v['pct_late'])}%", "Avg days late": v["avg_days_late"] or "—",
                         "WISMO / 100": v["wismo_per_100"],
                         "Top delay stage": (v["top_stage"] or "—").replace("_", " "),
                         "Recurring": "Yes" if v["recurring"] else "No"} for v in vendors])
    picked = st.dataframe(vdf, hide_index=True, use_container_width=True, on_select="rerun",
                          selection_mode="single-row", key="vendors", height=320)
    rows = picked.selection.rows if picked and picked.selection else []
    sel_vendor = vendors[rows[0]]["vendor_id"] if rows else vendors[0]["vendor_id"]

    st.markdown("#### Couriers · judged only on transit")
    st.caption("Target: 5–7 days by zone, 9 days to the north east")
    st.dataframe(pd.DataFrame([{"Courier": c["courier"], "Orders": c["orders"], "% late": f"{int(c['pct_late'])}%",
                                "Avg days late": c["avg_days_late"] or "—", "Worst zone": c["worst_zone"] or "—",
                                "Recurring": "Yes" if c["recurring"] else "No"}
                               for c in sorted(couriers, key=lambda c: -(c["pct_late"] or 0))]),
                 hide_index=True, use_container_width=True)

with right:
    v = next(x for x in vendors if x["vendor_id"] == sel_vendor)
    vd = df[df["vendor_id"] == sel_vendor]
    vlate = vd[vd["is_late"]]
    if v["recurring"]:
        st.markdown(f"<span style='color:{RED};font-weight:600;font-size:12px'>RECURRING</span>", unsafe_allow_html=True)
    st.markdown(f"### {sel_vendor}, {v['city']}")
    st.write(f"{int(v['pct_late'])}% of {v['orders']} orders waited too long for this vendor's stock.")

    st.markdown("**Average days per stage, late orders vs target**")
    if len(vlate):
        for label, col, target in [("Stock wait · vendor", "stock_wait_days", "stock_target"),
                                   ("Fulfilment · FC", "fulfilment_days", "fulfilment_target"),
                                   ("Transit · courier", "transit_days", "transit_target")]:
            avg = vlate[col].dropna().astype(float).mean()
            tgt = vlate[target].astype(float).mean()
            over = avg > tgt
            st.markdown(f"{'**' if over else ''}{label}{'**' if over else ''} — "
                        f"<span class='fr-mono' style='color:{RED if over else 'inherit'}'>{avg:.1f} d · target {tgt:.1f}</span>",
                        unsafe_allow_html=True)
            st.progress(min(1.0, avg / 9))
        st.caption("Bar length = days on a 9-day scale. Red = over target.")
    else:
        st.write("No late orders for this vendor.")

    st.markdown(f"**Orders and messages behind the number ({min(3, len(vlate))} of {len(vlate)} late)**")
    msgs = {w["order_id"]: w["body"] for w in wismo}
    for _, o in vlate.sort_values("days_late", ascending=False).head(3).iterrows():
        fmt = lambda d: pd.to_datetime(d).strftime("%-d %b") if d else "—"  # noqa: E731
        line = (f"{o['order_id']} · placed {fmt(o['placed_at'])} · stock {fmt(o['stock_at'])} · "
                f"{'delivered ' + fmt(o['delivered_at']) if o['delivered_at'] else 'in transit'} · {o['days_late']} d late")
        st.markdown(f"<div class='fr-quote'><div class='m fr-mono'>{line}</div>"
                    f"<div class='q'>{'“' + msgs[o['order_id']] + '”' if o['order_id'] in msgs else ''}</div></div>",
                    unsafe_allow_html=True)
    st.download_button("Export late orders (CSV)", vlate.to_csv(index=False), file_name=f"{sel_vendor}-late-orders.csv",
                       use_container_width=True)

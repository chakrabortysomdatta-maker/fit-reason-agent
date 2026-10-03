"""The reading pipeline. Models only read and write language; every lookup, date and count is code.

Steps:
  1. tag_new_items   - batch-tag untagged return comments and tickets (fast model), second look for unsure ones
                       (strong model), join order -> SKU -> vendor in code, save to item_tags
  2. title_issues    - one-line titles for issues with >= 5 items (fast model)
  3. draft_replies   - for tickets: facts from code -> draft (strong) -> fact-check (fast) -> one redraft -> or hand to a person
"""
import json
import re
import time
from datetime import timedelta
from typing import Optional

import psycopg
from psycopg.rows import dict_row

from core.config import settings
from core.llm import Usage, load_prompt, structured_call
from core.schemas import FactCheck, IssueTitle, ItemTag, ReplyDraft, TagBatch

BATCH_SIZE = 15
TRUST_AT = 0.65        # below this, a second look by the strong model (0.75 sent half of all items to it)
CHECK_TAG_BELOW = 0.60  # still below this after the second look -> the Check tag list
ORDER_ID = re.compile(r"\bDH-\d{4,6}\b", re.IGNORECASE)


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.supabase_db_url, row_factory=dict_row, autocommit=True)


# ------------------------------------------------------------------ run bookkeeping
def start_run(conn, kind: str) -> str:
    return conn.execute("insert into runs (kind) values (%s) returning run_id", (kind,)).fetchone()["run_id"]


def finish_run(conn, run_id, usage: Usage, items: int, unclassified: int, status: str = "done") -> None:
    conn.execute(
        "update runs set finished_at = now(), items = %s, unclassified = %s, tokens = %s, cost_inr = %s, status = %s "
        "where run_id = %s",
        (items, unclassified, json.dumps(usage.tokens), round(usage.cost, 2), status, run_id),
    )


# ------------------------------------------------------------------ 1. tagging
def _untagged(conn, limit: Optional[int]) -> list[dict]:
    sql = """
      select 'return' as source, r.return_id as item_id, r.other_text as text, ol.order_id, ol.sku_id
      from returns r join order_lines ol on ol.line_id = r.line_id
      where r.other_text is not null
        and not exists (select 1 from item_tags t where t.source = 'return' and t.item_id = r.return_id)
      union all
      select 'ticket', t.ticket_id, t.body, t.order_id, null
      from tickets t
      where not exists (select 1 from item_tags it where it.source = 'ticket' and it.item_id = t.ticket_id)
      order by 2
    """
    rows = conn.execute(sql + (f" limit {int(limit)}" if limit else "")).fetchall()
    return rows


def _resolve_order(conn, item: dict, tag_order: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """order_id, sku_id, vendor_id - from the source row first, then the ID written in the text. Code, not model."""
    order_id = item.get("order_id")
    if not order_id:
        found = ORDER_ID.search(item["text"] or "") or (ORDER_ID.search(tag_order) if tag_order else None)
        order_id = found.group(0).upper() if found else None
    sku_id = item.get("sku_id")
    if order_id and not sku_id:
        row = conn.execute("select sku_id from order_lines where order_id = %s order by line_id limit 1", (order_id,)).fetchone()
        sku_id = row["sku_id"] if row else None
        if not row:
            order_id = None  # an ID that does not exist is not trusted
    vendor_id = None
    if sku_id:
        vendor_id = conn.execute("select vendor_id from skus where sku_id = %s", (sku_id,)).fetchone()["vendor_id"]
    return order_id, sku_id, vendor_id


def _save_tag(conn, item, tag: Optional[ItemTag], route: str, model: str, version: str, run_id) -> None:
    order_id, sku_id, vendor_id = _resolve_order(conn, item, tag.order_id if tag else None)
    conn.execute(
        """insert into item_tags (source, item_id, category, sub_tag, urgency, language, order_id, sku_id, vendor_id,
                                  confidence, evidence_span, route, model, prompt_version, run_id)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (source, item_id) do update set category = excluded.category, sub_tag = excluded.sub_tag,
             urgency = excluded.urgency, language = excluded.language, order_id = excluded.order_id,
             sku_id = excluded.sku_id, vendor_id = excluded.vendor_id, confidence = excluded.confidence,
             evidence_span = excluded.evidence_span, route = excluded.route, model = excluded.model,
             prompt_version = excluded.prompt_version, run_id = excluded.run_id, tagged_at = now()""",
        (item["source"], item["item_id"], tag.category if tag else None, tag.sub_tag if tag else None,
         tag.urgency if tag else None, tag.language if tag else None, order_id, sku_id, vendor_id,
         round(tag.confidence, 2) if tag else None, tag.evidence_span[:300] if tag else None, route, model, version, run_id),
    )


def _too_short(text: str) -> bool:
    return len(re.findall(r"\w+", text or "")) < 2


def tag_new_items(limit: Optional[int] = None, log=print) -> dict:
    conn = connect()
    run_id = start_run(conn, "tag")
    usage = Usage()
    version, _ = load_prompt("tag_batch")
    items = _untagged(conn, limit)
    unclassified = second_looks = 0
    log(f"{len(items)} new items to read")

    # Too short to mean anything: decided in code, no model call.
    short = [i for i in items if _too_short(i["text"])]
    for i in short:
        tag = ItemTag(category="other", sub_tag="insufficient_information", urgency="low", language="other",
                      order_id=None, confidence=0.0, evidence_span=i["text"] or "")
        _save_tag(conn, i, tag, "check_tag", "code", "rule-short", run_id)
    items = [i for i in items if not _too_short(i["text"])]

    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        text = "\n".join(f"[{i['item_id']}] {i['text']}" for i in batch)
        res = structured_call("fast", "tag_batch", TagBatch, {"input": text}, usage)
        tags = {t.ref.strip("[] "): t for t in (res.parsed.items if res.parsed else [])}
        for i in batch:
            tag = tags.get(i["item_id"])
            route, model = "trusted", res.model
            if tag is None or tag.confidence < TRUST_AT:
                # Second look, one item at a time, by the strong model.
                second_looks += 1
                single = structured_call("strong", "tag", ItemTag, {"input": i["text"]}, usage)
                if single.parsed is not None:
                    tag, model = single.parsed, single.model
                if tag is None:
                    route = "unclassified"
                    unclassified += 1
                elif tag.confidence < CHECK_TAG_BELOW:
                    route = "check_tag"
            _save_tag(conn, i, tag, route, model, version, run_id)
        log(f"  read {min(start + BATCH_SIZE, len(items))}/{len(items)} · cost so far ₹{usage.cost:.2f}")

    total = len(items) + len(short)
    finish_run(conn, run_id, usage, total, unclassified)
    return {"items": total, "second_looks": second_looks, "unclassified": unclassified, "cost_inr": round(usage.cost, 2)}


# ------------------------------------------------------------------ 2. issue titles
def title_issues(log=print) -> dict:
    conn = connect()
    run_id = start_run(conn, "tag")
    usage = Usage()
    issues = conn.execute(
        "select issue_key, category, sub_tag, vendor_id, skus from v_issues where not monitor and category <> 'wismo' "
        "and issue_key not in (select issue_key from issue_titles)"
    ).fetchall()
    for iss in issues:
        quotes = conn.execute(
            """select coalesce(r.other_text, t.body) as text from item_tags it
               left join returns r on it.source = 'return' and r.return_id = it.item_id
               left join tickets t on it.source = 'ticket' and t.ticket_id = it.item_id
               where it.route = 'trusted' and it.category = %s
                 and (it.category = 'wismo' or coalesce(it.sub_tag, '-') = %s)
                 and coalesce(it.vendor_id, '-') = %s limit 5""",
            (iss["category"], iss["sub_tag"] or "-", iss["vendor_id"] or "-"),
        ).fetchall()
        names = conn.execute("select string_agg(distinct name, ', ') as n from skus where sku_id = any(%s)",
                             (iss["skus"] or [],)).fetchone()["n"]
        prompt = (f"category: {iss['category']}\nsub_tag: {iss['sub_tag']}\nvendor: {iss['vendor_id'] or 'unknown'}\n"
                  f"products: {names or 'unknown'}\nquotes:\n" + "\n".join(f"- {q['text']}" for q in quotes))
        res = structured_call("fast", "issue_title", IssueTitle, {"input": prompt}, usage)
        if res.parsed:
            conn.execute("insert into issue_titles (issue_key, title, run_id) values (%s,%s,%s) "
                         "on conflict (issue_key) do update set title = excluded.title, updated_at = now()",
                         (iss["issue_key"], res.parsed.title[:120], run_id))
    finish_run(conn, run_id, usage, len(issues), 0)
    log(f"titled {len(issues)} issues · ₹{usage.cost:.2f}")
    return {"issues": len(issues), "cost_inr": round(usage.cost, 2)}


# ------------------------------------------------------------------ 3. reply suggestions
def build_facts(conn, order_id: Optional[str]) -> dict:
    """Everything a reply may state. Built in code from the database; the model may use nothing else."""
    facts: dict = {"policies": {p["policy_key"]: p["body"] for p in conn.execute("select * from policies").fetchall()}}
    if not order_id:
        facts["order"] = "No order is linked to this message."
        return facts
    o = conn.execute(
        """select o.order_id, o.placed_at, o.payment_mode, o.courier, o.pin_zone, o.order_value_inr, o.status,
                  ol.size, ol.price_inr, s.name as product, s.sku_id, s.chart_id, s.product_type
           from orders o join order_lines ol on ol.order_id = o.order_id join skus s on s.sku_id = ol.sku_id
           where o.order_id = %s order by ol.line_id limit 1""", (order_id,)).fetchone()
    if not o:
        facts["order"] = f"Order {order_id} was not found."
        return facts
    ev = {e["status"]: e["at"] for e in conn.execute(
        "select status, min(at) as at from order_events where order_id = %s group by status", (order_id,)).fetchall()}
    fmt = lambda d: d.strftime("%-d %b %Y") if d else None  # noqa: E731
    order = {
        "order_id": o["order_id"], "product": o["product"], "size_bought": o["size"], "amount_paid_inr": o["price_inr"],
        "payment_mode": o["payment_mode"], "courier": o["courier"], "placed_on": fmt(o["placed_at"]),
        "current_status": o["status"].replace("_", " "),
    }
    if "handed_to_courier" in ev:
        order["dispatched_on"] = fmt(ev["handed_to_courier"])
        if "delivered" not in ev:
            max_days = conn.execute("select max_days from transit_targets where pin_zone = %s", (o["pin_zone"],)).fetchone()["max_days"]
            order["expected_delivery_by"] = fmt(ev["handed_to_courier"] + timedelta(days=max_days))
    else:
        order["dispatched_on"] = "not yet dispatched"
    if "delivered" in ev:
        order["delivered_on"] = fmt(ev["delivered"])
        order["exchange_window_ends"] = fmt(ev["delivered"] + timedelta(days=7))
    facts["order"] = order
    chart = conn.execute("select size, bust_in, waist_in, length_in from size_charts where chart_id = %s order by size",
                         (o["chart_id"],)).fetchall()
    if chart:
        facts["size_chart_inches"] = {c["size"]: {k: float(v) for k, v in c.items() if k != "size" and v is not None}
                                      for c in chart}
    ret = conn.execute(
        """select r.status, r.refund_amount_inr, r.refunded_at, r.raised_at from returns r
           join order_lines ol on ol.line_id = r.line_id where ol.order_id = %s order by r.raised_at desc limit 1""",
        (order_id,)).fetchone()
    if ret:
        facts["return"] = {
            "status": ret["status"].replace("_", " "), "raised_on": fmt(ret["raised_at"]),
            "refund_amount_inr": ret["refund_amount_inr"] or "not yet decided (after inspection)",
            "refunded_on": fmt(ret["refunded_at"]) or "no refund date recorded",
        }
    return facts


def draft_one(conn, message: str, order_id: Optional[str], category: Optional[str], usage: Usage) -> dict:
    """Draft -> check -> one redraft -> or a person. Returns the guidance_drafts row values."""
    facts = build_facts(conn, order_id)
    ret = facts.get("return") if isinstance(facts.get("return"), dict) else None
    if category == "refund" and (ret is None or ret.get("refunded_on") == "no refund date recorded"):
        # Pilot rule (PRD): refund timing and amounts are confirmed by a person when no refund date is on record.
        return {"status": "needs_human", "reply": None, "attempts": [], "facts": facts, "check_passed": None,
                "needs_human_reason": "Unsupported refund date: no refund date or amount is on record yet",
                "language": None}
    attempts = []
    feedback = ""
    for _ in range(2):
        prompt = (f"FACTS (JSON):\n{json.dumps(facts, ensure_ascii=False, default=str)}\n\n"
                  f"CUSTOMER MESSAGE:\n{message}{feedback}")
        draft = structured_call("strong", "reply_draft", ReplyDraft, {"input": prompt}, usage, temperature=0.4)
        if draft.parsed is None:
            return {"status": "unclassified", "reply": None, "attempts": attempts, "facts": facts,
                    "check_passed": None, "needs_human_reason": f"Draft failed validation: {draft.error}",
                    "language": None}
        d = draft.parsed
        if not d.can_answer:
            attempts.append({"reply": d.reply, "problems": ["Model said the facts are not enough to answer"]})
            return {"status": "needs_human", "reply": None, "attempts": attempts, "facts": facts, "check_passed": False,
                    "needs_human_reason": "Not enough facts on record to answer without guessing", "language": d.language}
        check = structured_call(
            "fast", "fact_check", FactCheck,
            {"input": f"FACTS (JSON):\n{json.dumps(facts, ensure_ascii=False, default=str)}\n\nREPLY:\n{d.reply}"}, usage)
        problems = check.parsed.problems if check.parsed else [f"Fact-check failed validation: {check.error}"]
        passed = bool(check.parsed and check.parsed.passed and not check.parsed.problems)
        attempts.append({"reply": d.reply, "problems": problems})
        if passed:
            return {"status": "drafted", "reply": d.reply, "attempts": attempts, "facts": facts, "check_passed": True,
                    "needs_human_reason": None, "language": d.language}
        feedback = "\n\nYOUR PREVIOUS DRAFT WAS REJECTED BY THE FACT-CHECK:\n- " + "\n- ".join(problems) + \
                   "\nRewrite using only the facts. If the facts cannot answer, set can_answer to false."
    reason = "Fact-check failed twice: " + "; ".join(attempts[-1]["problems"])[:240]
    return {"status": "needs_human", "reply": None, "attempts": attempts, "facts": facts, "check_passed": False,
            "needs_human_reason": reason, "language": None}


def _save_draft(conn, ticket_id, message, category, result, cost, run_id) -> str:
    return conn.execute(
        """insert into guidance_drafts (ticket_id, message_text, category, language, facts, reply, attempts, check_passed,
                                        status, needs_human_reason, cost_inr, run_id)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning draft_id""",
        (ticket_id, message, category, result["language"], json.dumps(result["facts"], default=str), result["reply"],
         json.dumps(result["attempts"], ensure_ascii=False), result["check_passed"], result["status"],
         result["needs_human_reason"], round(cost, 2), run_id)).fetchone()["draft_id"]


def draft_replies(limit: int = 40, log=print) -> dict:
    """Suggest replies for the most recent tagged tickets that have none yet (pilot: a sample, not all)."""
    conn = connect()
    run_id = start_run(conn, "draft")
    usage = Usage()
    rows = conn.execute(
        """select t.ticket_id, t.body, it.order_id, it.category, it.route from tickets t
           join item_tags it on it.source = 'ticket' and it.item_id = t.ticket_id
           where not exists (select 1 from guidance_drafts g where g.ticket_id = t.ticket_id)
           order by t.created_at desc limit %s""", (limit,)).fetchall()
    counts = {"drafted": 0, "needs_human": 0, "unclassified": 0}
    for r in rows:
        before = usage.cost
        if r["route"] != "trusted":
            result = {"status": "unclassified", "reply": None, "attempts": [], "facts": {}, "check_passed": None,
                      "needs_human_reason": "Message could not be understood with confidence", "language": None}
        else:
            result = draft_one(conn, r["body"], r["order_id"], r["category"], usage)
        _save_draft(conn, r["ticket_id"], r["body"], r["category"], result, usage.cost - before, run_id)
        counts[result["status"]] += 1
        log(f"  {r['ticket_id']} {result['status']} · ₹{usage.cost:.2f}")
    finish_run(conn, run_id, usage, len(rows), counts["unclassified"])
    return {**counts, "cost_inr": round(usage.cost, 2)}


def try_message(message: str, order_hint: Optional[str] = None) -> dict:
    """The live 'Try a message' box: tag, then draft. Saved as a draft with no ticket."""
    conn = connect()
    run_id = start_run(conn, "live")
    usage = Usage()
    text = f"{message}\n(order reference given separately: {order_hint})" if order_hint else message
    tag = structured_call("fast", "tag", ItemTag, {"input": text}, usage)
    order_id = None
    if tag.parsed:
        item = {"text": f"{message} {order_hint or ''}", "order_id": None, "sku_id": None}
        order_id, _, _ = _resolve_order(conn, item, tag.parsed.order_id)
    if tag.parsed is None:
        result = {"status": "unclassified", "reply": None, "attempts": [], "facts": {}, "check_passed": None,
                  "needs_human_reason": f"Could not tag the message: {tag.error}", "language": None}
    elif _too_short(message):
        result = {"status": "needs_human", "reply": None, "attempts": [], "facts": {}, "check_passed": None,
                  "needs_human_reason": "Message too short to understand", "language": tag.parsed.language}
    else:
        result = draft_one(conn, message, order_id, tag.parsed.category, usage)
    draft_id = _save_draft(conn, None, message, tag.parsed.category if tag.parsed else None, result, usage.cost, run_id)
    finish_run(conn, run_id, usage, 1, 1 if result["status"] == "unclassified" else 0)
    return {"draft_id": draft_id, "tag": tag.parsed.model_dump() if tag.parsed else None, "order_id": order_id,
            "cost_inr": round(usage.cost, 2), **result}


if __name__ == "__main__":
    t = time.time()
    print(tag_new_items())
    print(title_issues())
    print(draft_replies())
    print(f"done in {time.time() - t:.0f}s")

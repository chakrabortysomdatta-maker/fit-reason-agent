# Build note: Fit-Reason Agent

**Date:** 4 October 2026 · **Author:** Somdatta Chakraborty · **Live:** https://dhaga-fit-reason.streamlit.app

**What it is:** an internal tool that reads every return comment and support ticket (English, Hindi, Hinglish). It gives Neha a ranked list of issues and a delay scorecard, and Ms Chhaya Gupta fact-checked reply suggestions in shadow mode.

## 1. Code versus model, step by step

**Rule:** a model is used only for reading and writing language. Every count, date calculation, lookup and score is plain code or SQL.

| Step | Code or model | Why this side of the line |
|---|---|---|
| Load data, hide phone numbers and names; skip messages under two words | Code | Rules; "bekaar" goes to Check tag with no model call |
| Tag each message: topic, reason, urgency, language, order number | **gpt-oss-20b**, temperature 0, 15 messages per call | Messy Hinglish into fixed labels is language work; high volume, so the cheap model |
| Route by confidence (below 0.65 → second look; below 0.60 → Check tag) | Code | A comparison |
| Second look at unsure messages | **gpt-oss-120b**, temperature 0 | Judgment on ambiguous text; about 4% of messages |
| Link order → product → vendor; group into issues; priority score | Code (SQL) | Lookup, counting and arithmetic |
| One-line issue title | **gpt-oss-20b**, temperature 0 | Summarising customer quotes is language |
| Time each order's stages, blame the late stage, flag repeat offenders | Code (SQL) | Date arithmetic; must be exact and auditable |
| Gather the facts a reply may use (order, size chart, policy) | Code | Lookup |
| Draft the reply in the customer's language | **gpt-oss-120b**, temperature 0.4 | Customer-visible language; slight variety reads naturally |
| Fact-check the draft against those facts | **gpt-oss-20b**, temperature 0 | Judgment ("is this date in the facts?"); must be repeatable |
| Refund question with no refund date on record | Code | A business rule: always a person, never a model guess |
| Who can see what | Database access rules | Enforced by Supabase, not by the app |

Every model answer is a validated Pydantic schema (strict JSON); a failure is retried once, then shown as Unclassified. **Two models:** the cheap, fast 20B does the bulk work and checking; the 120B is used only where judgment or customer-facing quality matters (about 15% of calls).

## 2. Why each pattern is there, and what breaks without it

| Pattern | Where | What breaks without it |
|---|---|---|
| **Prompt chaining** | Facts → draft → fact-check; tag → group → title | One big prompt makes up order details, and there's no checkpoint to inspect when it's wrong |
| **Routing** | By topic (fit/quality → Neha's queue, delivery → scorecard, questions → replies) and by confidence | Unsure tags pollute Neha's ranking; delivery complaints never reach the delay scorecard; every message pays for the bigger model |
| **Evaluator-optimizer** | The fact-check rejects a draft; it is redrafted once with the reasons, then handed to a person | An invented date or refund amount reaches a tired reviewer, and after go-live, a customer |
| **Parallelization (batching)** | 15 messages tagged in one call | One call per message took ~50 minutes and hit Groq's request and token limits; batching took it to ~9 minutes |

## 3. Cost line

**Prices:** Groq list prices, gpt-oss-20b $0.075 / $0.30 and gpt-oss-120b $0.15 / $0.60 per million input/output tokens, at ₹88 = $1. Token counts are measured from the `runs` table.

- **One demo run:** 420 messages read and 95 reply suggestions (55 drafted, 39 handed to a person, 1 unclassified) cost **₹2.89 in total**.
- **Per item:** tagging ₹0.0024, second look ₹0.017, reply with fact-check ₹0.027.
- **At Dhaga's volume, per week:**
  - **Messages read:** 48,000 orders × 31% returns × 44% "Other" = 6,547 comments, plus ~9,000 tickets = **15,547 messages**.
  - **Tagging:** 15,547 × ₹0.0024 = **₹37**
  - **Second look:** ~620 × ₹0.017 = **₹10**
  - **Replies on a 20% sample:** 1,800 × ₹0.027 = **₹49**
  - **Total AI cost:** ≈ **₹96 a week, about ₹420 a month**. Replying to every ticket adds about ₹1,050 a month.
- **All in for the pilot:** about **₹2,600 a month**, of which the database (Supabase Pro) is ₹2,200. Hosting is free.
- **Break-even:** about 5 fewer returns a week out of 14,880, at an assumed ₹120 handling cost per return.

## 4. What broke that we didn't expect

1. **The free tier's speed limit, not its price.** Groq allows 8,000 tokens a minute. A 0.75 confidence bar sent half of all messages to the bigger model (the small one often says 0.7 on clear text), its limit ran out and the run crawled. **Fix:** 15 messages per call and a 0.65 bar. Second looks fell to about 4%; a full run takes about 9 minutes.
2. **Blaming the wrong party.** The first version filed every "where is my order" complaint under the product's vendor, so vendors were blamed for slow couriers, and the real slow-stock vendor didn't appear. **Fix:** each complaint goes to whoever caused that order's delay; on-time orders are left out.
3. **Sample data that didn't match the client.** The headline tile read "28% → 83%" because 72% of sample returns were "Other", against the brief's 44%. **Fix:** the sample now matches the brief, and the tile honestly reads "56% → 90%".
4. **Replies that looked right but weren't.** A Hinglish question was answered in Devanagari script, and a refund question got a vague holding reply. **Fix:** a script rule in the prompt, and a code rule that sends refund-date questions to a person.
5. **Bugs only a browser test found.** A reviewer's second click on a message could be lost, only 60 of 95 suggestions were listed, and the hosted app read its settings once at start-up and missed them. **Fix:** all three, then retested by signing in as each role on desktop and phone.

**Known gap, stated openly:** the live "Try a message" step runs inside the app with a full database connection. For a pilot on real data, it moves to its own small service with a restricted database role.

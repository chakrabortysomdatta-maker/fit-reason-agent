# Discovery note: Dhaga & Co.

**Date:** 3 October 2026, written before the first code commit
**Author:** Somdatta Chakraborty
**Source:** FDE Academy Tech Track Mini Project 1, "The Dhaga & Co. Engagement" (client brief) and the Reader's Guide

Labels: **[Brief]** = stated in the client brief; **[Calc]** = arithmetic on brief numbers; **[Assumption]** = ours, to confirm with the client.

---

## 1. The problem, in the client's words

> "Returns are thirty-one percent overall. When I read the Other box by hand, most of it is about fit, but I can only read a few hundred at a time." (Neha, Category Head)

**In one sentence:** customers already tell us why a third of orders come back, and nobody can read it fast enough to fix the size chart or the vendor.

## 2. Who owns it today, and what they do instead

- **Owner:** Neha, Category Head.
- **What she does instead:** she reads a few hundred "Other" comments by hand. The listing team never gets the signal. Vendor conversations (Faizan, Head of Supply Chain) run on anecdote, because vendor lead times are "held in people's heads" [Brief].
- **On the support side:** agents answer from four canned replies, and first response averages 9 hours [Brief].

## 3. The evidence

- **Returns:**
  - 31% of orders are returned [Brief].
  - 44% of return reasons land in "Other", a free-text box [Brief].
  - Neha says most of those are about fit [Brief].
- **Catalogue:** size charts differ per vendor. Colour is typed about 90 ways, and fabric is free text [Brief].
- **Unread text:**
  - 410,000 product reviews, displayed but never analysed [Brief].
  - About 9,000 support tickets a week, mostly free text, inconsistently tagged [Brief].
- **Customers:** they write in Hinglish, so free text in mixed language is normal input, not an edge case [Brief].
- **Supply:** 40 vendors in Tiruppur and Jaipur, about 400 new products a week, and products pulled after 6 weeks unsold [Brief]. The fixes have to land within one catalogue cycle.

## 4. What it costs them

- **Returns a week:** 48,000 orders × 31% = **14,880** [Calc].
- **Returns with only "Other" as the reason:** 14,880 × 44% = **about 6,550 a week** [Calc].
- **Sales reversed:** 14,880 × ₹840 average order = **₹1.25 Cr every week** [Calc].
- **Pickup and handling:** at ₹120 a return [Assumption, using the doorstep-refusal cost as a proxy], about **₹9.3 Cr a year** [Calc].
- **Retention:** repeat purchase has been stuck at **22% for six quarters**, and acquisition cost is up **40%** [Brief]. A first order that doesn't fit rarely gets a second.

## 5. What success looks like, measured with data they already hold

| Measure | Today | Target | Measured from |
|---|---|---|---|
| Returns with a specific, usable reason | 56% [Calc] | ≥ 85% | Returns table + tags |
| Issues acted on per week (fix or vendor escalation) | 0 | ≥ 15 | Action log |
| Return rate on fixed products | Product baseline | −20% within one 6-week catalogue cycle | Orders + returns |
| Neha's hours spent reading comments | ~6–8 a week [Assumption] | < 1 a week | Her own estimate + usage |

## 6. Ranked shortlist

**Ranked on:** owner and measurable loss (25), size of the loss (25), data ready now (20), root cause rather than symptom (15), safe and buildable by a small team (15).

| Rank | Problem (owner) | Why it sits here |
|---|---|---|
| **1** | **Returns explained only as "Other"** (Neha) | A named owner losing a tracked number. Unread text is already in hand. It sits upstream of fit, size-chart and vendor problems. It can run internally with no customer risk. |
| 2 | Cash-on-delivery orders refused at the door, 26% (Faizan) | The biggest rupee figure (~₹4.75 Cr a year [Calc]), but no reason is recorded, so the cause is unknown. Learning why has to come first. |
| 3 | "Where is my order" tickets, 58% of support (Arpita) | Clean data, but a symptom of slow delivery. We use these tickets as evidence for vendor and courier delays instead of automating replies first. |
| 4 | 6–9 days from sample to live listing (Vivek) | Real, but the cost of a missed drop isn't quantified in the brief. A good next step for the same reading engine. |
| 5 | Analytics request queue of ~2 weeks (Karthik) | A real bottleneck, but a meta-problem. Fixing #1 removes one class of his requests. |

**Not ranked as problems:** repeat purchase (22%) and acquisition cost (+40%). They are outcomes that problems 1–3 feed into, not things to build against directly.

## 7. Biggest assumption, and what would prove it wrong

- **The assumption:** "Other" comments are mostly about fit, **and** they cluster on identifiable products and vendors, so fixing size charts and vendors at the source works.
- **What would prove it wrong:** on a real sample of 2,000 "Other" comments, either:
  - fit is **under 40%** of them, or
  - the top 10% of products hold **under 30%** of the fit complaints.
- **What we'd do then:** pivot to generic size guidance and a redesigned return-reason dropdown, instead of product-by-product fixes.

---

**What we build:**
- **Internal-first:** an assistant reads every return comment and support ticket.
- **Neha** gets a ranked list of issues with evidence, plus a delay report by vendor and courier.
- **Support reviewers** see suggested replies in the customer's language, rated in shadow mode. Nothing is sent to customers until reviewers rate them accurate for two weeks.

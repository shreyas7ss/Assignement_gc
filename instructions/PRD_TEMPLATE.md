# Trade-Document Pipeline: PRD

Shreyas · Part 1

## 1. Nova, FDE, System of Outcomes

*(Your words, max 200 each. Finish these in your own voice, then delete the starters.)*

- **Nova:** Nova is ... Traditional SaaS stops at ... In my project, the agents ...
- **FDE:** An FDE is ... GoComet needs this because ... I saw this when ...
- **System of Outcomes:** A system of record ..., engagement ..., outcomes ... My pipeline gives the operator ...

## 2. Problem

Today someone reads every emailed document by hand and checks it against customer rules. It breaks because:

- rules live in people's heads
- small errors (an HS code digit, a consignee spelling) get missed
- a missing field can slip through
- each fix is a round trip; 2 to 4 cycles per shipment is normal
- amendment emails are typed by hand and often incomplete
- nobody can see what's pending or why something was approved

These are risks to confirm with operators, not measured numbers.

**First 5 minutes:** upload a document, see the eight fields with confidence, what matched, what didn't, what's uncertain, and a decision with a reason. Uncertain means a human looks.

## 3. Users and jobs

**Meera (CG operator):** checks documents all day, wants to catch real errors and stop retyping emails.
**Arjun (SU):** sends the paperwork, wants one clear list of fixes.

1. When a document arrives, I want fields extracted with evidence, so I check instead of type.
2. When a value breaks a rule, I want found vs. expected side by side, so I confirm it fast.
3. When a field is unreadable, I want it marked uncertain, so nothing wrong looks approved.
4. When there are several problems, I want one draft listing all of them, so Arjun fixes everything in one go.
5. When someone asks "how many were flagged this week?", I want to ask in plain language and see the SQL, so I can trust the answer.

## 4. Architecture

Three stages, because they fail differently: reading (perception), checking (logic), deciding (policy). One prompt would hide which failed and let the model judge its own reading. Five would add handoffs but no new failure types.

- **Extractor:** PDF or image in, eight fields out (value, confidence, quote, page).
- **Validator:** fields + customer rules in, match / mismatch / uncertain out. Plain Python.
- **Router:** validation in, `auto_approve` / `human_review` / `amendment_request` plus reasoning out. Plain Python.

Typed objects pass between stages in LangGraph. State is checkpointed to SQLite after each step, so a crashed run resumes. **[UPDATE: note your kill-and-resume test.]**

## 5. Tools

- **Extractor:** `gemma3:4b` on local Ollama. Gemini's free tier hit a quota and another provider blocked me, so local it is. Likely less accurate than a big hosted model; I'd compare one on the same test set.
- **Text-to-SQL:** `qwen3:8b` local, behind a read-only single-SELECT guard.
- **Bad scans:** clean the image, one retry, then unsupported values are nulled and sent to a human. Tesseract isn't installed, so image-only files fail loudly. **[UPDATE if tested.]**
- **LangGraph:** matches Nova, gives checkpointing, small graph.
- **Structured output** for fields and SQL, never for decisions.
- **SQLite** now, ClickHouse later. **No RAG:** one rule file fits in YAML, and counts need SQL.

## 6. Trust and evals

- **No made-up fields:** null if absent; every value needs a quote found in the document text; otherwise retry once, then null.
- **Low confidence:** any uncertain or missing field goes to human review, never auto-approve.
- **Limits:** one retry, three-page cap, errors stored and shown.
- **Offline eval:** 6 synthetic documents, `gemma3:4b`: 100% field accuracy, 0/46 hallucinated, 6/6 decisions. Caught rate untested. A smoke test, not proof. **[UPDATE: add damaged documents.]**
- **Online metric:** share of auto-approvals a human later overrides.

## 7. Metrics

**North star:** share of documents where the operator accepts the decision unchanged.

**Supporting:** critical-field accuracy, hallucination rate, caught rate, false auto-approvals (target 0), p95 time to decision, failed-run share, human-review share, amendment cycles per shipment.

**Go (2-week pilot):** no wrong approval reaches the customer, critical fields at least 95%, hallucination under 1%, at least 60% of decisions accepted unchanged.
**No-go:** an uncertain field can reach approval, or a decision can't be traced to evidence.

## 8. What's next

1. Real customer-labeled documents, including scans.
2. OCR for image-only files, then rerun evals.
3. Email trigger and cross-document checks.
4. Supervised pilot logging operator overrides.

Data and OCR come before UI polish because everything measured so far is synthetic.

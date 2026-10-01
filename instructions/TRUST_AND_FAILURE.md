# TRUST AND FAILURE RULES

## No hallucinated fields
- Extractor returns null (never a guess) when a field is absent.
- Every non-null value needs a source_quote.
- Post-check: quote must appear in the doc text (text layer via pdfplumber/PyMuPDF, or OCR fallback). If not found: downgrade confidence, status = uncertain.

## Confidence
Combine: model self-reported score + grounding check + format validity (HS code regex, known port names, weight is numeric with unit). Thresholds in config.py. Do not trust self-reported confidence alone.

## Low confidence
uncertain or null field -> Validator marks uncertain -> Router must choose human_review. Auto-approve is impossible if any field is uncertain or null. Silent approval is the worst outcome.

## Bad document quality
Preprocess (deskew, contrast, higher DPI). Retry extraction once with the fallback path. Still bad -> human_review with the reason. No further loops.

## Loop / cost guardrails
- Max 1 extraction retry, max 1 LLM fuzzy-match call per field.
- Per-document token and cost cap (abort -> human_review, status "cost_cap_hit").
- Per-call timeout; exponential backoff with hard cap.
- Fail loud: errors go to the runs table and the UI. Never swallow exceptions.

## Text-to-SQL safety
Read-only DB connection, single SELECT only (reject anything else), schema-limited prompt, LIMIT enforced, show the SQL and the raw rows behind the answer. If the question can't be answered from the schema, say so.

## Hard rules
- Never send emails or external actions.
- No approve path that bypasses the Validator.
- Every decision is stored with its reasoning.

## Real failure log
Append to docs/failures.md as you test: doc, symptom, root cause, fix. The write-up's "three nastiest failure modes" must come from here.

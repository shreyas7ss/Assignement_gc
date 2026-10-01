# Failure Log

Entries distinguish observed live behavior from deterministic test fixtures. Gemini and Groq incidents below are historical; the active provider is now local Ollama. The saved examples are synthetic; no customer document failures have been observed.

## Live NL-to-SQL Enum Mismatch

- **Input:** `How many shipments were auto-approved?`
- **Symptom:** Gemini generated `decision = 'auto-approved'`; the guarded query returned zero rows despite one auto-approved demo shipment.
- **Root cause:** The prompt described the column but omitted its exact stored enum values, so natural-language phrasing was used as a SQL literal.
- **Fix:** Add exact decision and status enums to the prompt, with tests that assert the literals are present. A follow-up query using the same concept generated `decision = 'auto_approve'` and returned one row.
- **Evidence:** Reproduced against `.data/demo/pipeline.sqlite`; query and answer are in [sample_queries.md](sample_queries.md).

## Live Field Alias and Column Mismatch

- **Input:** `Which shipment requested an amendment and what consignee value was found?`
- **Symptom:** Gemini used `fields.field = 'consignee'` and selected `fields.value`; the guarded query returned no rows.
- **Root cause:** The prompt omitted the exact allowed field names and did not distinguish the extracted `value` from validator `found`.
- **Fix:** Enumerate exact field keys and define `found` versus `value` in the prompt. A precise follow-up query returned `messy_scanned_invoice.pdf` and `ACME Trading Co.`.
- **Evidence:** Reproduced against `.data/demo/pipeline.sqlite`; see [sample_queries.md](sample_queries.md).

## Ungrounded Extraction Regression Fixture

- **Document:** Synthetic PNG fixture in `tests/test_extractor.py` with OCR text `Invoice No. INV-2048`.
- **Symptom:** A fake provider returns `INV-2048` with a quote absent from the document text, including after the fallback attempt.
- **Root cause:** Model output alone cannot prove that its quote is in the source.
- **Fix:** Ground every non-null quote against document text; retry once, then null the unsupported field and set confidence to zero.
- **Evidence:** `test_ungrounded_value_is_null_after_one_retry` passes. This is a regression fixture, not an observed live Gemini mistake.
- **Evidence:** `test_ungrounded_value_is_null_after_one_retry` passes. This is a regression fixture, not an observed live Gemini mistake.

## Gemini Service Unavailable During Sample Refresh

- **Input:** `samples/docs/clean_invoice.pdf`, uploaded through the FastAPI run endpoint.
- **Symptom:** Gemini returned HTTP 503 on the request and its single bounded retry. The API returned HTTP 502 and stored the failed run as `human_review`; prior successful sample output was left intact.
- **Root cause:** Gemini service availability; the response did not identify a document-specific cause.
- **Fix:** The client performs one retry for transient 503 errors, then fails loudly. The API persists the error rather than silently approving or overwriting a successful output.
- **Evidence:** Failed run `b26d85efe8254bd4a45e0c18d71fe6e4` in `.data/demo/pipeline.sqlite`.

## Gemini Free-Tier Request Quota Exhausted

- **Input:** The user-uploaded PDF from the review UI.
- **Symptom:** Gemini returned HTTP 429 with `RESOURCE_EXHAUSTED`; the provider named `generate_content_free_tier_requests`, limit 20, for `gemini-2.5-flash`, and advised checking plan and billing.
- **Root cause:** The Gemini project had exhausted its free-tier request allowance. The provider returned this detail on a retry after the original UI failure.
- **Fix:** The client now preserves the sanitized provider reason, the API returns HTTP 429, and the UI identifies rate-limit/quota errors. Code cannot increase the account quota; check Google AI Studio usage/billing or use an eligible project/key.
- **Evidence:** Reproduced with the original saved upload; latest failed shipment `74a05309524943b9a4eadf21f2a76366`.

## Groq API Blocked by Cloudflare

- **Input:** Synthetic one-page `samples/docs/clean_invoice.pdf` sent through the Groq-backed API after the key was updated.
- **Symptom:** Groq returned HTTP 403 with the plain-text body `error code: 1010`; the API stored a failed human-review shipment.
- **Root cause:** The response is a Cloudflare access block, not a model JSON/schema or document extraction failure. The provider response does not distinguish whether the restriction is based on network egress, account access, or another edge policy.
- **Fix:** Preserve and show the sanitized provider body, stop repeated calls, and verify access from the user's network/Groq account before retrying.
- **Evidence:** Shipment `a9a289a1c1be4b47b8e006d8360cc30d` in `.data/pipeline.sqlite`.

## Known Environment Limitation

Tesseract is not installed in the current environment. Image-only documents and scanned PDF pages without searchable text therefore fail loudly rather than being independently OCR-grounded. The messy demo and evaluation PDFs have hidden text layers and do not prove that this OCR path works.

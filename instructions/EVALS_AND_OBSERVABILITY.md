# EVALS AND OBSERVABILITY

## Offline eval (required)
- Labeled set: >= 6 docs (mix clean/messy), ground truth in evals/dataset/*.json.
- Script: evals/run_evals.py, outputs a table:
  - per-field exact/normalized accuracy
  - hallucination rate (value present in output but not in doc)
  - "caught rate": of wrong fields, % marked uncertain/mismatch instead of match
  - decision correctness vs expected decision
- Save results to evals/results.md for the write-up.

## Online metric (define and, if possible, simulate)
Human override rate of auto-approved docs (lower is better). Secondary: % routed to human_review, median time-to-decision.

## Logging
Structured JSON logs: run_id, shipment_id, agent, latency_ms, tokens_in/out, cost_usd, model, status.
Persist to the runs table so the UI and write-up use real numbers.

## Production story (for write-up, 50 customers)
- Trace id per email/shipment carried through all agents (Langfuse / OpenTelemetry style).
- Dashboard: docs/day, decision mix, uncertain-rate by field, cost/doc, p50/p95 latency per agent, override rate, failures by type.

## Cost and latency (measure, don't guess)
- Cost per doc = sum of runs.cost_usd. Note where it blows up (multi-page PDFs, retries, high-res images) and the control (page cap, DPI cap, cost cap).
- Slowest hop is likely the vision call. Mitigations: downscale, page selection, parallelize per page, cache by file hash.

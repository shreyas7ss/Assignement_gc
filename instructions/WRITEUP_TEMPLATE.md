# TECHNICAL WRITE-UP TEMPLATE (1-2 pages)

1. Architecture diagram (Mermaid): boxes, arrows, data flow, where state lives (checkpointer, SQLite).
2. Three nastiest failure modes: each with a real example from docs/failures.md, how it was caught, and the fix.
3. Observability for 50 customers: tracing one shipment from email to verified output; dashboard contents.
4. Cost: measured cost per document, where it blows up, controls.
5. Latency: slowest hop, measured, and the fix.
6. If I had a week instead of a day.

Rule: every number comes from the runs table or evals/results.md.

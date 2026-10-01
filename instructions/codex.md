# CLAUDE.md — Nova Trade-Doc Pipeline (GoComet DAW, Part 1)

Runnable-on-a-laptop multi-agent pipeline:
trade doc (PDF/image) -> Extractor -> Validator -> Router -> SQLite -> NL query -> minimal UI.

This is a hiring assignment. The chain being alive matters more than polish. Graded on architecture, AI craft (hallucination, confidence, evals, cost, observability), a working end-to-end demo, and clear reasoning.

## Read these before coding (imported)
@docs/ARCHITECTURE.md
@docs/TRUST_AND_FAILURE.md
@docs/EVALS_AND_OBSERVABILITY.md
@docs/BUILD_PLAN.md

Templates for later (read only when writing docs):
- docs/PRD_TEMPLATE.md
- docs/WRITEUP_TEMPLATE.md

## Hard requirements
1. Extractor: vision LLM; fields consignee_name, hs_code, port_of_loading, port_of_discharge, incoterms, goods_description, gross_weight, invoice_number. Each = {value, confidence, source_quote, page}.
2. Validator: per field match | mismatch | uncertain. Mismatch includes found + expected. Never silently approve.
3. Router: exactly one of auto_approve | human_review | amendment_request, with written reasoning.
4. Storage + NL query: SQLite, text-to-SQL, show the SQL used.
5. Minimal UI: real state from a real run (fields, confidence, validation, decision, reasoning).

## Working style
- Small vertical slices. Run each slice before moving on. Never claim something works unless you executed it; report what you ran and what happened.
- Simple readable code: type hints, small functions, no dead code, no over-abstraction.
- Write tests first for the Validator and the SQL guard.
- Log real failures to docs/failures.md as they happen (doc, symptom, cause, fix).
- Record real cost/latency per run; write-up numbers must be measured.
- Ask before adding dependencies beyond: fastapi, uvicorn, pydantic, langgraph, langgraph-checkpoint-sqlite, anthropic, pdfplumber or pymupdf, pillow, pyyaml, streamlit, pytest.
- Never send emails or take external actions.

## Do NOT write for me
- PRD section 1 (What is Nova / FDE / System of Outcomes). I write it myself. You may critique it.
- Demo video narration.

## Definition of done
- README lets a stranger run it in under 5 minutes (.env.example, one command each for backend and UI).
- 2+ sample docs (one clean, one messy) processed with real saved outputs.
- docs/sample_queries.md with real NL queries and answers.
- Mermaid architecture diagram in docs/WRITEUP.md.

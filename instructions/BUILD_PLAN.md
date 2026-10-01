# BUILD PLAN (slices) — run in order, verify each before the next

1. schemas.py — Pydantic: FieldValue, ExtractionResult, FieldResult, ValidationResult, Decision.
2. Extractor — one clean PDF, then one messy image. Show raw JSON output. Add grounding check.
3. Rules + Validator — customer_acme.yaml, normalizers, deterministic compare, optional LLM fuzzy match. Tests first.
4. Router — 3 outcomes, reasoning, amendment draft listing field/found/expected. Test with hand-built ValidationResults for all three outcomes.
5. graph.py — LangGraph wiring + SqliteSaver. Kill mid-run and resume.
6. db.py — schema + writes from graph output.
7. nl_query.py — guarded text-to-SQL. Tests for the guard (reject DROP, multiple statements, etc.).
8. FastAPI + Streamlit UI — upload doc, show fields, confidence, validation, decision, reasoning.
9. Evals — labeled set, run_evals.py, results.md.
10. Docs — README, PRD, write-up, sample_queries.md, failures.md.

## Starter prompts for Claude Code
- Slice 1-2: "Read CLAUDE.md and the imported docs. Implement only schemas.py and the Extractor. Run it on samples/<clean file> and show me the output, including the grounding check result."
- Plan mode before slice 5: "Propose the LangGraph state design and checkpoint strategy. Don't write code yet."
- Review pass: "Review the Validator for any path where an uncertain or null field can result in auto_approve. Write a failing test if you find one."

## Time budget (~12-14h)
Setup 1h, Extractor 2h, Validator 2h, Router+graph 1.5h, Storage+NL query+UI 2h, Evals 2h, Docs 2.5h, Demo 1h.

# ARCHITECTURE

## Stack (decided)
Python 3.11+, FastAPI, LangGraph, SQLite, Streamlit (reusable for Part 2), local Ollama REST API.
The extractor and NL-query generator use the locally running Ollama service.
Model names live in config/env only, never in logic.

## Repo layout
```
nova-pipeline/
  app/
    agents/{extractor,validator,router}.py
    graph.py          # LangGraph wiring + checkpointer
    schemas.py        # Pydantic models
    rules/customer_acme.yaml
    db.py             # SQLite schema + writes
    nl_query.py       # guarded text-to-SQL
    config.py         # models, thresholds, cost caps
    main.py           # FastAPI
  ui/streamlit_app.py
  evals/{dataset/,run_evals.py}
  samples/
  docs/
  tests/
```

## Why three agents (defend in PRD)
- Different inputs: Extractor sees pixels/text; Validator sees structured JSON + rules; Router sees validation results.
- Different failure modes: perception errors vs rule errors vs policy errors.
- Different model needs: strong vision model vs mostly no LLM vs cheap model for explanation.
- Independently evaluable: each has its own eval and can be swapped or retried alone.
- Not five: splitting further (e.g. per-field extractors) adds handoffs without adding independent failure modes.
- Not one prompt: a single prompt hides which stage failed, can't be checkpointed per step, and lets the model "approve" its own extraction.

## Roles (planner/executor/verifier framing)
- Extractor = executor: document -> ExtractionResult.
- Validator = verifier: ExtractionResult + rules -> ValidationResult. Mostly deterministic code (normalize, then compare). LLM only for fuzzy cases (e.g. "ACME Corp." vs "Acme Corporation Ltd"), returning only match/uncertain, never approving.
- Router = planner/decider: ValidationResult -> Decision + reasoning (+ amendment draft).

## Handoffs
Typed Pydantic models only: ExtractionResult, ValidationResult, Decision. No free text between agents. Shared state = LangGraph state object, persisted.

## State and crash recovery
LangGraph `SqliteSaver` checkpointer keyed by run_id/shipment_id. Each node's output is written before the next starts. Resume = re-invoke with the same thread id. Demo this by killing the process mid-run.

## Model choices
- Extractor: configured Ollama vision model (accuracy matters most, up to three rendered PDF pages per request).
- NL-to-SQL: configured local Ollama model with JSON-schema output; generated SQL is still guarded locally.
- Structured output / tool use: yes for Extractor and Router output shape. No for validation decisions.

## Storage schema (minimum)
- shipments(id, doc_name, customer, decision, created_at)
- fields(shipment_id, field, value, confidence, status, found, expected, source_quote)
- runs(run_id, shipment_id, agent, latency_ms, tokens_in, tokens_out, cost_usd, model, status, error)

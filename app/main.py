from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from app.agents.extractor import extract_document
from app.config import MAX_UPLOAD_BYTES, OLLAMA_VISION_MODEL
from app.ollama_client import OllamaAPIError
from app.db import (
    database_connection,
    initialize_database,
    persist_pipeline_failure,
    persist_pipeline_output,
    record_agent_run,
)
from app.graph import DEFAULT_RULES_PATH, open_checkpointed_pipeline, thread_config
from app.nl_query import SQLQueryError, answer_question
from app.schemas import FIELD_NAMES, ExtractionResult
from app.agents.validator import load_customer_rules


SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
Extractor = Callable[[str | Path], ExtractionResult]


class QueryRequest(BaseModel):
    question: str


def create_app(
    *,
    data_dir: str | Path | None = None,
    extractor: Extractor = extract_document,
    rules_path: str | Path = DEFAULT_RULES_PATH,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
) -> FastAPI:
    root = Path(data_dir or os.environ.get("NOVA_DATA_DIR", ".data")).resolve()
    upload_dir = root / "uploads"
    database_path = root / "pipeline.sqlite"
    checkpoint_path = root / "checkpoints.sqlite"
    rules = load_customer_rules(rules_path)

    root.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    with database_connection(database_path) as connection:
        initialize_database(connection)

    application = FastAPI(title="Nova Trade-Document Pipeline")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/runs")
    async def create_run(
        request: Request,
        filename: str = Query(..., min_length=1, max_length=255),
    ) -> dict[str, object]:
        safe_name = Path(filename).name
        if safe_name != filename or safe_name in {".", ".."}:
            raise HTTPException(status_code=400, detail="filename must be a plain file name")
        if Path(safe_name).suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
            raise HTTPException(status_code=415, detail="unsupported document file type")

        declared_length = request.headers.get("content-length")
        if declared_length and int(declared_length) > max_upload_bytes:
            raise HTTPException(status_code=413, detail="document exceeds upload size limit")

        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > max_upload_bytes:
                raise HTTPException(status_code=413, detail="document exceeds upload size limit")
        if not body:
            raise HTTPException(status_code=400, detail="document body must not be empty")

        shipment_id = uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        document_path = upload_dir / f"{shipment_id}_{safe_name}"
        document_path.write_bytes(body)
        started_at = time.perf_counter()

        try:
            with open_checkpointed_pipeline(
                checkpoint_path,
                rules_path=rules_path,
                extractor=extractor,
            ) as graph:
                state = graph.invoke(
                    {
                        "run_id": run_id,
                        "shipment_id": shipment_id,
                        "document_path": str(document_path),
                    },
                    config=thread_config(run_id),
                )

            extraction = state["extraction"]
            validation = state["validation"]
            decision = state["decision"]
            usage_records = state.get("extractor_usage", [])
            input_tokens = _sum_usage(usage_records, "tokens_in")
            output_tokens = _sum_usage(usage_records, "tokens_out")
            latency_ms = (time.perf_counter() - started_at) * 1000
            with database_connection(database_path) as connection:
                persist_pipeline_output(
                    connection,
                    shipment_id=shipment_id,
                    doc_name=safe_name,
                    customer=rules.customer,
                    extraction=extraction,
                    validation=validation,
                    decision=decision,
                )
                record_agent_run(
                    connection,
                    run_id=run_id,
                    shipment_id=shipment_id,
                    agent="extractor",
                    latency_ms=state["extractor_latency_ms"],
                    tokens_in=input_tokens,
                    tokens_out=output_tokens,
                    cost_usd=None,
                    model=OLLAMA_VISION_MODEL,
                    status="success",
                )
                record_agent_run(
                    connection,
                    run_id=run_id,
                    shipment_id=shipment_id,
                    agent="validator",
                    latency_ms=state["validator_latency_ms"],
                    tokens_in=None,
                    tokens_out=None,
                    cost_usd=None,
                    model=None,
                    status="success",
                )
                record_agent_run(
                    connection,
                    run_id=run_id,
                    shipment_id=shipment_id,
                    agent="router",
                    latency_ms=state["router_latency_ms"],
                    tokens_in=None,
                    tokens_out=None,
                    cost_usd=None,
                    model=None,
                    status="success",
                )
                record_agent_run(
                    connection,
                    run_id=run_id,
                    shipment_id=shipment_id,
                    agent="pipeline",
                    latency_ms=latency_ms,
                    tokens_in=None,
                    tokens_out=None,
                    cost_usd=None,
                    model=OLLAMA_VISION_MODEL,
                    status="success",
                )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            with database_connection(database_path) as connection:
                persist_pipeline_failure(
                    connection,
                    shipment_id=shipment_id,
                    run_id=run_id,
                    doc_name=safe_name,
                    customer=rules.customer,
                    error=str(exc),
                    latency_ms=latency_ms,
                    model=OLLAMA_VISION_MODEL,
                )
            raise HTTPException(
                status_code=(
                    exc.status_code
                    if isinstance(exc, OllamaAPIError) and exc.status_code in {404, 503}
                    else 502
                ),
                detail={
                    "error": str(exc),
                    "run_id": run_id,
                    "shipment_id": shipment_id,
                },
            ) from exc

        return _format_run_response(
            run_id=run_id,
            shipment_id=shipment_id,
            document_name=safe_name,
            extraction=extraction,
            validation=validation,
            decision=decision,
        )

    @application.get("/shipments/{shipment_id}")
    def get_shipment(shipment_id: str) -> dict[str, object]:
        with database_connection(database_path) as connection:
            shipment = connection.execute(
                "SELECT * FROM shipments WHERE id = ?",
                (shipment_id,),
            ).fetchone()
            if shipment is None:
                raise HTTPException(status_code=404, detail="shipment not found")
            fields = connection.execute(
                "SELECT * FROM fields WHERE shipment_id = ? ORDER BY field",
                (shipment_id,),
            ).fetchall()
            runs = connection.execute(
                "SELECT * FROM runs WHERE shipment_id = ? ORDER BY created_at, agent",
                (shipment_id,),
            ).fetchall()
        return {
            "shipment": dict(shipment),
            "fields": [dict(row) for row in fields],
            "runs": [dict(row) for row in runs],
        }

    @application.post("/queries")
    def query_database(query: QueryRequest) -> dict[str, object]:
        try:
            result = answer_question(database_path, query.question)
        except SQLQueryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"sql": result.sql, "rows": result.rows}

    return application


def _format_run_response(
    *,
    run_id: str,
    shipment_id: str,
    document_name: str,
    extraction: ExtractionResult,
    validation: object,
    decision: object,
) -> dict[str, object]:
    fields = []
    for field_name, value in extraction.field_values().items():
        field_result = validation.fields[field_name]
        fields.append(
            {
                "field": field_name,
                **value.model_dump(),
                **field_result.model_dump(),
            }
        )
    return {
        "run_id": run_id,
        "shipment_id": shipment_id,
        "document_name": document_name,
        "fields": fields,
        "decision": decision.model_dump(),
    }


def _sum_usage(
    usage_records: list[dict[str, int | float | None]],
    field: str,
) -> int | None:
    values = [record[field] for record in usage_records if isinstance(record.get(field), int)]
    return sum(values) if values else None
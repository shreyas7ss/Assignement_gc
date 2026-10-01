from __future__ import annotations

import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterator, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.extractor import extract_document
from app.agents.router import route_validation
from app.agents.validator import CustomerRules, load_customer_rules, validate_extraction
from app.schemas import Decision, ExtractionResult, ValidationResult


class PipelineState(TypedDict, total=False):
    run_id: str
    shipment_id: str
    document_path: str
    extraction: ExtractionResult
    extractor_usage: list[dict[str, int | float | None]]
    extractor_latency_ms: float
    validation: ValidationResult
    validator_latency_ms: float
    decision: Decision
    router_latency_ms: float


Extractor = Callable[[str | Path], ExtractionResult]
DEFAULT_RULES_PATH = Path(__file__).parent / "rules" / "customer_acme.yaml"
CHECKPOINT_SCHEMA_MODELS = [
    ("app.schemas", "AmendmentItem"),
    ("app.schemas", "Decision"),
    ("app.schemas", "ExtractionResult"),
    ("app.schemas", "FieldResult"),
    ("app.schemas", "FieldValue"),
    ("app.schemas", "ValidationResult"),
]


def thread_config(run_id: str) -> dict[str, dict[str, str]]:
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise ValueError("run_id must not be empty")
    return {"configurable": {"thread_id": normalized_run_id}}


def build_pipeline(
    checkpointer: BaseCheckpointSaver,
    *,
    rules_path: str | Path = DEFAULT_RULES_PATH,
    extractor: Extractor = extract_document,
    interrupt_after: list[str] | None = None,
) -> Any:
    rules: CustomerRules = load_customer_rules(rules_path)
    graph = StateGraph(PipelineState)

    def extract_node(state: PipelineState) -> dict[str, Any]:
        started = perf_counter()
        usage: list[dict[str, int | float | None]] = []
        if extractor is extract_document:
            extraction = extractor(
                state["document_path"],
                usage_callback=usage.append,
            )
        else:
            extraction = extractor(state["document_path"])
        return {
            "extraction": extraction,
            "extractor_usage": usage,
            "extractor_latency_ms": (perf_counter() - started) * 1000,
        }

    def validate_node(state: PipelineState) -> dict[str, Any]:
        started = perf_counter()
        validation = validate_extraction(state["extraction"], rules)
        return {
            "validation": validation,
            "validator_latency_ms": (perf_counter() - started) * 1000,
        }

    def route_node(state: PipelineState) -> dict[str, Any]:
        started = perf_counter()
        decision = route_validation(state["validation"])
        return {
            "decision": decision,
            "router_latency_ms": (perf_counter() - started) * 1000,
        }

    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)
    graph.add_node("route", route_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "validate")
    graph.add_edge("validate", "route")
    graph.add_edge("route", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )


@contextmanager
def open_checkpointed_pipeline(
    database_path: str | Path,
    *,
    rules_path: str | Path = DEFAULT_RULES_PATH,
    extractor: Extractor = extract_document,
    interrupt_after: list[str] | None = None,
) -> Iterator[Any]:
    connection_string = os.fspath(database_path)
    if connection_string != ":memory:":
        Path(connection_string).parent.mkdir(parents=True, exist_ok=True)

    serializer = JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_SCHEMA_MODELS)
    with closing(
        sqlite3.connect(connection_string, check_same_thread=False)
    ) as connection:
        checkpointer = SqliteSaver(connection, serde=serializer)
        checkpointer.setup()
        yield build_pipeline(
            checkpointer,
            rules_path=rules_path,
            extractor=extractor,
            interrupt_after=interrupt_after,
        )
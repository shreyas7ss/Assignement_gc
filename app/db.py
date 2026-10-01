from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.schemas import FIELD_NAMES, Decision, ExtractionResult, ValidationResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS shipments (
    id TEXT PRIMARY KEY,
    doc_name TEXT NOT NULL,
    customer TEXT NOT NULL,
    decision TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fields (
    shipment_id TEXT NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    value TEXT,
    confidence REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('match', 'mismatch', 'uncertain')),
    found TEXT,
    expected TEXT,
    source_quote TEXT,
    page INTEGER,
    PRIMARY KEY (shipment_id, field)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT NOT NULL,
    shipment_id TEXT NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    latency_ms REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    model TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, agent)
);
"""


@contextmanager
def database_connection(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def persist_pipeline_output(
    connection: sqlite3.Connection,
    *,
    shipment_id: str,
    doc_name: str,
    customer: str,
    extraction: ExtractionResult,
    validation: ValidationResult,
    decision: Decision,
) -> None:
    if set(extraction.field_values()) != set(validation.fields):
        raise ValueError("extraction and validation must contain the same fields")

    with connection:
        connection.execute(
            """
            INSERT INTO shipments (id, doc_name, customer, decision, reasoning)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                doc_name = excluded.doc_name,
                customer = excluded.customer,
                decision = excluded.decision,
                reasoning = excluded.reasoning
            """,
            (shipment_id, doc_name, customer, decision.outcome, decision.reasoning),
        )
        connection.execute("DELETE FROM fields WHERE shipment_id = ?", (shipment_id,))
        connection.executemany(
            """
            INSERT INTO fields (
                shipment_id, field, value, confidence, status, found, expected,
                source_quote, page
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    shipment_id,
                    field_name,
                    extracted.value,
                    extracted.confidence,
                    validation.fields[field_name].status,
                    validation.fields[field_name].found,
                    validation.fields[field_name].expected,
                    extracted.source_quote,
                    extracted.page,
                )
                for field_name, extracted in extraction.field_values().items()
            ],
        )


def record_agent_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    shipment_id: str,
    agent: str,
    latency_ms: float | None,
    tokens_in: int | None,
    tokens_out: int | None,
    cost_usd: float | None,
    model: str | None,
    status: str,
    error: str | None = None,
) -> None:
    with connection:
        connection.execute(
            """
            INSERT INTO runs (
                run_id, shipment_id, agent, latency_ms, tokens_in, tokens_out,
                cost_usd, model, status, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, agent) DO UPDATE SET
                shipment_id = excluded.shipment_id,
                latency_ms = excluded.latency_ms,
                tokens_in = excluded.tokens_in,
                tokens_out = excluded.tokens_out,
                cost_usd = excluded.cost_usd,
                model = excluded.model,
                status = excluded.status,
                error = excluded.error
            """,
            (
                run_id,
                shipment_id,
                agent,
                latency_ms,
                tokens_in,
                tokens_out,
                cost_usd,
                model,
                status,
                error,
            ),
        )


def persist_pipeline_failure(
    connection: sqlite3.Connection,
    *,
    shipment_id: str,
    run_id: str,
    doc_name: str,
    customer: str,
    error: str,
    latency_ms: float,
    model: str | None,
) -> None:
    reasoning = f"Pipeline failed before producing a safe decision: {error}"
    with connection:
        connection.execute(
            """
            INSERT INTO shipments (id, doc_name, customer, decision, reasoning)
            VALUES (?, ?, ?, 'human_review', ?)
            ON CONFLICT(id) DO UPDATE SET
                doc_name = excluded.doc_name,
                customer = excluded.customer,
                decision = excluded.decision,
                reasoning = excluded.reasoning
            """,
            (shipment_id, doc_name, customer, reasoning),
        )
        connection.execute("DELETE FROM fields WHERE shipment_id = ?", (shipment_id,))
        connection.executemany(
            """
            INSERT INTO fields (
                shipment_id, field, value, confidence, status, found, expected,
                source_quote, page
            ) VALUES (?, ?, NULL, 0, 'uncertain', NULL, NULL, NULL, NULL)
            """,
            [(shipment_id, field_name) for field_name in FIELD_NAMES],
        )
        connection.execute(
            """
            INSERT INTO runs (
                run_id, shipment_id, agent, latency_ms, tokens_in, tokens_out,
                cost_usd, model, status, error
            ) VALUES (?, ?, 'pipeline', ?, NULL, NULL, NULL, ?, 'failed', ?)
            ON CONFLICT(run_id, agent) DO UPDATE SET
                shipment_id = excluded.shipment_id,
                latency_ms = excluded.latency_ms,
                model = excluded.model,
                status = excluded.status,
                error = excluded.error
            """,
            (run_id, shipment_id, latency_ms, model, error),
        )
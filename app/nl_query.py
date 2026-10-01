from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from app.config import MAX_QUERY_ROWS, OLLAMA_BASE_URL, OLLAMA_TEXT_MODEL
from app.ollama_client import OllamaAPIError, OllamaRestClient


ALLOWED_TABLES = frozenset({"shipments", "fields", "runs"})
SQL_GENERATOR_PROMPT = """Translate the user's question into one SQLite SELECT statement.
Return SQL only. Do not use writes, pragmas, attached databases, or tables outside
this schema. The application will enforce a row limit.

Tables:
- shipments(id, doc_name, customer, decision, reasoning, created_at)
- fields(shipment_id, field, value, confidence, status, found, expected, source_quote, page)
- runs(run_id, shipment_id, agent, latency_ms, tokens_in, tokens_out, cost_usd, model, status, error, created_at)

Allowed shipments.decision values: 'auto_approve', 'human_review', 'amendment_request'.
Allowed fields.status values: 'match', 'mismatch', 'uncertain'. Use these exact literals.
Allowed fields.field values: 'consignee_name', 'hs_code', 'port_of_loading',
'port_of_discharge', 'incoterms', 'goods_description', 'gross_weight', 'invoice_number'.
Use fields.found for the validator's found value and fields.expected for its rule value;
fields.value is the raw extractor output.

User question: {question}
"""


class SQLQueryError(ValueError):
    pass


@dataclass(frozen=True)
class QueryResult:
    sql: str
    rows: list[dict[str, object]]


def answer_question(
    database_path: str | Path,
    question: str,
    *,
    sql_generator: Callable[[str], str] | None = None,
    row_limit: int = MAX_QUERY_ROWS,
) -> QueryResult:
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must not be empty")
    prompt = SQL_GENERATOR_PROMPT.format(question=normalized_question)
    generated_sql = (sql_generator or _ollama_sql_generator)(prompt)
    return execute_guarded_query(database_path, generated_sql, row_limit=row_limit)


def _ollama_sql_generator(prompt: str) -> str:
    try:
        response = OllamaRestClient(base_url=OLLAMA_BASE_URL).generate_content(
            model=OLLAMA_TEXT_MODEL,
            system_instruction=(
                "Return JSON only, containing one SQLite SELECT statement in the sql field. "
                "Never generate writes, pragmas, attached databases, or markdown."
            ),
            prompt=prompt,
            parts=[],
            response_schema={
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        )
    except OllamaAPIError as exc:
        raise SQLQueryError(str(exc)) from exc

    try:
        payload = json.loads(response)
        sql = payload["sql"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SQLQueryError("Ollama did not return a JSON object with a sql field") from exc
    if not isinstance(sql, str) or not sql.strip():
        raise SQLQueryError("Ollama returned an empty SQL query")
    return sql.strip()


def execute_guarded_query(
    database_path: str | Path,
    sql: str,
    *,
    row_limit: int = MAX_QUERY_ROWS,
) -> QueryResult:
    if not isinstance(row_limit, int) or row_limit < 1:
        raise ValueError("row_limit must be a positive integer")
    enforced_limit = min(row_limit, MAX_QUERY_ROWS)
    query = sql.strip()
    if not re.match(r"(?is)^(SELECT|WITH)\b", query):
        raise SQLQueryError("Only a single SELECT query is allowed")

    query = query.removesuffix(";").rstrip()
    if not query:
        raise SQLQueryError("Query must not be empty")
    guarded_sql = f"SELECT * FROM ({query}) AS guarded_query LIMIT {enforced_limit}"

    path = Path(database_path).resolve()
    uri_path = quote(path.as_posix(), safe="/:\\")
    connection_uri = f"file:{uri_path}?mode=ro"
    try:
        with closing(sqlite3.connect(connection_uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.set_authorizer(_read_authorizer)
            connection.set_progress_handler(lambda: 1, 100_000)
            cursor = connection.execute(guarded_sql)
            rows = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        raise SQLQueryError(f"Query rejected or failed: {exc}") from exc

    return QueryResult(sql=guarded_sql, rows=rows)


def _read_authorizer(
    action: int,
    argument_one: str | None,
    argument_two: str | None,
    database_name: str | None,
    trigger_name: str | None,
) -> int:
    del database_name, trigger_name
    if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ and argument_one in ALLOWED_TABLES:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        function_name = (argument_two or argument_one or "").casefold()
        if function_name in {"load_extension", "readfile", "writefile"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY
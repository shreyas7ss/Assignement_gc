import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import database_connection, initialize_database
from app.ollama_client import OllamaRestClient
from app.nl_query import (
    SQLQueryError,
    _ollama_sql_generator,
    SQL_GENERATOR_PROMPT,
    answer_question,
    execute_guarded_query,
)


class NLQueryGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "pipeline.sqlite"
        with database_connection(self.database_path) as connection:
            initialize_database(connection)
            for index in range(4):
                connection.execute(
                    "INSERT INTO shipments (id, doc_name, customer, decision, reasoning) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        f"shipment-{index}",
                        f"invoice-{index}.pdf",
                        "acme_demo",
                        "auto_approve",
                        "all fields matched",
                    ),
                )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_select_returns_rows_and_executable_limited_sql(self) -> None:
        result = execute_guarded_query(
            self.database_path,
            "SELECT id FROM shipments ORDER BY id",
            row_limit=2,
        )

        self.assertEqual(len(result.rows), 2)
        self.assertIn("LIMIT 2", result.sql.upper())
        self.assertEqual(set(result.rows[0]), {"id"})

    def test_rejects_drop_and_preserves_table(self) -> None:
        with self.assertRaises(SQLQueryError):
            execute_guarded_query(self.database_path, "DROP TABLE shipments")

        result = execute_guarded_query(
            self.database_path,
            "SELECT count(*) AS count FROM shipments",
        )
        self.assertEqual(result.rows[0]["count"], 4)

    def test_rejects_multiple_statements(self) -> None:
        with self.assertRaises(SQLQueryError):
            execute_guarded_query(
                self.database_path,
                "SELECT id FROM shipments; DELETE FROM shipments",
            )

    def test_rejects_reads_outside_application_schema(self) -> None:
        with self.assertRaises(SQLQueryError):
            execute_guarded_query(
                self.database_path,
                "SELECT name FROM sqlite_master",
            )

    def test_answer_question_shows_generated_sql_and_raw_rows(self) -> None:
        prompt_seen: list[str] = []

        def sql_generator(prompt: str) -> str:
            prompt_seen.append(prompt)
            return "SELECT decision, count(*) AS total FROM shipments GROUP BY decision"

        result = answer_question(
            self.database_path,
            "How many shipments were approved?",
            sql_generator=sql_generator,
        )

        self.assertIn("shipments", prompt_seen[0])
        self.assertIn("SELECT", result.sql.upper())
        self.assertEqual(result.rows, [{"decision": "auto_approve", "total": 4}])

    def test_ollama_generator_uses_local_text_model(self) -> None:
        with (
            patch("app.nl_query.OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            patch("app.nl_query.OLLAMA_TEXT_MODEL", "qwen3:8b"),
            patch("app.nl_query.OllamaRestClient") as client_type,
        ):
            client_type.return_value.generate_content.return_value = (
                '{"sql":"SELECT count(*) AS total FROM shipments"}'
            )

            sql = _ollama_sql_generator("Count shipments")

        self.assertEqual(sql, "SELECT count(*) AS total FROM shipments")
        client_type.assert_called_once_with(base_url="http://127.0.0.1:11434")
        call = client_type.return_value.generate_content.call_args.kwargs
        self.assertEqual(call["model"], "qwen3:8b")
        self.assertEqual(call["response_schema"]["required"], ["sql"])

    def test_sql_prompt_specifies_exact_decision_values(self) -> None:
        self.assertIn("auto_approve", SQL_GENERATOR_PROMPT)
        self.assertIn("human_review", SQL_GENERATOR_PROMPT)
        self.assertIn("amendment_request", SQL_GENERATOR_PROMPT)
        self.assertIn("consignee_name", SQL_GENERATOR_PROMPT)
        self.assertIn("fields.found", SQL_GENERATOR_PROMPT)

if __name__ == "__main__":
    unittest.main()
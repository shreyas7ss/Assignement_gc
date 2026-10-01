import tempfile
import unittest
from pathlib import Path

from app.db import (
    database_connection,
    initialize_database,
    persist_pipeline_output,
    record_agent_run,
)
from app.schemas import FIELD_NAMES, ExtractionResult, FieldResult, FieldValue, ValidationResult
from app.agents.router import route_validation


class DatabaseTests(unittest.TestCase):
    def pipeline_models(self) -> tuple[ExtractionResult, ValidationResult]:
        values = {
            "consignee_name": "ACME Corporation Ltd",
            "hs_code": "847130",
            "port_of_loading": "Shanghai",
            "port_of_discharge": "Los Angeles",
            "incoterms": "FOB",
            "goods_description": "Portable computers",
            "gross_weight": "1200 kg",
            "invoice_number": "ACME-INV-2026-999",
        }
        extraction = ExtractionResult.model_validate(
            {
                name: FieldValue(
                    value=values[name],
                    confidence=0.96,
                    source_quote=values[name],
                    page=1,
                )
                for name in FIELD_NAMES
            }
        )
        validation = ValidationResult(
            fields={
                name: FieldResult(
                    status="mismatch" if name == "invoice_number" else "match",
                    found=values[name],
                    expected=("ACME-INV-2026-001" if name == "invoice_number" else values[name]),
                    reason="different invoice number" if name == "invoice_number" else "matches",
                )
                for name in FIELD_NAMES
            }
        )
        return extraction, validation

    def test_persists_decision_and_all_field_evidence(self) -> None:
        extraction, validation = self.pipeline_models()
        decision = route_validation(validation)

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "pipeline.sqlite"
            with database_connection(database_path) as connection:
                initialize_database(connection)
                persist_pipeline_output(
                    connection,
                    shipment_id="shipment-1",
                    doc_name="invoice.pdf",
                    customer="acme_demo",
                    extraction=extraction,
                    validation=validation,
                    decision=decision,
                )

            with database_connection(database_path) as connection:
                shipment = connection.execute(
                    "SELECT decision, reasoning FROM shipments WHERE id = ?",
                    ("shipment-1",),
                ).fetchone()
                fields = connection.execute(
                    "SELECT field, value, confidence, status, found, expected, source_quote, page "
                    "FROM fields WHERE shipment_id = ?",
                    ("shipment-1",),
                ).fetchall()

        self.assertEqual(shipment["decision"], "amendment_request")
        self.assertIn("invoice_number", shipment["reasoning"])
        self.assertEqual(len(fields), 8)
        invoice = next(row for row in fields if row["field"] == "invoice_number")
        self.assertEqual(invoice["status"], "mismatch")
        self.assertEqual(invoice["found"], "ACME-INV-2026-999")
        self.assertEqual(invoice["expected"], "ACME-INV-2026-001")
        self.assertEqual(invoice["source_quote"], "ACME-INV-2026-999")
        self.assertEqual(invoice["page"], 1)

    def test_persists_measured_agent_run_fields(self) -> None:
        extraction, validation = self.pipeline_models()
        decision = route_validation(validation)

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "pipeline.sqlite"
            with database_connection(database_path) as connection:
                initialize_database(connection)
                persist_pipeline_output(
                    connection,
                    shipment_id="shipment-1",
                    doc_name="invoice.pdf",
                    customer="acme_demo",
                    extraction=extraction,
                    validation=validation,
                    decision=decision,
                )
                record_agent_run(
                    connection,
                    run_id="run-1",
                    shipment_id="shipment-1",
                    agent="extractor",
                    latency_ms=845.4,
                    tokens_in=1200,
                    tokens_out=800,
                    cost_usd=0.012,
                    model="test-model",
                    status="success",
                )

            with database_connection(database_path) as connection:
                run = connection.execute(
                    "SELECT latency_ms, tokens_in, tokens_out, cost_usd, model, status "
                    "FROM runs WHERE run_id = ? AND agent = ?",
                    ("run-1", "extractor"),
                ).fetchone()

        self.assertEqual(run["latency_ms"], 845.4)
        self.assertEqual(run["tokens_in"], 1200)
        self.assertEqual(run["tokens_out"], 800)
        self.assertEqual(run["cost_usd"], 0.012)
        self.assertEqual(run["model"], "test-model")
        self.assertEqual(run["status"], "success")


if __name__ == "__main__":
    unittest.main()
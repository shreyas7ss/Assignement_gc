import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.ollama_client import OllamaAPIError
from app.main import create_app
from app.schemas import FIELD_NAMES, ExtractionResult, FieldValue


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def matching_extractor(self, document_path: str | Path) -> ExtractionResult:
        values = {
            "consignee_name": "ACME Corporation Ltd",
            "hs_code": "847130",
            "port_of_loading": "Shanghai",
            "port_of_discharge": "Los Angeles",
            "incoterms": "FOB",
            "goods_description": "Portable computers",
            "gross_weight": "1200 kg",
            "invoice_number": "ACME-INV-2026-001",
        }
        return ExtractionResult.model_validate(
            {
                name: FieldValue(
                    value=values[name],
                    confidence=0.99,
                    source_quote=values[name],
                    page=1,
                )
                for name in FIELD_NAMES
            }
        )

    def test_upload_runs_pipeline_persists_output_and_can_be_retrieved(self) -> None:
        app = create_app(
            data_dir=self.data_dir,
            extractor=self.matching_extractor,
        )
        with TestClient(app) as client:
            response = client.post(
                "/runs?filename=invoice.pdf",
                content=b"test document bytes",
                headers={"content-type": "application/pdf"},
            )

            self.assertEqual(response.status_code, 200)
            run = response.json()
            self.assertEqual(run["decision"]["outcome"], "auto_approve")
            self.assertEqual(len(run["fields"]), 8)
            self.assertTrue(run["decision"]["reasoning"])

            saved = client.get(f"/shipments/{run['shipment_id']}")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["shipment"]["decision"], "auto_approve")
        self.assertEqual(len(saved.json()["fields"]), 8)
        run_agents = {run["agent"] for run in saved.json()["runs"]}
        self.assertTrue({"extractor", "validator", "router", "pipeline"}.issubset(run_agents))
        self.assertTrue(
            all(run["latency_ms"] is not None for run in saved.json()["runs"])
        )

    def test_unsupported_file_type_is_rejected(self) -> None:
        app = create_app(data_dir=self.data_dir, extractor=self.matching_extractor)
        with TestClient(app) as client:
            response = client.post(
                "/runs?filename=notes.txt",
                content=b"not a supported document",
            )

        self.assertEqual(response.status_code, 415)

    def test_upload_size_limit_is_enforced(self) -> None:
        app = create_app(
            data_dir=self.data_dir,
            extractor=self.matching_extractor,
            max_upload_bytes=8,
        )
        with TestClient(app) as client:
            response = client.post(
                "/runs?filename=invoice.pdf",
                content=b"more than eight bytes",
            )

        self.assertEqual(response.status_code, 413)

    def test_extraction_failure_is_reported_and_stored_for_review(self) -> None:
        def failing_extractor(document_path: str | Path) -> ExtractionResult:
            raise RuntimeError("test extraction failure")

        app = create_app(data_dir=self.data_dir, extractor=failing_extractor)
        with TestClient(app) as client:
            response = client.post(
                "/runs?filename=invoice.pdf",
                content=b"test document bytes",
            )
            self.assertEqual(response.status_code, 502)
            failure = response.json()["detail"]
            saved = client.get(f"/shipments/{failure['shipment_id']}")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["shipment"]["decision"], "human_review")
        self.assertEqual(len(saved.json()["fields"]), 8)
        self.assertTrue(all(item["status"] == "uncertain" for item in saved.json()["fields"]))
        self.assertEqual(saved.json()["runs"][0]["status"], "failed")

    def test_missing_ollama_model_status_is_preserved_for_ui(self) -> None:
        def model_missing_extractor(document_path: str | Path) -> ExtractionResult:
            raise OllamaAPIError(
                "Ollama returned HTTP 404: model not found",
                status_code=404,
            )

        app = create_app(data_dir=self.data_dir, extractor=model_missing_extractor)
        with TestClient(app) as client:
            response = client.post(
                "/runs?filename=invoice.pdf",
                content=b"test document bytes",
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn("model not found", response.json()["detail"]["error"])


if __name__ == "__main__":
    unittest.main()
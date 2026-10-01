import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pymupdf

from app.agents.extractor import ExtractorError, _extraction_response_schema, extract_document
from app.config import load_app_env
from app.schemas import FIELD_NAMES


class FakeOllamaClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []
        self.last_usage = {"latency_ms": 12.5, "tokens_in": 100, "tokens_out": 24}

    def generate_content(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return json.dumps(self.responses.pop(0))


class ExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.image_path = Path(self.temp_dir.name) / "document.png"
        Image.new("RGB", (16, 16), "white").save(self.image_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def extraction_input(self, invoice_quote: str | None) -> dict[str, object]:
        fields = {
            name: {
                "value": None,
                "confidence": 0.0,
                "source_quote": None,
                "page": None,
            }
            for name in FIELD_NAMES
        }
        if invoice_quote is not None:
            fields["invoice_number"] = {
                "value": "INV-2048",
                "confidence": 0.94,
                "source_quote": invoice_quote,
                "page": 1,
            }
        return fields

    def test_extraction_schema_allows_absent_values_and_evidence(self) -> None:
        schema = _extraction_response_schema()
        field_schema = schema["properties"]["invoice_number"]

        self.assertEqual(
            field_schema["properties"]["value"]["anyOf"],
            [{"type": "string"}, {"type": "null"}],
        )
        self.assertEqual(
            field_schema["properties"]["source_quote"]["anyOf"],
            [{"type": "string"}, {"type": "null"}],
        )
        self.assertEqual(
            field_schema["properties"]["page"]["anyOf"],
            [{"type": "integer"}, {"type": "null"}],
        )

    def test_grounded_value_is_preserved_and_serializable(self) -> None:
        client = FakeOllamaClient([self.extraction_input("Invoice No. INV-2048")])
        result = extract_document(
            self.image_path,
            client,
            model="test-model",
            ocr=lambda _: "Invoice No. INV-2048",
        )

        self.assertEqual(result.invoice_number.value, "INV-2048")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["model"], "test-model")
        self.assertEqual(json.loads(result.model_dump_json())["invoice_number"]["value"], "INV-2048")

    def test_provider_usage_is_forwarded_to_callback(self) -> None:
        client = FakeOllamaClient([self.extraction_input("Invoice No. INV-2048")])
        usage_records: list[dict[str, int | float]] = []

        extract_document(
            self.image_path,
            client,
            model="test-model",
            ocr=lambda _: "Invoice No. INV-2048",
            usage_callback=usage_records.append,
        )

        self.assertEqual(
            usage_records,
            [{"latency_ms": 12.5, "tokens_in": 100, "tokens_out": 24}],
        )

    def test_ungrounded_value_is_null_after_one_retry(self) -> None:
        client = FakeOllamaClient(
            [
                self.extraction_input("made-up invoice"),
                self.extraction_input("still made-up"),
            ]
        )
        result = extract_document(
            self.image_path,
            client,
            model="test-model",
            ocr=lambda _: "Invoice No. INV-2048",
        )

        self.assertEqual(len(client.calls), 2)
        self.assertIsNone(result.invoice_number.value)
        self.assertEqual(result.invoice_number.confidence, 0.0)

    def test_clean_pdf_text_grounds_value_without_retry(self) -> None:
        pdf_path = Path(self.temp_dir.name) / "clean.pdf"
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Invoice No. INV-2048")
        pdf_path.write_bytes(pdf.tobytes())
        pdf.close()
        client = FakeOllamaClient([self.extraction_input("Invoice No. INV-2048")])

        result = extract_document(
            pdf_path,
            client,
            model="test-model",
            ocr=lambda _: self.fail("OCR should not run for a text PDF"),
        )

        self.assertEqual(result.invoice_number.value, "INV-2048")
        self.assertEqual(len(client.calls), 1)

    def test_app_env_loader_reads_key_values_without_overriding_existing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "OLLAMA_VISION_MODEL='qwen3-vl:8b'\nNOVA_DATA_DIR=test-data\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"OLLAMA_VISION_MODEL": "existing-model"},
                clear=True,
            ):
                load_app_env(env_path)

                self.assertEqual(os.environ["OLLAMA_VISION_MODEL"], "existing-model")
                self.assertEqual(os.environ["NOVA_DATA_DIR"], "test-data")

    def test_pdf_with_more_than_three_pages_is_rejected(self) -> None:
        pdf_path = Path(self.temp_dir.name) / "too-many-pages.pdf"
        pdf = pymupdf.open()
        for page_number in range(4):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Page {page_number + 1}")
        pdf_path.write_bytes(pdf.tobytes())
        pdf.close()

        with self.assertRaisesRegex(ExtractorError, "three PDF pages"):
            extract_document(
                pdf_path,
                FakeOllamaClient([]),
                model="qwen-test",
                ocr=lambda _: "",
            )
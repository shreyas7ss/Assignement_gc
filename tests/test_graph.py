import tempfile
import unittest
from pathlib import Path

from app.graph import open_checkpointed_pipeline, thread_config
from app.schemas import FIELD_NAMES, ExtractionResult, FieldValue


class PipelineGraphTests(unittest.TestCase):
    def make_extractor(self, calls: list[str]):
        def extractor(document_path: str | Path) -> ExtractionResult:
            calls.append(str(document_path))
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

        return extractor

    def test_checkpoint_resume_continues_after_completed_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_path = Path(temp_dir) / "pipeline.sqlite"
            calls: list[str] = []
            extractor = self.make_extractor(calls)
            config = thread_config("run-resume-1")
            initial_state = {
                "run_id": "run-resume-1",
                "shipment_id": "shipment-1",
                "document_path": "sample.pdf",
            }

            with open_checkpointed_pipeline(
                checkpoint_path,
                extractor=extractor,
                interrupt_after=["extract"],
            ) as graph:
                paused = graph.invoke(initial_state, config=config)
                self.assertIn("extraction", paused)
                self.assertNotIn("validation", paused)

            with open_checkpointed_pipeline(
                checkpoint_path,
                extractor=extractor,
            ) as graph:
                completed = graph.invoke(None, config=config)

            self.assertEqual(calls, ["sample.pdf"])
            self.assertEqual(completed["decision"].outcome, "auto_approve")
            self.assertEqual(len(completed["validation"].fields), 8)


if __name__ == "__main__":
    unittest.main()
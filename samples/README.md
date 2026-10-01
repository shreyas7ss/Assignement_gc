# Demo Samples

These are synthetic documents created for the prototype; they do not contain customer data.

- `docs/clean_invoice.pdf`: clean text PDF, processed through the FastAPI pipeline.
- `docs/messy_scanned_invoice.pdf`: rasterized low-quality page with a hidden searchable text layer, processed through the same pipeline. It is not an image-only OCR test.
- `outputs/clean_invoice.json` and `outputs/messy_scanned_invoice.json`: successful Gemma 3 4B API responses, including field evidence, validation, and decision.

The latest shipment rows and per-agent telemetry are in the Git-ignored `.data/pipeline.sqlite` database. Run outputs use generated IDs and are not stable across reruns.

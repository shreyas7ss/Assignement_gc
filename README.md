Runtime uploads, SQLite records, and LangGraph checkpoints are stored under `.data/` by default and are Git-ignored. `samples/docs/` contains two synthetic demo PDFs; `samples/outputs/` contains the latest Gemma 3 4B API responses. Per-agent timing and local token counts are captured on successful runs; hardware/energy costs are not measured.
# Nova Trade-Document Pipeline

A local prototype that extracts trade-document fields, validates them against customer rules, routes the result, stores the run in SQLite, and exposes a small review UI.

## Requirements

- Python 3.11 or newer
- Ollama installed and running locally
- Local models `gemma3:4b` and `qwen3:8b`
- Tesseract OCR on `PATH` for image-only documents and scanned PDFs without a searchable text layer

The bundled demo documents are synthetic. The messy PDF has a searchable text layer behind its rasterized page, so it does not test standalone OCR.

## Setup on Windows

From PowerShell in the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example app/.env
```

Ollama must be running locally. Download the two models if needed:

```powershell
ollama pull gemma3:4b
ollama pull qwen3:8b
```

`app/.env` configures `OLLAMA_BASE_URL`, `OLLAMA_VISION_MODEL`, and `OLLAMA_TEXT_MODEL`; the defaults target `http://127.0.0.1:11434`. No API key is required. Do not commit `app/.env`.

## Run

Start the API in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload
```

Start the UI in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui/streamlit_app.py
```

Open the Streamlit URL printed by the command (normally `http://localhost:8501`). The API health endpoint is `http://127.0.0.1:8000/health`.

## Use

Upload a PDF or image in the UI and select **Run review**. The response includes extracted values, confidence, evidence quotes, per-field validation, a decision, and reasoning. Uncertain fields route to human review. The amendment draft lists each mismatched field, found value, and expected value.

The API also exposes:

- `POST /runs?filename=<name>` with the document bytes as the request body
- `GET /shipments/{shipment_id}` for persisted fields and run data
- `POST /queries` with `{"question":"..."}` for guarded natural-language SQL

The query generator uses the local `qwen3:8b` model with JSON-schema output. SQL executes through a read-only SQLite connection, is limited to the application schema, and receives an enforced row limit. The UI displays the executed SQL and returned rows.

## Tests and evaluations

Run the tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Regenerate the six synthetic eval PDFs and labels, then evaluate them with Ollama:

```powershell
.\.venv\Scripts\python.exe -m evals.generate_dataset
.\.venv\Scripts\python.exe -m evals.run_evals
```

The measured snapshot in [evals/results.md](evals/results.md) is a synthetic Ollama evaluation, not a real-customer accuracy claim. The visually messy PDFs contain hidden searchable text and do not evaluate OCR on image-only documents.

## Data locations

Runtime uploads, SQLite records, and LangGraph checkpoints are stored under `.data/` by default and are Git-ignored. `samples/docs/` contains two synthetic demo PDFs. `samples/outputs/` contains successful local Gemma results. Successful runs record per-agent latency and token counts; hardware/energy costs are not estimated.

See [docs/PRD.md](docs/PRD.md), [docs/WRITEUP.md](docs/WRITEUP.md), [docs/sample_queries.md](docs/sample_queries.md), and [docs/failures.md](docs/failures.md) for product framing, architecture, measured examples, and observed issues.

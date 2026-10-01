import os
from pathlib import Path


def load_app_env(path: str | Path | None = None) -> None:
	env_path = Path(path) if path is not None else Path(__file__).with_name(".env")
	try:
		lines = env_path.read_text(encoding="utf-8").splitlines()
	except FileNotFoundError:
		return

	for line in lines:
		entry = line.strip()
		if not entry or entry.startswith("#"):
			continue
		if entry.startswith("export "):
			entry = entry[7:].lstrip()
		key, separator, value = entry.partition("=")
		if not separator:
			continue
		key = key.strip()
		value = value.strip()
		if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
			value = value[1:-1]
		if key:
			os.environ.setdefault(key, value)


load_app_env()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "gemma3:4b")
OLLAMA_TEXT_MODEL = os.environ.get("OLLAMA_TEXT_MODEL", "qwen3:8b")
MAX_VISION_IMAGES = 3
MIN_FIELD_CONFIDENCE = 0.8
MAX_QUERY_ROWS = 100
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
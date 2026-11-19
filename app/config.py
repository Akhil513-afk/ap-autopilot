import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from .env. Real environment variables always win; blank values are ignored."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


if not os.environ.get("AP_SKIP_DOTENV"):
    _load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
STORAGE = Path(os.environ.get("STORAGE_DIR", str(ROOT / "storage")))
UPLOADS = STORAGE / "uploads"
SAMPLES = ROOT / "samples"
STATIC = ROOT / "static"

UPLOADS.mkdir(parents=True, exist_ok=True)

VERSION = "1.1.0"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
WORKERS = max(1, int(os.environ.get("WORKERS", "3")))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))
# The demo reset endpoint wipes all runs - disable it in shared environments with ALLOW_RESET=0.
ALLOW_RESET = os.environ.get("ALLOW_RESET", "1") != "0"
DB_PATH = Path(os.environ.get("DB_PATH", str(STORAGE / "ap.db")))

# Seconds to pause between stages so a human can follow the live run view. 0 = full speed.
STAGE_PACING = float(os.environ.get("STAGE_PACING", "0.6"))

# Gemini model used for document understanding when GEMINI_API_KEY is set (free tier: Google AI Studio).
LLM_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
# Tried in order when the primary model is overloaded (503), rate-limited (429) or retired (404).
LLM_FALLBACK_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3.5-flash,gemini-3.8-flash").split(",") if m.strip()]
# Per-model request timeout, and a total budget across the whole fallback chain, so a congested
# free tier can't stall a run - after the budget the rule-based parser takes over.
LLM_TIMEOUT_S = int(os.environ.get("GEMINI_TIMEOUT_S", "15"))
LLM_TOTAL_BUDGET_S = int(os.environ.get("GEMINI_TOTAL_BUDGET_S", "30"))


def gemini_models() -> list[str]:
    seen, out = set(), []
    for m in [LLM_MODEL, *LLM_FALLBACK_MODELS]:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out
# Set USE_LLM=0 to force the deterministic parser even when a key is present.
USE_LLM = os.environ.get("USE_LLM", "1") != "0"

# Business "today" for date-sanity checks. Overridable so the demo is reproducible.
AS_OF_DATE = os.environ.get("AS_OF_DATE")  # e.g. "2026-11-18"; default = real today


def load_json(name: str):
    return json.loads((DATA / name).read_text())


def vendors():
    return load_json("vendors.json")


def purchase_orders():
    return load_json("purchase_orders.json")


def policy():
    return load_json("policy.json")


def llm_available() -> bool:
    if not USE_LLM:
        return False
    return bool(gemini_key())


def gemini_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

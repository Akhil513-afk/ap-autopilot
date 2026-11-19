"""Test environment - set before any app module is imported."""
import os
import tempfile

os.environ["AP_SKIP_DOTENV"] = "1"  # never pick up a developer's real key from .env
os.environ["STAGE_PACING"] = "0"
os.environ["USE_LLM"] = "0"
os.environ["AS_OF_DATE"] = "2026-11-18"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="ap-test-")
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)

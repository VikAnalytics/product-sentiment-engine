"""
Shared configuration and clients for the Product Sentiment Engine.
Validates environment variables and provides lazy-initialized Supabase and Gemini clients.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Required environment variables ---
REQUIRED_ENV = ("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY")

# --- Tunable constants (single place to change behavior) ---
GEMINI_MODEL_NAME = "gemini-2.5-flash"
# Embedding model listed for your key as: models/gemini-embedding-001
# For the newer client we pass it without the 'models/' prefix.
EMBEDDING_MODEL = "gemini-embedding-001"
MATCH_THRESHOLD = 0.82
HTTP_TIMEOUT_SEC = 15
REQUEST_DELAY_BETWEEN_TARGETS_SEC = 1.0
ARTICLES_PER_FEED = 10
HN_SEARCH_LIMIT = 3
REDDIT_SEARCH_LIMIT = 3
STACKOVERFLOW_SEARCH_LIMIT = 3
GOOGLE_NEWS_LIMIT = 3
LOOKBACK_DAYS = 1
MAX_PAYLOAD_CHARS_PER_FIELD = 2000  # truncate long pros/cons in report payload to avoid token limits

_supabase_client = None
_genai_model = None
_genai_configured = False


def _validate_env(*required: str) -> None:
    """Ensure required env vars are set. Defaults to REQUIRED_ENV; pass a subset for e.g. dashboard-only."""
    keys = required if required else REQUIRED_ENV
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env or your environment."
        )


def get_supabase():
    """Return Supabase client. Validates Supabase env on first use (dashboard can run without GEMINI_API_KEY)."""
    global _supabase_client
    if _supabase_client is None:
        _validate_env("SUPABASE_URL", "SUPABASE_KEY")
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        _supabase_client = create_client(url, key)
    return _supabase_client


def _configure_genai() -> None:
    global _genai_configured
    if _genai_configured:
        return
    _validate_env("GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY")
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    _genai_configured = True


def get_model():
    """Return Gemini generative model (free-form text). Validates env on first use."""
    global _genai_model
    if _genai_model is None:
        _configure_genai()
        import google.generativeai as genai
        _genai_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    return _genai_model


def get_json_model():
    """Return a Gemini model configured to return structured JSON (application/json MIME type).
    Use this for structured extraction (tracker); use get_model() for free-form reports."""
    _configure_genai()
    import google.generativeai as genai
    return genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        ),
    )

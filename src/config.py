"""
Shared configuration and clients for the Product Sentiment Engine.
Validates environment variables and provides lazy-initialized Supabase and OpenAI clients.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Required environment variables ---
REQUIRED_ENV = ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY")

# --- Model ---
OPENAI_MODEL_NAME = "gpt-4o-mini"

# --- Tunable constants (single place to change behavior) ---
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
_openai_client = None


def _validate_env(*required: str) -> None:
    """Ensure required env vars are set."""
    keys = required if required else REQUIRED_ENV
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env or your environment."
        )


def get_supabase():
    """Return Supabase client (dashboard can run without OPENAI_API_KEY)."""
    global _supabase_client
    if _supabase_client is None:
        _validate_env("SUPABASE_URL", "SUPABASE_KEY")
        from supabase import create_client
        _supabase_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    return _supabase_client


# ---------------------------------------------------------------------------
# OpenAI adapter — keeps the same .generate_content() / .text interface so
# all callers (scout, tracker, report, weekly_brief, domain_resolver) are
# unchanged.
# ---------------------------------------------------------------------------

class _TextResponse:
    """Mimics Gemini's GenerateContentResponse.text so callers stay unchanged."""
    def __init__(self, text: str):
        self.text = text


class _OpenAIModel:
    """Thin wrapper around openai.OpenAI that exposes generate_content(prompt)."""

    def __init__(self, client, model_name: str, json_mode: bool = False):
        self._client = client
        self._model = model_name
        self._json_mode = json_mode

    def generate_content(self, prompt: str) -> _TextResponse:
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": self._model, "messages": messages}
        if self._json_mode:
            # OpenAI requires the word "json" in the prompt for JSON mode
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        return _TextResponse(resp.choices[0].message.content or "")


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        _validate_env("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY")
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def get_model() -> _OpenAIModel:
    """Return OpenAI model wrapper for free-form text generation."""
    return _OpenAIModel(_get_openai_client(), OPENAI_MODEL_NAME, json_mode=False)


def get_json_model() -> _OpenAIModel:
    """Return OpenAI model wrapper configured for structured JSON output.
    Use this for structured extraction (tracker); use get_model() for free-form reports."""
    return _OpenAIModel(_get_openai_client(), OPENAI_MODEL_NAME, json_mode=True)

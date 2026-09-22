"""
Shared pytest configuration.

Tests are designed to run without Supabase/OpenAI credentials — they only
exercise pure functions. To guarantee that, we set placeholder env vars so
any accidental import that validates env doesn't fail collection.
"""
import os


os.environ.setdefault("SUPABASE_URL", "https://test.invalid")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

# Keep telemetry from attempting a Supabase round trip during tests. The helper
# already swallows connection errors, but waiting on DNS for every step is slow.
os.environ.setdefault("PIPELINE_TELEMETRY", "0")

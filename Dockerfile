# Product Sentiment Engine — reproducible runtime image.
# Run pipeline steps or the Streamlit dashboard from the same container.
#
# Build:
#   docker build -t psengine .
#
# Run a pipeline step (mount .env for secrets):
#   docker run --rm --env-file .env psengine python src/scout.py
#   docker run --rm --env-file .env psengine python src/sim_trader.py --action diagnose
#
# Run the Streamlit dashboard:
#   docker run --rm -p 8501:8501 --env-file .env psengine \
#       streamlit run src/app.py --server.address 0.0.0.0 --server.port 8501

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# System deps: build tools for numpy/scipy wheels + curl for healthcheck
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching)
COPY requirements.txt ./
RUN pip install -r requirements.txt \
 && python -m spacy download en_core_web_sm

# Copy application code
COPY src ./src
COPY scripts ./scripts
COPY supabase ./supabase

# Non-root user for safer runtime
RUN useradd --create-home --uid 10001 psengine \
 && chown -R psengine:psengine /app
USER psengine

EXPOSE 8501

# Default: dashboard. Override with `docker run ... python src/scout.py` etc.
CMD ["streamlit", "run", "src/app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]

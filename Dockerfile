# Genuine — deterministic-core API image (Gate 8).
#
# Only requirements.txt is installed: the RAG layer is embedding-free TF-IDF, so
# no faiss/torch/tree-sitter wheels are needed (requirements-ml.txt is not
# imported by the running code). `git` IS required — ingestion drives gitpython,
# which shells out to the real git binary.

FROM python:3.12-slim

# git: gitpython shells out to it for clone/log/diff. Without it, ingestion fails.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GENUINE_DB_PATH=data/genuine.sqlite \
    GENUINE_CLONE_CACHE=data/clones

WORKDIR /app

# Dependencies first, so the (slow) install layer caches across code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Then the package itself. pyproject declares no runtime deps (they live in
# requirements.txt), so --no-deps keeps this from re-resolving anything.
COPY pyproject.toml README.md ./
COPY genuine ./genuine
RUN pip install --no-deps .

# SQLite (jobs + registry) and cloned repos land here. Mount a volume/disk at
# /app/data to persist them across restarts (see docker-compose.yml / render.yaml).
RUN mkdir -p data

EXPOSE 8000

# Render/Fly inject $PORT; default to 8000 for a plain `docker run`.
CMD ["sh", "-c", "uvicorn genuine.api:app --host 0.0.0.0 --port ${PORT:-8000}"]

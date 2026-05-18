# ── Stage 1: install Python packages ─────────────────────────────────────────
# h5py and python-igraph ship bundled HDF5/libxml2 in their PyPI wheels,
# so no system -dev headers are needed for pip installs.
# gcc is kept only as a fallback if any package forces a source build.
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements_backend.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements_backend.txt


# ── Stage 2: lean runtime image ───────────────────────────────────────────────
# No system HDF5/libxml2 packages needed — bundled inside the wheels above.
FROM python:3.11-slim

# Copy pre-built packages from builder stage
COPY --from=builder /install /usr/local

WORKDIR /app
COPY agent_pipeline.py .

# ── Runtime configuration via environment variables ───────────────────────────
# OLLAMA_URL   — override if Ollama is not on localhost (e.g. http://ollama:11434/api/chat)
# OLLAMA_MODEL — model tag to use
# WORKSPACE_DIR — path inside the container where JSON bridge files are written
ENV OLLAMA_URL="http://localhost:11434/api/chat" \
    OLLAMA_MODEL="qwen2.5-coder:14b" \
    WORKSPACE_DIR="/app/workspace"

# workspace dir must exist; host mounts over it at runtime
RUN mkdir -p /app/workspace

ENTRYPOINT ["python", "agent_pipeline.py"]
# Default args — override with: docker run scchat-pipeline /data/input.h5ad --output /app/workspace/out.h5ad
CMD ["--help"]

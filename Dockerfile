# One image for the API and the io/cpu workers ("app", the default), plus a
# "gpu" variant for the GPU worker that adds NVIDIA's CUDA libraries.
# docker-compose.yml picks the target and the command.
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# UV_NO_CACHE: uv's download cache would otherwise be saved inside the image
# (it doubled the dependency layer to 3.6 GB).
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so code edits don't reinstall them. pdqhash is published
# as source only, so a C++ compiler is installed for this step and removed in
# the same step (so it doesn't stay in the image).
COPY pyproject.toml uv.lock ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && uv sync --frozen --no-dev --no-install-project \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config

# Don't run as root inside the container. The model cache folder exists here,
# owned by farq, so a Docker volume mounted on it gets the same owner.
RUN useradd --create-home --uid 1000 farq \
    && mkdir -p /home/farq/.paddlex /home/farq/.cache/huggingface \
    && chown -R farq:farq /home/farq/.paddlex /home/farq/.cache
USER farq

CMD ["uvicorn", "farq.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# GPU worker: cuBLAS and cuDNN for CTranslate2 (faster-whisper) on CUDA 12.
# Installs only the NVIDIA packages, at the versions in uv.lock, on top of the
# app's environment (a full re-sync rewrote other files and added 4.6 GB).
# Their C headers are only for compiling, so they are removed.
FROM base AS gpu
USER root
RUN uv export --frozen --no-dev --extra gpu --no-hashes --no-emit-project \
        | grep -E '^nvidia-' > /tmp/gpu-requirements.txt \
    && UV_COMPILE_BYTECODE=0 uv pip install --python /opt/venv --no-deps \
        -r /tmp/gpu-requirements.txt \
    && rm -rf /opt/venv/lib/python3.12/site-packages/nvidia/*/include /tmp/gpu-requirements.txt
ENV LD_LIBRARY_PATH=/opt/venv/lib/python3.12/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cudnn/lib
USER farq


# Default target (last stage): the plain app image.
FROM base AS app

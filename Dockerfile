# One image for the API and the io/cpu workers ("app", the default), plus a
# "gpu" variant for the GPU worker that adds NVIDIA's CUDA libraries.
# docker-compose.yml picks the target and the command.
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so code edits don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config

# Don't run as root inside the container. The model cache folder exists here,
# owned by farq, so a Docker volume mounted on it gets the same owner.
RUN useradd --create-home --uid 1000 farq \
    && mkdir -p /home/farq/.paddlex \
    && chown farq:farq /home/farq/.paddlex
USER farq

CMD ["uvicorn", "farq.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# GPU worker: cuBLAS and cuDNN for CTranslate2 (faster-whisper) on CUDA 12.
FROM base AS gpu
USER root
RUN uv sync --frozen --no-dev --extra gpu
ENV LD_LIBRARY_PATH=/opt/venv/lib/python3.12/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cudnn/lib
USER farq


# Default target (last stage): the plain app image.
FROM base AS app

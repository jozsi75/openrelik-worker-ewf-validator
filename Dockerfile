# Use the official Ubuntu base image
FROM ubuntu:24.04

# Prevent interactive package prompts
RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Install system dependencies required by the worker
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ewf-tools \
    && rm -rf /var/lib/apt/lists/*

# Configure debugging
ARG OPENRELIK_PYDEBUG
ENV OPENRELIK_PYDEBUG=${OPENRELIK_PYDEBUG:-0}

ARG OPENRELIK_PYDEBUG_PORT
ENV OPENRELIK_PYDEBUG_PORT=${OPENRELIK_PYDEBUG_PORT:-5678}

# Set working directory
WORKDIR /openrelik

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for better Docker layer caching
COPY uv.lock pyproject.toml ./

# Install Python dependencies
RUN uv sync --locked --no-install-project --no-dev

# Copy the worker source code
COPY . ./

# Install the worker project itself
RUN uv sync --locked --no-dev

# Use the virtual environment created by uv
ENV PATH="/openrelik/.venv/bin:$PATH"

CMD ["celery", "--app=src.tasks", "worker", "--task-events", "--concurrency=1", "--loglevel=DEBUG"]
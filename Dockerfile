FROM python:3.12-slim-bookworm

# Install make and other build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends make && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory in the container
WORKDIR /biar

# Copy project file into the container
COPY . .

# Tell the container about our project layout
ENV PROJECT_ROOT=/biar

# Install the project dependencies using UV
RUN uv sync --all-extras --dev

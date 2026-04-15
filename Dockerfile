# ── Base image ────────────────────────────────────────────────────
FROM python:3.12-slim

# Prevents Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# ── System dependencies ───────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ── Work directory ────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────
# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── Copy project ──────────────────────────────────────────────────
COPY . .

# ── Create media and static directories ──────────────────────────
RUN mkdir -p /app/media /app/staticfiles

# ── Entrypoint ────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
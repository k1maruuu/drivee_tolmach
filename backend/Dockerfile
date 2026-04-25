FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DEFAULT_TIMEOUT=300

COPY requirements.txt /app/requirements.txt
# PyPI can be slow from Docker; default pip read timeout often fails mid-download (files.pythonhosted.org Read timed out).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --retries 10 --default-timeout=300 -r /app/requirements.txt

COPY src /app/src

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

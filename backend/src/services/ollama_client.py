import json
import re
from typing import Any

import httpx
from fastapi import HTTPException, status

from src.core.config import settings
from src.services.prompt_builder import build_sql_prompt


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("Ollama did not return JSON")


def _extract_sql(text: str) -> str | None:
    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()

    match = re.search(r"\b(WITH|SELECT)\b.*", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return None


async def generate_sql(question: str, max_rows: int, validation_feedback: str | None = None) -> dict[str, Any]:
    prompt = build_sql_prompt(question=question, max_rows=max_rows, validation_feedback=validation_feedback)
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_ctx": 8192,
        },
    }

    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    timeout = httpx.Timeout(
        connect=30.0,
        read=float(settings.ollama_timeout_seconds),
        write=30.0,
        pool=30.0,
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ollama is unavailable at {settings.ollama_base_url}: {exc}",
        ) from exc

    raw_text = str(data.get("response", "")).strip()
    try:
        parsed = _extract_json(raw_text)
    except Exception:
        sql = _extract_sql(raw_text)
        if not sql:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Ollama response does not contain SQL",
            )
        parsed = {"sql": sql, "confidence": None, "notes": "Parsed SQL from non-JSON Ollama response"}

    if not parsed.get("sql"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Ollama JSON has no sql field")

    return parsed

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook


def query_result_to_xlsx_bytes(result: dict[str, Any] | None) -> bytes:
    """Build a minimal .xlsx from a QueryResult-shaped dict (columns, rows)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    cols = list(result.get("columns") or []) if result else []
    ws.append(cols)
    for row in result.get("rows") or []:
        if isinstance(row, dict):
            ws.append([row.get(c) for c in cols])
        else:
            ws.append(list(row) if isinstance(row, (list, tuple)) else [row])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()

import json
import re
from dataclasses import dataclass, field
from typing import Any

import sqlparse
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlparse.tokens import Comment

from src.core.config import settings

FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "COPY",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "ANALYZE",
    "CALL",
    "DO",
    "EXECUTE",
    "MERGE",
    "SET",
    "RESET",
    "LOCK",
    "LISTEN",
    "NOTIFY",
}

DANGEROUS_FUNCTIONS = {
    "pg_sleep",
    "generate_series",
    "dblink",
    "lo_import",
    "lo_export",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
}

ALLOWED_TABLES = {"incity", "pass_detail", "driver_detail"}


@dataclass
class ValidationResult:
    is_valid: bool
    sql: str
    normalized_sql: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _extract_cte_names(sql: str) -> set[str]:
    names: set[str] = set()
    if not re.match(r"^\s*WITH\b", sql, flags=re.IGNORECASE):
        return names
    for match in re.finditer(r"(?:WITH|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", sql, flags=re.IGNORECASE):
        names.add(match.group(1).lower())
    return names


def _is_comment_token(token) -> bool:
    # sqlparse Token does not have is_comment in all versions.
    value = str(getattr(token, "value", "")).lstrip()
    if value.startswith("--") or value.startswith("/*"):
        return True

    ttype = getattr(token, "ttype", None)
    while ttype is not None:
        if ttype is Comment:
            return True
        ttype = getattr(ttype, "parent", None)

    return False


def _first_keyword(statement) -> str | None:
    for token in statement.tokens:
        if getattr(token, "is_whitespace", False) or _is_comment_token(token):
            continue
        return str(token.value).strip().split()[0].upper()
    return None


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--.*?$", " ", sql, flags=re.MULTILINE)
    return sql


def _strip_sql_literals_and_comments(sql: str) -> str:
    """Remove comments and literal values before keyword guardrails.

    Values like status_order = 'delete' are safe for this dataset. We must not
    treat the word DELETE inside a quoted string as a DML command.
    """
    cleaned = _strip_sql_comments(sql)

    # PostgreSQL dollar-quoted strings: $$...$$ and $tag$...$tag$.
    cleaned = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)\$.*?\$\1\$", "''", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\$\$.*?\$\$", "''", cleaned, flags=re.DOTALL)

    # Standard strings and PostgreSQL escape strings: '...', E'...'.
    cleaned = re.sub(r"(?:\bE)?'(?:''|[^'])*'", "''", cleaned, flags=re.IGNORECASE)

    # Quoted identifiers should not trigger keyword guardrails either.
    cleaned = re.sub(r'"(?:""|[^"])*"', '""', cleaned)
    return cleaned


def _mask_extract_from_clauses(sql: str) -> str:
    """Mask EXTRACT(... FROM ...) expressions before table extraction."""
    result: list[str] = []
    i = 0
    lower = sql.lower()
    while i < len(sql):
        if lower.startswith("extract", i):
            j = i + len("extract")
            while j < len(sql) and sql[j].isspace():
                j += 1
            if j < len(sql) and sql[j] == "(":
                depth = 0
                k = j
                in_single = False
                in_double = False
                while k < len(sql):
                    ch = sql[k]
                    if ch == "'" and not in_double:
                        in_single = not in_single
                    elif ch == '"' and not in_single:
                        in_double = not in_double
                    elif not in_single and not in_double:
                        if ch == "(":
                            depth += 1
                        elif ch == ")":
                            depth -= 1
                            if depth == 0:
                                k += 1
                                break
                    k += 1
                result.append(" EXTRACT_EXPR ")
                i = k
                continue
        result.append(sql[i])
        i += 1
    return "".join(result)


def _extract_table_references(sql: str) -> list[str]:
    """Extract real table names from FROM/JOIN clauses.

    Derived tables like FROM (SELECT ...) are ignored here, while the inner real
    FROM train remains visible to the regex.
    """
    cleaned = _mask_extract_from_clauses(_strip_sql_comments(sql))
    tables: list[str] = []
    for match in re.finditer(
        r"\b(?:FROM|JOIN)\s+(?!\()([a-zA-Z_][a-zA-Z0-9_\.]*)(?:\s+AS)?(?:\s+[a-zA-Z_][a-zA-Z0-9_]*)?",
        cleaned,
        flags=re.IGNORECASE,
    ):
        table = match.group(1).split(".")[-1].strip('"').lower()
        if table:
            tables.append(table)
    return tables


def _extract_tables(sql: str) -> set[str]:
    return set(_extract_table_references(sql))


def _has_limit(sql: str) -> bool:
    return bool(re.search(r"\bLIMIT\b", sql, flags=re.IGNORECASE))


def _limit_warning(sql: str, limit: int) -> str | None:
    cleaned = sql.strip().rstrip(";")
    match = re.search(r"\bLIMIT\s+(\d+)\s*$", cleaned, flags=re.IGNORECASE)
    if match:
        current_limit = int(match.group(1))
        if current_limit > limit:
            return f"LIMIT was reduced from {current_limit} to {limit}."
        return None
    if _has_limit(cleaned):
        return f"Unsupported LIMIT form was wrapped and limited to {limit} rows."
    return f"LIMIT {limit} was added automatically."


def _enforce_limit(sql: str, limit: int) -> str:
    cleaned = sql.strip().rstrip(";")
    match = re.search(r"\bLIMIT\s+(\d+)\s*$", cleaned, flags=re.IGNORECASE)
    if match:
        current_limit = int(match.group(1))
        if current_limit <= limit:
            return cleaned
        return cleaned[: match.start()] + f"LIMIT {limit}"

    if _has_limit(cleaned):
        # Handles uncommon LIMIT forms like LIMIT ALL or parameterized LIMIT.
        return f"SELECT * FROM ({cleaned}) AS nl2sql_limited LIMIT {limit}"

    return f"{cleaned} LIMIT {limit}"


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    message = re.sub(r"\s+", " ", message)
    return message[:700]


def _safe_limit(limit: int | None = None) -> int:
    return min(limit or settings.sql_default_limit, settings.sql_max_limit)


def normalize_sql(sql: str, limit: int | None = None) -> str:
    cleaned = sql.strip().rstrip(";")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _enforce_limit(cleaned, _safe_limit(limit))


def _extract_offset(sql: str) -> int | None:
    match = re.search(r"\bOFFSET\s+(\d+)\b", sql, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _plan_from_explain_row(raw_value: Any) -> dict[str, Any] | None:
    """Parse EXPLAIN (FORMAT JSON) result from psycopg2/SQLAlchemy."""
    value = raw_value
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return first.get("Plan") or first
    if isinstance(value, dict):
        return value.get("Plan") or value
    return None


def _max_plan_metric(plan: dict[str, Any], key: str) -> float:
    current = float(plan.get(key) or 0)
    children = plan.get("Plans") or []
    for child in children:
        if isinstance(child, dict):
            current = max(current, _max_plan_metric(child, key))
    return current


def _apply_readonly_settings(db: Session) -> None:
    timeout_ms = int(settings.sql_statement_timeout_ms)
    db.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
    db.execute(text(f"SET LOCAL idle_in_transaction_session_timeout = {timeout_ms}"))
    if settings.sql_readonly_transaction:
        db.execute(text("SET LOCAL default_transaction_read_only = on"))


def _is_aggregate_or_grouped_query(sql: str, plan: dict[str, Any]) -> bool:
    """Return True for queries that scan many rows but return aggregated output.

    COUNT(DISTINCT order_id) over a large dataset can require a full scan, but it
    returns 1 row and is exactly the kind of safe KPI query expected in this MVP.
    The previous guard used the maximum Plan Rows from all child nodes and blocked
    such queries by mistake.
    """
    normalized = _strip_sql_literals_and_comments(sql).upper()
    if re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", normalized):
        return True
    if re.search(r"\bGROUP\s+BY\b", normalized):
        return True

    node_type = str(plan.get("Node Type") or "").lower()
    if "aggregate" in node_type:
        return True
    return False


def _validate_explain_plan(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[str]:
    """Run PostgreSQL planner checks without fetching data.

    Important distinction:
    - root_plan_rows = estimated rows returned to the user; this must stay small.
    - max_scan_rows = rows PostgreSQL may scan internally; large values are OK for
      safe aggregate queries like COUNT/SUM/AVG because they return compact results.
    """
    warnings: list[str] = []
    raw_plan = db.execute(text("EXPLAIN (FORMAT JSON) " + sql), params or {}).scalar()
    plan = _plan_from_explain_row(raw_plan)
    if not plan:
        warnings.append("PostgreSQL EXPLAIN passed, but plan metrics could not be parsed.")
        return warnings

    total_cost = _max_plan_metric(plan, "Total Cost")
    root_plan_rows = float(plan.get("Plan Rows") or 0)
    max_scan_rows = _max_plan_metric(plan, "Plan Rows")
    is_aggregate = _is_aggregate_or_grouped_query(sql, plan)

    if total_cost > settings.sql_max_explain_total_cost:
        raise ValueError(
            f"Query is too expensive by EXPLAIN: total_cost={total_cost:.2f}, "
            f"limit={settings.sql_max_explain_total_cost}."
        )

    # Block queries that can return too many rows to the API/client. Do not block
    # safe aggregate queries just because the database must scan a large table.
    if root_plan_rows > settings.sql_max_explain_plan_rows:
        raise ValueError(
            f"Query may produce too many result rows by EXPLAIN: root_plan_rows={int(root_plan_rows)}, "
            f"limit={settings.sql_max_explain_plan_rows}."
        )

    if max_scan_rows > settings.sql_max_explain_plan_rows and not is_aggregate:
        raise ValueError(
            f"Query may scan too many rows by EXPLAIN: scan_rows={int(max_scan_rows)}, "
            f"limit={settings.sql_max_explain_plan_rows}. Add filters, grouping, or a smaller LIMIT."
        )

    if max_scan_rows > settings.sql_max_explain_plan_rows and is_aggregate:
        warnings.append(
            f"EXPLAIN warning: query scans about {int(max_scan_rows)} rows, "
            "but it returns an aggregated result, so it is allowed."
        )

    warnings.append(
        f"EXPLAIN estimate: total_cost={total_cost:.2f}, "
        f"root_plan_rows={int(root_plan_rows)}, max_scan_rows={int(max_scan_rows)}."
    )
    return warnings


def validate_sql(sql: str, limit: int | None = None) -> ValidationResult:
    """Fast static validation: syntax shape, dangerous keywords, allowed table."""
    original_sql = sql.strip()
    errors: list[str] = []
    warnings: list[str] = []
    safe_limit = _safe_limit(limit)

    if not original_sql:
        return ValidationResult(False, sql, errors=["SQL is empty"])

    parsed = sqlparse.parse(original_sql)
    if len(parsed) != 1:
        return ValidationResult(False, original_sql, errors=["Only one SQL statement is allowed"])

    statement = parsed[0]
    statement_type = statement.get_type().upper()
    first_keyword = _first_keyword(statement)

    if statement_type not in {"SELECT", "UNKNOWN"}:
        errors.append("Only SELECT queries are allowed")

    if first_keyword not in {"SELECT", "WITH"}:
        errors.append("SQL must start with SELECT or WITH")

    # Keyword scan must ignore string literals, otherwise a safe filter like
    # WHERE status_order = 'delete' is falsely blocked as DELETE.
    scan_sql = _strip_sql_literals_and_comments(original_sql).upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", scan_sql):
            errors.append(f"Forbidden keyword: {keyword}")

    for function_name in DANGEROUS_FUNCTIONS:
        if re.search(rf"\b{function_name}\s*\(", scan_sql, flags=re.IGNORECASE):
            errors.append(f"Forbidden function: {function_name}")

    if re.search(r";\s*\S", original_sql):
        errors.append("Multiple statements are forbidden")

    if re.search(r"\bSELECT\s+\*", scan_sql):
        message = "SELECT * is forbidden; use explicit columns to control payload size."
        if settings.sql_block_select_star:
            errors.append(message)
        else:
            warnings.append(message)

    if settings.sql_block_cross_join and re.search(r"\bCROSS\s+JOIN\b", scan_sql):
        errors.append("CROSS JOIN is forbidden because it can produce extremely large result sets.")

    if re.search(r"\bORDER\s+BY\s+RANDOM\s*\(", scan_sql):
        errors.append("ORDER BY random() is forbidden because it is expensive on large tables.")

    if re.search(r"\bFOR\s+(UPDATE|SHARE|NO\s+KEY\s+UPDATE|KEY\s+SHARE)\b", scan_sql):
        errors.append("Row-locking clauses are forbidden in read-only analytics queries.")

    offset_value = _extract_offset(scan_sql)
    if offset_value is not None and offset_value > settings.sql_max_offset:
        errors.append(f"OFFSET {offset_value} is too large. Maximum allowed OFFSET is {settings.sql_max_offset}.")
    elif re.search(r"\bOFFSET\s+(?!\d+\b)", scan_sql):
        errors.append("Parameterized or non-numeric OFFSET is forbidden.")

    # Detect implicit comma joins, e.g. FROM incity a, incity b.
    if re.search(r"\bFROM\s+(?:incity|pass_detail|driver_detail)(?:\s+[a-zA-Z_][a-zA-Z0-9_]*)?\s*,", scan_sql, flags=re.IGNORECASE):
        errors.append("Comma joins are forbidden. Use explicit JOIN with clear ON conditions.")

    table_refs = _extract_table_references(original_sql)
    tables = set(table_refs)
    cte_names = _extract_cte_names(original_sql)
    unknown_tables = tables - ALLOWED_TABLES - cte_names
    if unknown_tables:
        allowed = ", ".join(sorted(ALLOWED_TABLES))
        errors.append(f"Only these dataset tables are allowed: {allowed}. Unknown tables: {', '.join(sorted(unknown_tables))}")

    if not (tables & ALLOWED_TABLES):
        errors.append("Query must read from at least one dataset table: incity, pass_detail, driver_detail")

    max_refs = getattr(settings, "sql_max_table_references", settings.sql_max_train_references)
    real_table_refs = [table for table in table_refs if table in ALLOWED_TABLES]
    if len(real_table_refs) > max_refs:
        errors.append(
            f"Query references dataset tables {len(real_table_refs)} times; maximum allowed is {max_refs}. "
            "Use simple joins/aggregations for MVP mode."
        )
    for table in ALLOWED_TABLES:
        if real_table_refs.count(table) > 1:
            errors.append(f"Self-join or repeated reference to {table} is forbidden in MVP mode.")

    normalized = None
    if not errors:
        warning = _limit_warning(original_sql, safe_limit)
        if warning:
            warnings.append(warning)
        normalized = normalize_sql(original_sql, limit=safe_limit)

    return ValidationResult(
        is_valid=not errors,
        sql=original_sql,
        normalized_sql=normalized,
        errors=errors,
        warnings=warnings,
    )


def validate_sql_against_database(
    db: Session,
    sql: str,
    limit: int | None = None,
    params: dict[str, Any] | None = None,
) -> ValidationResult:
    """
    Full validation for MVP guardrails.

    1. Static guardrails block dangerous statements and heavy patterns.
    2. PostgreSQL EXPLAIN checks executability: columns, functions, casts,
       aliases, GROUP BY correctness, bind parameters, and rough plan cost.
    3. No data is changed and no rows are fetched at validation stage.
    """
    validation = validate_sql(sql, limit=limit)
    if not validation.is_valid or not validation.normalized_sql:
        return validation

    try:
        _apply_readonly_settings(db)
        validation.warnings.extend(_validate_explain_plan(db, validation.normalized_sql, params or {}))
        db.rollback()
    except Exception as exc:
        db.rollback()
        validation.is_valid = False
        validation.errors.append(f"SQL cannot be executed safely by PostgreSQL: {_safe_error(exc)}")
        validation.normalized_sql = None

    return validation

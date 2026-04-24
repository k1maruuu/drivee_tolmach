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
}

ALLOWED_TABLES = {"train"}


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

    Important: values like status_order = 'delete' are safe and valid for this
    dataset. We must not treat the word DELETE inside a quoted string as a DML
    command. Real DML statements are still blocked by the first keyword check
    and by scanning SQL after literals are removed.
    """
    cleaned = _strip_sql_comments(sql)

    # PostgreSQL dollar-quoted strings: $$...$$ and $tag$...$tag$.
    cleaned = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)\$.*?\$\1\$", "''", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\$\$.*?\$\$", "''", cleaned, flags=re.DOTALL)

    # Standard strings and PostgreSQL escape strings: '...', E'...'.
    # Do NOT require a word boundary before the opening quote: quotes are not
    # word characters, so r\b before ' does not match after spaces/operators.
    cleaned = re.sub(r"(?:\bE)?'(?:''|[^'])*'", "''", cleaned, flags=re.IGNORECASE)

    # Quoted identifiers should not trigger keyword guardrails either.
    cleaned = re.sub(r'"(?:""|[^"])*"', '""', cleaned)
    return cleaned




def _mask_extract_from_clauses(sql: str) -> str:
    """Mask EXTRACT(... FROM ...) expressions before table extraction.

    A simple FROM/JOIN regex can otherwise treat the FROM inside
    EXTRACT(HOUR FROM order_timestamp) as a real table reference and falsely
    block safe analytical templates.
    """
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

def _extract_tables(sql: str) -> set[str]:
    """
    Extract real table names from FROM/JOIN clauses.

    This intentionally ignores derived tables like:
    FROM (SELECT ... FROM train) t

    The inner FROM train is still extracted by the regex, while the outer
    FROM (...) alias is not treated as a table.
    """
    cleaned = _mask_extract_from_clauses(_strip_sql_comments(sql))
    tables: set[str] = set()
    for match in re.finditer(
        r"\b(?:FROM|JOIN)\s+(?!\()([a-zA-Z_][a-zA-Z0-9_\.]*)(?:\s+AS)?(?:\s+[a-zA-Z_][a-zA-Z0-9_]*)?",
        cleaned,
        flags=re.IGNORECASE,
    ):
        table = match.group(1).split(".")[-1].strip('"').lower()
        if table:
            tables.add(table)
    return tables


def _has_limit(sql: str) -> bool:
    return bool(re.search(r"\bLIMIT\b", sql, flags=re.IGNORECASE))


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


def normalize_sql(sql: str, limit: int | None = None) -> str:
    safe_limit = min(limit or settings.sql_default_limit, settings.sql_max_limit)
    cleaned = sql.strip().rstrip(";")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _enforce_limit(cleaned, safe_limit)


def validate_sql(sql: str, limit: int | None = None) -> ValidationResult:
    """Fast static validation: syntax shape, dangerous keywords, allowed table."""
    original_sql = sql.strip()
    errors: list[str] = []
    warnings: list[str] = []

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

    if re.search(r";\s*\S", original_sql):
        errors.append("Multiple statements are forbidden")

    if re.search(r"\bSELECT\s+\*", scan_sql):
        warnings.append("SELECT * is not recommended; explicit columns are safer")

    tables = _extract_tables(original_sql)
    cte_names = _extract_cte_names(original_sql)
    unknown_tables = tables - ALLOWED_TABLES - cte_names
    if unknown_tables:
        errors.append(f"Only table train is allowed. Unknown tables: {', '.join(sorted(unknown_tables))}")

    if "train" not in tables:
        errors.append("Query must read from table train")

    normalized = None
    if not errors:
        normalized = normalize_sql(original_sql, limit=limit)

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

    1. Static guardrails block dangerous statements.
    2. PostgreSQL EXPLAIN checks real executability: columns, functions, casts,
       aliases, GROUP BY correctness, bind parameters, etc.
    3. No data is changed and no rows are fetched at validation stage.
    """
    validation = validate_sql(sql, limit=limit)
    if not validation.is_valid or not validation.normalized_sql:
        return validation

    try:
        db.execute(text(f"SET LOCAL statement_timeout = {int(settings.sql_statement_timeout_ms)}"))
        db.execute(text("EXPLAIN " + validation.normalized_sql), params or {})
        db.rollback()
    except Exception as exc:
        db.rollback()
        validation.is_valid = False
        validation.errors.append(f"SQL cannot be executed by PostgreSQL: {_safe_error(exc)}")
        validation.normalized_sql = None

    return validation

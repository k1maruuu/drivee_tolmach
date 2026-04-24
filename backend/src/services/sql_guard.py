import re
from dataclasses import dataclass, field

import sqlparse
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlparse.tokens import Comment, Keyword, Name

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


def _extract_tables(statement) -> set[str]:
    tables: set[str] = set()
    expect_table = False
    for token in statement.flatten():
        value = token.value.strip()
        upper = value.upper()
        if not value or _is_comment_token(token):
            continue
        if token.ttype is Keyword and upper in {"FROM", "JOIN", "UPDATE", "INTO"}:
            expect_table = True
            continue
        if expect_table:
            if token.ttype in (Name, Keyword) or re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*$", value):
                tables.add(value.split(".")[-1].strip('"').lower())
                expect_table = False
            elif value not in {",", "("}:
                expect_table = False
    return tables


def _has_limit(sql: str) -> bool:
    return bool(re.search(r"\bLIMIT\b", sql, flags=re.IGNORECASE))


def _append_limit(sql: str, limit: int) -> str:
    sql = sql.strip().rstrip(";")
    if _has_limit(sql):
        return sql
    return f"{sql} LIMIT {limit}"


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    message = re.sub(r"\s+", " ", message)
    return message[:700]


def normalize_sql(sql: str, limit: int | None = None) -> str:
    safe_limit = min(limit or settings.sql_default_limit, settings.sql_max_limit)
    cleaned = sql.strip().rstrip(";")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _append_limit(cleaned, safe_limit)


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

    upper_sql = original_sql.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            errors.append(f"Forbidden keyword: {keyword}")

    if re.search(r";\s*\S", original_sql):
        errors.append("Multiple statements are forbidden")

    if re.search(r"\bSELECT\s+\*", upper_sql):
        warnings.append("SELECT * is not recommended; explicit columns are safer")

    tables = _extract_tables(statement)
    cte_names = _extract_cte_names(original_sql)
    unknown_tables = tables - ALLOWED_TABLES - cte_names
    if unknown_tables:
        errors.append(f"Only table train is allowed. Unknown tables: {', '.join(sorted(unknown_tables))}")

    if not tables:
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


def validate_sql_against_database(db: Session, sql: str, limit: int | None = None) -> ValidationResult:
    """
    Full validation for MVP guardrails.

    1. Static guardrails block dangerous statements.
    2. PostgreSQL EXPLAIN checks real executability: columns, functions, casts,
       aliases, GROUP BY correctness, etc.
    3. No data is changed and no rows are fetched at validation stage.
    """
    validation = validate_sql(sql, limit=limit)
    if not validation.is_valid or not validation.normalized_sql:
        return validation

    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text(f"SET LOCAL statement_timeout = {int(settings.sql_statement_timeout_ms)}"))
        db.execute(text("EXPLAIN " + validation.normalized_sql))
        db.rollback()
    except Exception as exc:
        db.rollback()
        validation.is_valid = False
        validation.errors.append(f"SQL cannot be executed by PostgreSQL: {_safe_error(exc)}")
        validation.normalized_sql = None

    return validation

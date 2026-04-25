from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.security import hash_password
from src.db.session import Base, SessionLocal, engine


def _migrate_saved_reports_extras() -> None:
    """Add columns introduced after first deploy (PostgreSQL)."""
    if engine.dialect.name != "postgresql":
        return
    stmts = [
        "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS last_interpretation JSONB",
        "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS last_visualization JSONB",
    ]
    with engine.begin() as conn:
        for sql in stmts:
            conn.execute(text(sql))
from src.models import QueryAuditLog, QueryHistory, QueryLog, ReportSchedule, SavedReport, User  # noqa: F401
from src.services.dataset_loader import import_all_datasets_if_needed


def seed_superuser(db: Session) -> None:
    existing = db.query(User).filter(User.email == settings.first_superuser_email.lower()).first()
    if existing:
        return

    user = User(
        email=settings.first_superuser_email.lower(),
        full_name="Admin",
        hashed_password=hash_password(settings.first_superuser_password),
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_saved_reports_extras()
    with SessionLocal() as db:
        seed_superuser(db)
    import_all_datasets_if_needed()

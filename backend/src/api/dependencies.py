from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.core.jwt import decode_access_token
from src.crud.user import get_user_by_email
from src.db.session import get_db
from src.models.user import User

# OAuth2 Password Bearer flow for Swagger Authorize button.
# The URL is relative to the FastAPI app root and includes API_PREFIX=/api.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise credentials_exception

    user = get_user_by_email(db, str(payload["sub"]))
    if not user or not user.is_active:
        raise credentials_exception

    return user


def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser permissions required",
        )
    return current_user

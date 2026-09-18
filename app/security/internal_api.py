import hmac

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import INTERNAL_API_TOKEN


bearer_scheme = HTTPBearer(auto_error=False)


def require_internal_api_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> None:
    """Allow internal endpoints only with the configured bearer token."""

    if not INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Internal API access is not configured.",
        )

    if (
        credentials is None
        or credentials.scheme.casefold() != "bearer"
        or not hmac.compare_digest(
            credentials.credentials,
            INTERNAL_API_TOKEN,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing internal API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

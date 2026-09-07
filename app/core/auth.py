# app/core/auth.py
import hashlib
import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ClientIdentity:
    client_id: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
) -> ClientIdentity:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials
    token_hash = hash_token(raw_token)

    # settings.CLIENT_API_KEYS holds a mapping of {client_id: sha256_hash}
    matched_client_id: str | None = None
    for client_id, valid_hash in settings.CLIENT_API_KEYS.items():
        if hmac.compare_digest(token_hash, valid_hash):
            matched_client_id = client_id
            break

    if not matched_client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unauthorized API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return ClientIdentity(client_id=matched_client_id)
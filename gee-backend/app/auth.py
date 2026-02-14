"""
Authentication module for Consorcio Canalero API.
Implements JWT verification using Supabase tokens.

Supports both legacy HS256 and modern ES256 (P-256) JWT algorithms.
Supabase projects created after 2024 use ES256 by default.
"""

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx
import json
import base64

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Cache for JWKS keys
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_time: float = 0


# Security scheme
security = HTTPBearer(auto_error=False)


class User(BaseModel):
    """Authenticated user model."""
    id: str
    email: Optional[str] = None
    role: str = "ciudadano"


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str
    email: Optional[str] = None
    role: Optional[str] = None
    exp: int


async def get_jwks() -> Dict[str, Any]:
    """
    Fetch JWKS (JSON Web Key Set) from Supabase.
    Caches the result for 1 hour.
    """
    import time
    global _jwks_cache, _jwks_cache_time

    # Return cached if less than 1 hour old
    if _jwks_cache and (time.time() - _jwks_cache_time) < 3600:
        return _jwks_cache

    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url, timeout=10.0)
            if response.status_code == 200:
                _jwks_cache = response.json()
                _jwks_cache_time = time.time()
                logger.debug("JWKS fetched successfully", keys_count=len(_jwks_cache.get("keys", [])))
                return _jwks_cache
    except Exception as e:
        logger.warning("Failed to fetch JWKS", error=str(e))

    return _jwks_cache or {"keys": []}


def get_signing_key_from_jwks(jwks: Dict[str, Any], kid: str) -> Optional[str]:
    """Extract the signing key from JWKS matching the key ID."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            # Return the key in JWK format for jose to use
            return key
    return None


def decode_jwt_header(token: str) -> Dict[str, Any]:
    """Decode JWT header without verification to get algorithm and key ID."""
    try:
        header_segment = token.split(".")[0]
        # Add padding if needed
        padding = 4 - len(header_segment) % 4
        if padding != 4:
            header_segment += "=" * padding
        header_data = base64.urlsafe_b64decode(header_segment)
        return json.loads(header_data)
    except Exception:
        return {}


async def verify_supabase_token(token: str) -> Optional[TokenPayload]:
    """
    Verify a Supabase JWT token.
    Supports both HS256 (legacy) and ES256 (modern P-256) algorithms.
    """
    try:
        # First, decode the header to determine the algorithm
        header = decode_jwt_header(token)
        alg = header.get("alg", "HS256")
        kid = header.get("kid")

        logger.debug("JWT header decoded", algorithm=alg, kid=kid)

        if alg == "ES256":
            # Modern Supabase uses ES256 with JWKS
            jwks = await get_jwks()

            if kid:
                signing_key = get_signing_key_from_jwks(jwks, kid)
                if not signing_key:
                    logger.warning("No matching key found in JWKS", kid=kid)
                    return None

                # Decode using the JWK
                payload = jwt.decode(
                    token,
                    signing_key,
                    algorithms=["ES256"],
                    audience="authenticated",
                )
            else:
                # Try all keys if no kid specified
                for key in jwks.get("keys", []):
                    try:
                        payload = jwt.decode(
                            token,
                            key,
                            algorithms=["ES256"],
                            audience="authenticated",
                        )
                        break
                    except JWTError:
                        continue
                else:
                    logger.warning("No valid key found for ES256 token")
                    return None
        else:
            # Legacy HS256 with shared secret
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )

        return TokenPayload(
            sub=payload.get("sub", ""),
            email=payload.get("email"),
            role=payload.get("role", payload.get("user_metadata", {}).get("role")),
            exp=payload.get("exp", 0),
        )
    except JWTError as e:
        logger.warning("JWT verification failed", error=str(e))
        return None


async def get_user_role(user_id: str) -> str:
    """Get user role from Supabase perfiles table."""
    try:
        # Use httpx to query Supabase directly
        # Soporta tanto formato nuevo (2025+) como legacy
        api_key = settings.effective_secret_key or settings.effective_publishable_key
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.supabase_url}/rest/v1/perfiles",
                params={"id": f"eq.{user_id}", "select": "rol"},
                headers={
                    "apikey": api_key,
                    "Authorization": f"Bearer {api_key}",
                },
            )
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return data[0].get("rol", "ciudadano")
    except Exception as e:
        logger.error("Error fetching user role", error=str(e), user_id=user_id)
    return "ciudadano"


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Optional[User]:
    """
    Get current authenticated user from JWT token.
    Returns None if no valid token is provided.
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = await verify_supabase_token(token)

    if not payload:
        return None

    # Get role from database for accurate permission check
    role = await get_user_role(payload.sub)

    return User(
        id=payload.sub,
        email=payload.email,
        role=role,
    )


async def get_current_user_required(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> User:
    """
    Get current authenticated user. Raises 401 if not authenticated.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionaron credenciales de autenticacion",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = await verify_supabase_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = await get_user_role(payload.sub)

    return User(
        id=payload.sub,
        email=payload.email,
        role=role,
    )


def require_roles(allowed_roles: List[str]):
    """
    Dependency factory that requires specific roles.
    Usage: Depends(require_roles(["admin", "operador"]))
    """
    async def role_checker(
        user: User = Depends(get_current_user_required),
    ) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta accion",
            )
        return user
    return role_checker


# Convenience dependencies
require_admin = require_roles(["admin"])
require_admin_or_operator = require_roles(["admin", "operador"])
require_authenticated = get_current_user_required

# src/rlcoach/api/auth.py
"""JWT authentication for FastAPI.

Verifies JWT tokens issued by NextAuth.js and provides
FastAPI dependencies for protected routes.
"""

from __future__ import annotations

import os
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ..db import User, get_session

# JWT configuration - must match NextAuth settings
# NextAuth uses HS256 by default with NEXTAUTH_SECRET
ALGORITHM = "HS256"


class TokenData(BaseModel):
    """Data extracted from JWT token."""

    user_id: str
    email: str | None = None
    subscription_tier: str = "free"
    exp: int | None = None


class CurrentUser(BaseModel):
    """Current authenticated user with subscription info."""

    id: str
    email: str | None = None
    name: str | None = None
    subscription_tier: str = "free"
    is_pro: bool = False


def get_jwt_secret() -> str:
    """Get the JWT secret from environment."""
    secret = os.getenv("NEXTAUTH_SECRET")
    if not secret:
        raise RuntimeError("NEXTAUTH_SECRET environment variable not set")
    return secret


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        TokenData with user information

    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        secret = get_jwt_secret()
        # PyJWT validates expiration automatically by default
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])

        # NextAuth JWT structure
        user_id: str | None = payload.get("userId") or payload.get("sub")
        if user_id is None:
            raise credentials_exception

        return TokenData(
            user_id=user_id,
            email=payload.get("email"),
            subscription_tier=payload.get("subscriptionTier", "free"),
            exp=payload.get("exp"),
        )

    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except InvalidTokenError as e:
        raise credentials_exception from e


def get_token_from_header(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract Bearer token from Authorization header.

    Args:
        authorization: Authorization header value

    Returns:
        Token string

    Raises:
        HTTPException: If no token or invalid format
    """
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


async def get_current_user(
    token: Annotated[str, Depends(get_token_from_header)],
    db: Annotated[DBSession, Depends(get_session)],
) -> CurrentUser:
    """Get the current authenticated user.

    FastAPI dependency that extracts and validates the JWT token,
    then fetches user data from the database.

    Args:
        token: JWT token from Authorization header
        db: Database session

    Returns:
        CurrentUser with full user data

    Raises:
        HTTPException: If authentication fails
    """
    token_data = decode_token(token)

    # Fetch user from database
    user = db.query(User).filter(User.id == token_data.user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.display_name,
        subscription_tier=user.subscription_tier or "free",
        is_pro=(user.subscription_tier or "free") == "pro",
    )


async def get_current_user_optional(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[DBSession, Depends(get_session)] = None,
) -> CurrentUser | None:
    """Get the current user if authenticated, None otherwise.

    Use this for routes that work for both authenticated and
    anonymous users but provide additional features when logged in.

    Args:
        authorization: Optional Authorization header
        db: Database session

    Returns:
        CurrentUser if authenticated, None otherwise
    """
    if authorization is None:
        return None

    try:
        token = get_token_from_header(authorization)
        return await get_current_user(token, db)
    except HTTPException:
        return None


async def require_pro(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Require Pro subscription tier.

    FastAPI dependency that ensures the current user has Pro tier.

    Args:
        user: Current authenticated user

    Returns:
        CurrentUser if Pro tier

    Raises:
        HTTPException: If not Pro tier
    """
    if not user.is_pro:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pro subscription required",
        )
    return user


# Type aliases for cleaner dependency injection
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
OptionalUser = Annotated[CurrentUser | None, Depends(get_current_user_optional)]
ProUser = Annotated[CurrentUser, Depends(require_pro)]

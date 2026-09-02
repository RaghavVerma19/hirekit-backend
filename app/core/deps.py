import uuid
from typing import Callable, List, Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import Role, User

# Security scheme for Swagger UI
security_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT access token, returning the authenticated User."""
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_TOKEN",
                message="Token payload is missing subject.",
            )
        user_id = uuid.UUID(user_id_str)
    except jwt.ExpiredSignatureError:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="TOKEN_EXPIRED",
            message="Access token has expired. Please refresh your session.",
        )
    except (jwt.PyJWTError, ValueError) as e:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_TOKEN",
            message=f"Could not validate credentials: {str(e)}",
        )

    # Fetch active user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="USER_NOT_FOUND",
            message="User account associated with this token no longer exists.",
        )

    return user


async def require_verified(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure that the authenticated user has verified their email address."""
    if not current_user.is_verified:
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="EMAIL_NOT_VERIFIED",
            message="Please verify your email address to access this feature.",
            details={"email": current_user.email},
        )
    return current_user


def require_role(*roles: Role) -> Callable:
    """Dependency factory checking if current user possesses one of the allowed roles."""
    flat_roles: List[Role] = []
    for r in roles:
        if isinstance(r, (list, tuple, set)):
            flat_roles.extend(r)
        else:
            flat_roles.append(r)

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in flat_roles:
            raise AppException(
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="FORBIDDEN_ROLE",
                message="You do not have permission to perform this action.",
                details={
                    "required_roles": [r.value for r in flat_roles],
                    "user_role": current_user.role.value,
                },
            )
        return current_user

    return role_checker


def require_owner(resource_user_id: uuid.UUID, current_user: User) -> None:
    """Helper to guard against IDOR. Admins bypass this check."""
    if current_user.role == Role.ADMIN:
        return
    if resource_user_id != current_user.id:
        # Return 404 rather than 403 to prevent resource existence enumeration
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND",
            message="The requested resource was not found.",
        )

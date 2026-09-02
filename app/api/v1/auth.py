from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import AppException
from app.core.security import generate_random_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordIn,
    ResetPasswordIn,
    TokenOut,
    UserLogin,
    UserRegister,
    VerifyEmailIn,
)
from app.schemas.common import MessageOut
from app.schemas.user import UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_auth_cookies(response: Response, refresh_token: str) -> None:
    """Set secure HttpOnly refresh token cookie and CSRF cookie."""
    is_prod = settings.ENVIRONMENT == "production"
    
    # 1. HttpOnly Refresh Token Cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 3600,
        path=f"{settings.API_V1_STR}/auth",
    )

    # 2. Non-HttpOnly CSRF Cookie (readable by JS to include in X-CSRF-Token header)
    csrf_token = generate_random_token(24)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=is_prod,
        samesite="lax",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 3600,
        path=f"{settings.API_V1_STR}/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear authentication cookies."""
    response.delete_cookie(
        key="refresh_token",
        path=f"{settings.API_V1_STR}/auth",
    )
    response.delete_cookie(
        key="csrf_token",
        path=f"{settings.API_V1_STR}/auth",
    )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Student Account",
)
async def register(
    register_in: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Register a new student account."""
    user, verification_token = await AuthService.register(db, register_in)
    # Note: In production, SendGrid worker will email the verification_token
    return user


@router.post(
    "/login",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
    summary="Log In",
)
async def login(
    login_in: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    """Authenticate with email and password, setting secure refresh cookies."""
    user, access_token, raw_refresh_token = await AuthService.login(db, login_in)
    _set_auth_cookies(response, raw_refresh_token)
    return TokenOut(access_token=access_token)


@router.post(
    "/refresh",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
    summary="Refresh Access Token",
)
async def refresh_token(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    csrf_token: Optional[str] = Cookie(None),
    x_csrf_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    """Rotate refresh token and issue a fresh access token."""
    if not refresh_token:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="MISSING_REFRESH_TOKEN",
            message="No refresh token provided in request cookies.",
        )

    # Double-submit CSRF Protection check
    if settings.ENVIRONMENT == "production":
        if not csrf_token or not x_csrf_token or csrf_token != x_csrf_token:
            raise AppException(
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="CSRF_VALIDATION_FAILED",
                message="CSRF validation failed for token refresh.",
            )

    new_access_token, new_refresh_token = await AuthService.refresh_tokens(
        db, refresh_token
    )
    _set_auth_cookies(response, new_refresh_token)
    return TokenOut(access_token=new_access_token)


@router.post(
    "/logout",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Log Out",
)
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Revoke refresh token and clear authentication cookies."""
    await AuthService.logout(db, refresh_token)
    _clear_auth_cookies(response)
    return MessageOut(message="Successfully logged out.")


@router.post(
    "/verify-email",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Verify Email Address",
)
async def verify_email(
    verify_in: VerifyEmailIn,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Confirm email verification with single-use token."""
    await AuthService.verify_email(db, verify_in.token)
    return MessageOut(message="Email address verified successfully.")


@router.post(
    "/forgot-password",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Request Password Reset Link",
)
async def forgot_password(
    forgot_in: ForgotPasswordIn,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Send a password reset link (always returns success to prevent email enumeration)."""
    await AuthService.forgot_password(db, forgot_in.email)
    return MessageOut(
        message="If an account exists with this email, a password reset link has been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Reset Password with Token",
)
async def reset_password(
    reset_in: ResetPasswordIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Set new password with a valid reset token and revoke existing sessions."""
    await AuthService.reset_password(db, reset_in.token, reset_in.new_password)
    _clear_auth_cookies(response)
    return MessageOut(message="Password reset successfully. Please log in with your new password.")


@router.get(
    "/me",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Get Current User Profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """Retrieve profile of the currently authenticated user."""
    return current_user

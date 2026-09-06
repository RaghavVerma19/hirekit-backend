from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import uuid
from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import structlog

from app.core.config import settings
from app.core.errors import AppException
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    generate_random_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    Role,
    User,
    UserSettings,
)
from app.schemas.auth import UserLogin, UserRegister

logger = structlog.get_logger()


def _ensure_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class AuthService:
    @staticmethod
    async def register(
        db: AsyncSession, register_in: UserRegister
    ) -> Tuple[User, str]:
        """Register a new student account and generate email verification token."""
        # 1. Check if email already exists
        existing_user = await db.scalar(
            select(User).where(User.email == register_in.email.lower())
        )
        if existing_user:
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                error_code="EMAIL_ALREADY_EXISTS",
                message="An account with this email address already exists.",
            )

        # 2. Create User
        new_user = User(
            email=register_in.email.lower(),
            password_hash=hash_password(register_in.password),
            name=register_in.name,
            role=register_in.role,
            college_id=uuid.UUID("00000000-0000-0000-0000-000000000001") if register_in.role != Role.SUPER_ADMIN else None,
            is_verified=False,
            is_onboarded=False,
        )
        db.add(new_user)
        await db.flush()  # Flush to populate new_user.id

        # 3. Create Default UserSettings
        user_settings = UserSettings(
            user_id=new_user.id,
            email_notifications=True,
            push_notifications=True,
            job_alerts=True,
            interview_reminders=True,
            weekly_digest=True,
        )
        db.add(user_settings)

        # 4. Generate Email Verification Token
        raw_verification_token = generate_random_token(32)
        verification_token = EmailVerificationToken(
            user_id=new_user.id,
            token_hash=hash_token(raw_verification_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            used=False,
        )
        db.add(verification_token)
        await db.commit()
        await db.refresh(new_user)

        logger.info("user_registered", user_id=str(new_user.id), email=new_user.email)
        return new_user, raw_verification_token

    @staticmethod
    async def login(
        db: AsyncSession, login_in: UserLogin
    ) -> Tuple[User, str, str]:
        """Authenticate user, verify Argon2id hash, and issue token pair."""
        # Query user
        user = await db.scalar(
            select(User).options(joinedload(User.college)).where(User.email == login_in.email.lower())
        )

        if not user:
            # Timing attack prevention: verify against dummy hash
            verify_password(login_in.password, DUMMY_HASH)
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
            )

        # Verify password
        if not verify_password(login_in.password, user.password_hash):
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
            )

        if not user.is_active:
            raise AppException(
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="ACCOUNT_DEACTIVATED",
                message="Your account has been deactivated. Please contact support.",
            )

        # Generate Refresh Token
        raw_refresh_token = generate_random_token(48)
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
            revoked=False,
        )
        db.add(refresh_token_record)
        await db.commit()

        # Generate Access Token with Tenant Claims
        tenant_id = str(user.college_id) if user.college_id else None
        tenant_slug = user.college.slug if user.college else None
        access_token = create_access_token(
            user_id=str(user.id),
            role=user.role.value,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
        )

        logger.info("user_logged_in", user_id=str(user.id), email=user.email)
        return user, access_token, raw_refresh_token

    @staticmethod
    async def refresh_tokens(
        db: AsyncSession, raw_refresh_token: str
    ) -> Tuple[str, str]:
        """
        Rotate refresh token with 30s multi-tab grace period.
        If a compromised token is reused outside grace period, invalidate entire token tree.
        """
        token_h = hash_token(raw_refresh_token)
        rt = await db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_h)
        )

        if not rt:
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="INVALID_REFRESH_TOKEN",
                message="Invalid or expired session. Please log in again.",
            )

        now = datetime.now(timezone.utc)

        # If token was already revoked, check if within 30-second grace period
        if rt.revoked:
            revoked_at = _ensure_tz(rt.revoked_at)
            if revoked_at and (now - revoked_at).total_seconds() < 30:
                # Find the successor token that replaced this one
                successor = await db.scalar(
                    select(RefreshToken).where(
                        RefreshToken.previous_token_id == rt.id,
                        RefreshToken.revoked.is_(False),
                    )
                )
                if successor:
                    # Issue a fresh access token without failing
                    user = await db.scalar(select(User).options(joinedload(User.college)).where(User.id == rt.user_id))
                    if user:
                        new_access_token = create_access_token(
                            user_id=str(user.id),
                            role=user.role.value,
                        )
                        # We return the new access token. Client keeps existing active refresh token
                        return new_access_token, raw_refresh_token
            
            # If outside grace period, this is a replay attack. Nuke entire session family
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == rt.user_id)
                .values(revoked=True, revoked_at=now)
            )
            await db.commit()
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="SESSION_COMPROMISED",
                message="Security alert: Session compromised. Please log in again.",
            )

        expires_at = _ensure_tz(rt.expires_at)
        if expires_at and expires_at < now:
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="REFRESH_TOKEN_EXPIRED",
                message="Refresh token expired. Please log in again.",
            )

        user = await db.scalar(select(User).options(joinedload(User.college)).where(User.id == rt.user_id))
        if not user:
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="USER_NOT_FOUND",
                message="User no longer exists.",
            )

        # Normal Rotation: Revoke current token
        rt.revoked = True
        rt.revoked_at = now

        # Create new refresh token
        raw_new_refresh_token = generate_random_token(48)
        new_rt = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_new_refresh_token),
            previous_token_id=rt.id,
            expires_at=now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
            revoked=False,
        )
        db.add(new_rt)

        # Create new access token with Tenant Claims
        tenant_id = str(user.college_id) if user.college_id else None
        tenant_slug = user.college.slug if user.college else None
        new_access_token = create_access_token(
            user_id=str(user.id),
            role=user.role.value,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
        )
        await db.commit()

        return new_access_token, raw_new_refresh_token

    @staticmethod
    async def logout(db: AsyncSession, raw_refresh_token: Optional[str]) -> None:
        """Revoke a refresh token on logout."""
        if not raw_refresh_token:
            return
        token_h = hash_token(raw_refresh_token)
        now = datetime.now(timezone.utc)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_h)
            .values(revoked=True, revoked_at=now)
        )
        await db.commit()

    @staticmethod
    async def verify_email(db: AsyncSession, raw_token: str) -> User:
        """Verify user's email using verification token."""
        token_h = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        token_record = await db.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_h,
                EmailVerificationToken.used.is_(False),
                EmailVerificationToken.expires_at > now,
            )
        )

        if not token_record:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_VERIFICATION_TOKEN",
                message="Verification token is invalid or has expired.",
            )

        token_record.used = True
        user = await db.get(User, token_record.user_id)
        if not user:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="USER_NOT_FOUND",
                message="User not found.",
            )

        user.is_verified = True
        await db.commit()
        await db.refresh(user)

        logger.info("email_verified", user_id=str(user.id))
        return user

    @staticmethod
    async def forgot_password(db: AsyncSession, email: str) -> Optional[Tuple[User, str]]:
        """Generate a password reset token (returns None if user not found, without leaking)."""
        user = await db.scalar(
            select(User).where(User.email == email.lower())
        )
        if not user:
            return None

        raw_token = generate_random_token(32)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            used=False,
        )
        db.add(reset_token)
        await db.commit()

        logger.info("password_reset_requested", user_id=str(user.id))
        return user, raw_token

    @staticmethod
    async def reset_password(
        db: AsyncSession, raw_token: str, new_password: str
    ) -> User:
        """Reset user's password and revoke all active refresh tokens."""
        token_h = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        token_record = await db.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_h,
                PasswordResetToken.used.is_(False),
                PasswordResetToken.expires_at > now,
            )
        )

        if not token_record:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_RESET_TOKEN",
                message="Password reset token is invalid or has expired.",
            )

        token_record.used = True
        user = await db.get(User, token_record.user_id)
        if not user:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="USER_NOT_FOUND",
                message="User not found.",
            )

        user.password_hash = hash_password(new_password)

        # Security: Revoke all existing refresh tokens
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .values(revoked=True, revoked_at=now)
        )

        await db.commit()
        await db.refresh(user)

        logger.info("password_reset_successful", user_id=str(user.id))
        return user

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User, UserSettings
from app.schemas.settings import UserSettingsIn, UserSettingsOut

router = APIRouter(prefix='/settings', tags=['User Settings'])


@router.get('', response_model=UserSettingsOut, status_code=status.HTTP_200_OK)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsOut:
    res = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = res.scalar_one_or_none()

    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return UserSettingsOut.model_validate(settings)


@router.put('', response_model=UserSettingsOut, status_code=status.HTTP_200_OK)
async def update_settings(
    body: UserSettingsIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsOut:
    res = await db.execute(select(UserSettings).where(UserSettings.user_id == current_user.id))
    settings = res.scalar_one_or_none()

    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    for k, v in body.model_dump().items():
        setattr(settings, k, v)

    await db.commit()
    await db.refresh(settings)
    return UserSettingsOut.model_validate(settings)

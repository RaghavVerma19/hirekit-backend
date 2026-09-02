from typing import List
import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.application import ApplicationDetailOut, ApplicationOut
from app.services.application_service import ApplicationService

router = APIRouter(prefix="/applications", tags=["Applications & Tracking"])


@router.get(
    "",
    response_model=List[ApplicationOut],
    status_code=status.HTTP_200_OK,
    summary="List My Applications",
)
async def list_my_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ApplicationOut]:
    """Retrieve all applications submitted by the logged-in student."""
    applications = await ApplicationService.list_applications(db, current_user.id)
    return [ApplicationOut.model_validate(a) for a in applications]


@router.get(
    "/{application_id}",
    response_model=ApplicationDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Get Application Status & Timeline",
)
async def get_application_detail(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailOut:
    """View application stage and full event history (interview calls, offers, reviews)."""
    application = await ApplicationService.get_application(
        db, current_user.id, application_id
    )
    return ApplicationDetailOut.model_validate(application)


@router.delete(
    "/{application_id}",
    response_model=ApplicationDetailOut,
    status_code=status.HTTP_200_OK,
    summary="Withdraw Application",
)
async def withdraw_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailOut:
    """Withdraw an active application."""
    application = await ApplicationService.withdraw(db, current_user.id, application_id)
    return ApplicationDetailOut.model_validate(application)

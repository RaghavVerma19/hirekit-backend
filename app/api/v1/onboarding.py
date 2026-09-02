from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageOut
from app.schemas.onboarding import OnboardingStatusOut, OnboardingStepOut

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get(
    "/status",
    response_model=OnboardingStatusOut,
    status_code=status.HTTP_200_OK,
    summary="Get Onboarding Wizard Status",
)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
) -> OnboardingStatusOut:
    """Check student onboarding progress and required setup steps."""
    steps = [
        OnboardingStepOut(
            step_number=1,
            title="Complete Basic Information",
            description="Add your contact info and degree department.",
            is_completed=bool(current_user.name and current_user.phone),
        ),
        OnboardingStepOut(
            step_number=2,
            title="Upload Marksheet & Enter CGPA",
            description="Verify your academic eligibility.",
            is_completed=False,
        ),
        OnboardingStepOut(
            step_number=3,
            title="Create & Score Your Resume",
            description="Run AI ATS audit to optimize keyword match.",
            is_completed=False,
        ),
    ]

    return OnboardingStatusOut(
        is_onboarded=current_user.is_onboarded,
        current_step=1 if not current_user.is_onboarded else 3,
        total_steps=3,
        steps=steps,
    )


@router.post(
    "/complete",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Complete Onboarding Flow",
)
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Mark the student onboarding process as completed."""
    current_user.is_onboarded = True
    await db.commit()
    return MessageOut(message="Onboarding completed successfully.")

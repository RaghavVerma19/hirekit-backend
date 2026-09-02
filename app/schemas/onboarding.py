from typing import List, Optional
from pydantic import BaseModel


class OnboardingStepOut(BaseModel):
    step_number: int
    title: str
    description: str
    is_completed: bool


class OnboardingStatusOut(BaseModel):
    is_onboarded: bool
    current_step: int
    total_steps: int
    steps: List[OnboardingStepOut]

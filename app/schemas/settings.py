from pydantic import BaseModel, ConfigDict


class UserSettingsIn(BaseModel):
    email_notifications: bool = True
    push_notifications: bool = True
    job_alerts: bool = True
    interview_reminders: bool = True
    weekly_digest: bool = True


class UserSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_notifications: bool
    push_notifications: bool
    job_alerts: bool
    interview_reminders: bool
    weekly_digest: bool

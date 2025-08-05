from pydantic import BaseModel


class UserPublic(BaseModel):
    id: str
    email: str
    role: str
    subscription_tier: str

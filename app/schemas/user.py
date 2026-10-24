import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.membership import Role


class UserOut(BaseModel):
    # Lets Pydantic read the fields straight off a SQLAlchemy User object.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime


class MeResponse(BaseModel):
    user: UserOut
    workspace_id: uuid.UUID
    role: Role

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import Role


class AddMemberRequest(BaseModel):
    email: EmailStr  
    role: Role


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role


class MemberDetail(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: Role

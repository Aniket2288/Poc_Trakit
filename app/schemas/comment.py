import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.issue import PersonOut


class CommentCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"body": "I can reproduce this on Safari 17."}]})

    body: str = Field(min_length=1, max_length=5000)


class CommentUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: uuid.UUID
    author: PersonOut
    body: str
    edited_at: datetime | None
    created_at: datetime


class CommentRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    body: str  # the text BEFORE that edit
    edited_by: uuid.UUID
    created_at: datetime


class AttachmentOut(BaseModel):
    id: uuid.UUID
    issue_id: uuid.UUID
    original_name: str
    content_type: str
    size_bytes: int
    uploaded_by: uuid.UUID
    created_at: datetime
    download_url: str  # signed, expires after a few minutes

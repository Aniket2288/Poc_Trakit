import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import IssuePriority, IssueStatus


def clean_labels(labels: list[str] | None) -> list[str] | None:
    """Trim, lowercase and de-duplicate label names: [" Bug", "bug "] -> ["bug"]."""
    if labels is None:
        return None
    cleaned = sorted({name.strip().lower() for name in labels if name.strip()})
    if any(len(name) > 30 for name in cleaned):
        raise ValueError("Each label must be 30 characters or fewer")
    if len(cleaned) > 10:
        raise ValueError("An issue can have at most 10 labels")
    return cleaned


# ---------- Requests ----------

class IssueCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Login button does nothing on Safari",
                    "description": "Clicking Log in on Safari 17 shows no error and no request.",
                    "priority": "high",
                    "due_date": "2026-10-31",
                    "assignee_id": None,
                    "labels": ["bug", "frontend"],
                }
            ]
        }
    )

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    priority: IssuePriority = IssuePriority.MEDIUM
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None
    labels: list[str] = []

    @field_validator("labels")
    @classmethod
    def check_labels(cls, labels):
        return clean_labels(labels)


class IssueUpdate(BaseModel):
    """Send only the fields you want to change. Status and assignee have their own endpoints."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"priority": "urgent", "labels": ["bug"]}]})

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    priority: IssuePriority | None = None
    due_date: date | None = None
    labels: list[str] | None = None

    @field_validator("labels")
    @classmethod
    def check_labels(cls, labels):
        return clean_labels(labels)


class AssignRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"assignee_id": "3403a770-ead2-405b-85f2-8c389b1c8676"}, {"assignee_id": None}]})

    assignee_id: uuid.UUID | None  # null = unassign


class TransitionRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "in_progress"}]})

    status: IssueStatus


# ---------- Responses ----------

class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str


class IssueOut(BaseModel):
    id: uuid.UUID
    key: str  # e.g. "TRK-12"
    project_id: uuid.UUID
    number: int
    title: str
    description: str | None
    status: IssueStatus
    priority: IssuePriority
    due_date: date | None
    assignee: PersonOut | None
    reporter_id: uuid.UUID
    labels: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_issue(cls, issue) -> "IssueOut":
        return cls(
            id=issue.id,
            key=f"{issue.project.key}-{issue.number}",
            project_id=issue.project_id,
            number=issue.number,
            title=issue.title,
            description=issue.description,
            status=issue.status,
            priority=issue.priority,
            due_date=issue.due_date,
            assignee=PersonOut.model_validate(issue.assignee) if issue.assignee else None,
            reporter_id=issue.reporter_id,
            labels=sorted(label.name for label in issue.labels),
            created_at=issue.created_at,
            updated_at=issue.updated_at,
        )


class IssuePage(BaseModel):
    items: list[IssueOut]
    total: int
    limit: int
    offset: int


class IssueSort(str, Enum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    DUE_DATE = "due_date"
    PRIORITY = "priority"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


@dataclass
class IssueFilters:
    """The optional filters of GET /issues, bundled so they travel through the layers as one value."""

    project_id: uuid.UUID | None = None
    status: IssueStatus | None = None
    assignee_id: uuid.UUID | None = None
    label: str | None = None
    priority: IssuePriority | None = None
    q: str | None = None

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.core.database import get_db
from app.models import IssuePriority, IssueStatus, Role
from app.schemas.issue import AssignRequest, IssueCreate, IssueFilters, IssueOut, IssuePage, IssueSort, IssueUpdate, SortOrder, TransitionRequest
from app.services import issue_service

router = APIRouter(tags=["issues"])

anyone = get_current_user
editors = require_role(Role.ADMIN, Role.MEMBER)


@router.post("/projects/{project_id}/issues", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
def create_issue(project_id: uuid.UUID, data: IssueCreate, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    """Create an issue in a project. It always starts in **Backlog**."""
    issue = issue_service.create_issue(db, current.workspace_id, current.user_id, project_id, data)
    return IssueOut.from_issue(issue)


@router.get("/issues", response_model=IssuePage)
def list_issues(
    project_id: uuid.UUID | None = Query(None, description="Only issues in this project"),
    status_filter: IssueStatus | None = Query(None, alias="status", examples=["in_progress"]),
    assignee_id: uuid.UUID | None = Query(None, description="Only issues assigned to this user"),
    label: str | None = Query(None, examples=["bug"]),
    priority: IssuePriority | None = Query(None, examples=["high"]),
    q: str | None = Query(None, min_length=1, max_length=100, description="Text search in title and description", examples=["login"]),
    sort: IssueSort = Query(IssueSort.CREATED_AT, examples=["due_date"]),
    order: SortOrder = Query(SortOrder.DESC, examples=["asc"]),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="How many issues to skip"),
    current: CurrentUser = Depends(anyone),
    db: Session = Depends(get_db),
):
    """
    List issues in your workspace, with offset pagination.

    Example: `GET /issues?status=in_progress&label=bug&q=login&sort=due_date&order=asc&limit=20&offset=0`
    """
    filters = IssueFilters(project_id=project_id, status=status_filter, assignee_id=assignee_id, label=label, priority=priority, q=q)
    issues, total = issue_service.list_issues(db, current.workspace_id, filters, sort, order, limit, offset)
    return IssuePage(items=[IssueOut.from_issue(i) for i in issues], total=total, limit=limit, offset=offset)


@router.get("/issues/{issue_id}", response_model=IssueOut)
def get_issue(issue_id: uuid.UUID, current: CurrentUser = Depends(anyone), db: Session = Depends(get_db)):
    return IssueOut.from_issue(issue_service.get_issue(db, current.workspace_id, issue_id))


@router.patch("/issues/{issue_id}", response_model=IssueOut)
def update_issue(issue_id: uuid.UUID, data: IssueUpdate, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    return IssueOut.from_issue(issue_service.update_issue(db, current.workspace_id, current.user_id, issue_id, data))


@router.post("/issues/{issue_id}/assign", response_model=IssueOut)
def assign_issue(issue_id: uuid.UUID, data: AssignRequest, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    """Assign to a workspace member, or send `null` to unassign."""
    return IssueOut.from_issue(issue_service.assign_issue(db, current.workspace_id, current.user_id, issue_id, data))


@router.post(
    "/issues/{issue_id}/transition",
    response_model=IssueOut,
    responses={422: {"description": "The state machine does not allow this move, e.g. Backlog → Done"}},
)
def transition_issue(issue_id: uuid.UUID, data: TransitionRequest, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    """Move an issue to a new status. Allowed: Backlog→In Progress, In Progress→Backlog/Review, Review→In Progress/Done, Done→In Progress."""
    return IssueOut.from_issue(issue_service.transition_issue(db, current.workspace_id, current.user_id, issue_id, data))

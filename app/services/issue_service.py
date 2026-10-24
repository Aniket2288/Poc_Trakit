import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidTransitionError, NotFoundError, UnprocessableError
from app.models import Issue, IssueStatus
from app.repositories import issue_repository, workspace_repository
from app.schemas.issue import AssignRequest, IssueCreate, IssueFilters, IssueSort, IssueUpdate, SortOrder, TransitionRequest
from app.services import audit_service, jobs, project_service



ALLOWED_TRANSITIONS: dict[IssueStatus, set[IssueStatus]] = {
    IssueStatus.BACKLOG: {IssueStatus.IN_PROGRESS},
    IssueStatus.IN_PROGRESS: {IssueStatus.BACKLOG, IssueStatus.REVIEW},
    IssueStatus.REVIEW: {IssueStatus.IN_PROGRESS, IssueStatus.DONE},
    IssueStatus.DONE: {IssueStatus.IN_PROGRESS},
}

STATUS_NAMES = {
    IssueStatus.BACKLOG: "Backlog",
    IssueStatus.IN_PROGRESS: "In Progress",
    IssueStatus.REVIEW: "Review",
    IssueStatus.DONE: "Done",
}


def check_transition(current: IssueStatus, new: IssueStatus) -> None:
    """Raise a clear 422 if the state machine doesn't allow current -> new."""
    allowed = ALLOWED_TRANSITIONS[current]
    if new not in allowed:
        allowed_names = ", ".join(STATUS_NAMES[s] for s in sorted(allowed, key=list(STATUS_NAMES).index))
        raise InvalidTransitionError(
            f"Cannot move an issue from {STATUS_NAMES[current]} to {STATUS_NAMES[new]}. Allowed next: {allowed_names}."
        )


# ---------- Reads ----------

def get_issue(db: Session, workspace_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
    issue = issue_repository.get_in_workspace(db, issue_id, workspace_id)
    if issue is None:
        raise NotFoundError("Issue not found")
    return issue


def list_issues(db: Session, workspace_id: uuid.UUID, filters: IssueFilters, sort: IssueSort, order: SortOrder, limit: int, offset: int):
    return issue_repository.list_issues(db, workspace_id, filters, sort, order, limit, offset)


# ---------- Writes (each one is audited and committed once) ----------

def create_issue(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, project_id: uuid.UUID, data: IssueCreate) -> Issue:
    project_service.get_project(db, workspace_id, project_id)  # 404 if it's not in this workspace
    if data.assignee_id:
        _check_assignee_is_member(db, workspace_id, data.assignee_id)

    issue = Issue(
        workspace_id=workspace_id,
        project_id=project_id,
        number=issue_repository.next_issue_number(db, project_id),
        title=data.title,
        description=data.description,
        status=IssueStatus.BACKLOG,  # every issue starts in Backlog
        priority=data.priority,
        due_date=data.due_date,
        assignee_id=data.assignee_id,
        reporter_id=actor_id,
    )
    issue.labels = issue_repository.get_or_create_labels(db, workspace_id, data.labels)
    issue_repository.add(db, issue)

    _audit(db, issue, actor_id, "issue.created", after=snapshot(issue))
    assigned = None
    if issue.assignee_id:
        assigned = _audit(db, issue, actor_id, "issue.assigned", before={"assignee_id": None}, after={"assignee_id": str(issue.assignee_id)})
    db.commit()
    if assigned:
        jobs.enqueue_assignment_email(assigned.id)  # only after commit, so the worker can see the issue
    return issue


def update_issue(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, issue_id: uuid.UUID, data: IssueUpdate) -> Issue:
    issue = get_issue(db, workspace_id, issue_id)
    before = snapshot(issue)

    changes = data.model_dump(exclude_unset=True)
    labels = changes.pop("labels", None)
    for field, value in changes.items():
        setattr(issue, field, value)
    if labels is not None:
        issue.labels = issue_repository.get_or_create_labels(db, workspace_id, labels)

    _audit(db, issue, actor_id, "issue.updated", before=before, after=snapshot(issue))
    db.commit()
    return issue


def assign_issue(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, issue_id: uuid.UUID, data: AssignRequest) -> Issue:
    issue = get_issue(db, workspace_id, issue_id)
    if data.assignee_id == issue.assignee_id:
        return issue  # nothing changes, so no audit entry and no email
    if data.assignee_id:
        _check_assignee_is_member(db, workspace_id, data.assignee_id)

    before = {"assignee_id": _str(issue.assignee_id)}
    issue.assignee_id = data.assignee_id
    event = _audit(db, issue, actor_id, "issue.assigned", before=before, after={"assignee_id": _str(issue.assignee_id)})
    db.commit()
    if issue.assignee_id:
        jobs.enqueue_assignment_email(event.id)  # after commit: the job must never see uncommitted data
    return issue


def transition_issue(db: Session, workspace_id: uuid.UUID, actor_id: uuid.UUID, issue_id: uuid.UUID, data: TransitionRequest) -> Issue:
    issue = get_issue(db, workspace_id, issue_id)
    if data.status == issue.status:
        return issue  # already there: a repeat click is harmless
    check_transition(issue.status, data.status)

    before = {"status": issue.status.value}
    issue.status = data.status
    _audit(db, issue, actor_id, "issue.status_changed", before=before, after={"status": issue.status.value})
    db.commit()
    return issue


# ---------- Helpers ----------

def snapshot(issue: Issue) -> dict:
    data = audit_service.snapshot(issue, ["title", "description", "status", "priority", "due_date", "assignee_id"])
    data["labels"] = sorted(label.name for label in issue.labels)
    return data


def _audit(db: Session, issue: Issue, actor_id: uuid.UUID, action: str, before: dict | None = None, after: dict | None = None):
    return audit_service.record(
        db, workspace_id=issue.workspace_id, actor_id=actor_id, action=action, entity_type="issue",
        entity_id=issue.id, before=before, after=after,
    )


def _check_assignee_is_member(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    if workspace_repository.get_membership(db, user_id, workspace_id) is None:
        raise UnprocessableError("The assignee must be a member of this workspace")


def _str(value) -> str | None:
    return str(value) if value is not None else None

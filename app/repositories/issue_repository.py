import uuid
from datetime import date

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Issue, IssuePriority, IssueStatus, Label, Project
from app.schemas.issue import IssueFilters, IssueSort, SortOrder


# Sorting by the enum text would give high < low < medium < urgent. This maps each to its real rank.
PRIORITY_RANK = case(
    {IssuePriority.LOW: 1, IssuePriority.MEDIUM: 2, IssuePriority.HIGH: 3, IssuePriority.URGENT: 4},
    value=Issue.priority,
)
SORT_COLUMNS = {
    IssueSort.CREATED_AT: Issue.created_at,
    IssueSort.UPDATED_AT: Issue.updated_at,
    IssueSort.DUE_DATE: Issue.due_date,
    IssueSort.PRIORITY: PRIORITY_RANK,
}


def next_issue_number(db: Session, project_id: uuid.UUID) -> int:
    """
    Atomically bump the project's counter and return the new value.

    Doing it as one UPDATE ... RETURNING means Postgres locks the project row for us, so two
    issues created at the same moment can never both get number 5.
    """
    return db.scalar(
        update(Project)
        .where(Project.id == project_id)
        .values(issue_counter=Project.issue_counter + 1)
        .returning(Project.issue_counter)
    )


def add(db: Session, issue: Issue) -> Issue:
    db.add(issue)
    db.flush()
    return issue


def get_in_workspace(db: Session, issue_id: uuid.UUID, workspace_id: uuid.UUID) -> Issue | None:
    return db.scalar(select(Issue).where(Issue.id == issue_id, Issue.workspace_id == workspace_id))


def list_issues(
    db: Session, workspace_id: uuid.UUID, filters: IssueFilters, sort: IssueSort, order: SortOrder, limit: int, offset: int
) -> tuple[list[Issue], int]:
    query = select(Issue).where(Issue.workspace_id == workspace_id)

    if filters.project_id:
        query = query.where(Issue.project_id == filters.project_id)
    if filters.status:
        query = query.where(Issue.status == filters.status)
    if filters.assignee_id:
        query = query.where(Issue.assignee_id == filters.assignee_id)
    if filters.priority:
        query = query.where(Issue.priority == filters.priority)
    if filters.label:
        query = query.where(Issue.labels.any(Label.name == filters.label.strip().lower()))
    if filters.q:
        pattern = f"%{_escape_like(filters.q.strip())}%"
        query = query.where(or_(Issue.title.ilike(pattern, escape="\\"), Issue.description.ilike(pattern, escape="\\")))

    total = db.scalar(select(func.count()).select_from(query.subquery()))

    column = SORT_COLUMNS[sort]
    ordered = column.asc() if order == SortOrder.ASC else column.desc()
    # nulls_last: issues with no due date go to the end either way. Issue.id breaks ties so pages never overlap.
    query = query.order_by(ordered.nulls_last(), Issue.id).limit(limit).offset(offset)
    # Fix for the N+1: load what IssueOut needs up front instead of one lazy query per issue.
    #   selectinload(labels): ONE extra query, "... WHERE issue_id IN (<ids on this page>)"
    #   joinedload(assignee, project): fetched in the same SELECT through a LEFT JOIN
    query = query.options(selectinload(Issue.labels), joinedload(Issue.assignee), joinedload(Issue.project))
    return list(db.scalars(query).unique()), total


def list_overdue(db: Session, today: date) -> list[Issue]:
    """Every open, assigned issue whose due date has passed, across all workspaces (for the daily digest)."""
    return list(
        db.scalars(
            select(Issue)
            .where(Issue.due_date < today, Issue.status != IssueStatus.DONE, Issue.assignee_id.is_not(None))
            .order_by(Issue.assignee_id, Issue.due_date)
        )
    )


# ---------- Labels ----------

def get_or_create_labels(db: Session, workspace_id: uuid.UUID, names: list[str]) -> list[Label]:
    if not names:
        return []
    existing = {label.name: label for label in db.scalars(select(Label).where(Label.workspace_id == workspace_id, Label.name.in_(names)))}
    labels = []
    for name in names:
        label = existing.get(name)
        if label is None:
            label = Label(workspace_id=workspace_id, name=name)
            db.add(label)
        labels.append(label)
    db.flush()
    return labels


def _escape_like(text: str) -> str:
    """So a search for '50%' looks for the text '50%', not '50 followed by anything'."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

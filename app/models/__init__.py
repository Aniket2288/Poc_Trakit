# Importing every model registers it on Base.metadata, which Alembic reads.
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.comment import Attachment, Comment, CommentRevision
from app.models.issue import Issue, IssuePriority, IssueStatus, Label, issue_labels
from app.models.membership import Membership, Role
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.sent_email import SentEmail
from app.models.user import User
from app.models.workspace import Workspace

__all__ = ["Attachment", "AuditLog", "Base", "Comment", "CommentRevision", "Issue", "IssuePriority", "IssueStatus", "Label", "issue_labels", "User", "Workspace", "Membership", "Role", "Project", "RefreshToken", "SentEmail"]

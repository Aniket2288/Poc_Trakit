import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_role
from app.core import storage
from app.core.config import settings
from app.core.database import get_db
from app.models import Attachment, Role
from app.schemas.comment import AttachmentOut, CommentCreate, CommentOut, CommentRevisionOut, CommentUpdate
from app.services import comment_service

router = APIRouter(tags=["comments & attachments"])

anyone = get_current_user
editors = require_role(Role.ADMIN, Role.MEMBER)


# ---------- Comments ----------

@router.post("/issues/{issue_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(issue_id: uuid.UUID, data: CommentCreate, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    return comment_service.add_comment(db, current.workspace_id, current.user_id, issue_id, data.body)


@router.get("/issues/{issue_id}/comments", response_model=list[CommentOut])
def list_comments(issue_id: uuid.UUID, current: CurrentUser = Depends(anyone), db: Session = Depends(get_db)):
    return comment_service.list_comments(db, current.workspace_id, issue_id)


@router.patch("/comments/{comment_id}", response_model=CommentOut)
def edit_comment(comment_id: uuid.UUID, data: CommentUpdate, current: CurrentUser = Depends(editors), db: Session = Depends(get_db)):
    """Only the author can edit. The previous text is kept in the comment's history."""
    return comment_service.edit_comment(db, current.workspace_id, current.user_id, comment_id, data.body)


@router.get("/comments/{comment_id}/history", response_model=list[CommentRevisionOut])
def comment_history(comment_id: uuid.UUID, current: CurrentUser = Depends(anyone), db: Session = Depends(get_db)):
    """Earlier versions of the comment, newest first."""
    return comment_service.comment_history(db, current.workspace_id, comment_id)


# ---------- Attachments ----------

def _out(attachment: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=attachment.id, issue_id=attachment.issue_id, original_name=attachment.original_name, content_type=attachment.content_type,
        size_bytes=attachment.size_bytes, uploaded_by=attachment.uploaded_by, created_at=attachment.created_at,
        download_url=storage.signed_download_url(attachment.id),
    )


@router.post("/issues/{issue_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_attachment(
    issue_id: uuid.UUID, file: UploadFile = File(...), current: CurrentUser = Depends(editors), db: Session = Depends(get_db)
):
    """PNG, JPEG, GIF, PDF or plain text, up to 5 MB. The type is checked from the file's bytes, not its name."""
    # Read at most one byte past the limit, so a huge upload can't fill the server's memory.
    data = file.file.read(settings.max_upload_bytes + 1)
    attachment = comment_service.upload_attachment(db, current.workspace_id, current.user_id, issue_id, file.filename, data)
    return _out(attachment)


@router.get("/issues/{issue_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(issue_id: uuid.UUID, current: CurrentUser = Depends(anyone), db: Session = Depends(get_db)):
    """Each item has a fresh signed download_url that expires in 5 minutes."""
    return [_out(a) for a in comment_service.list_attachments(db, current.workspace_id, issue_id)]


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: uuid.UUID, expires: int = Query(...), signature: str = Query(...), db: Session = Depends(get_db)):
    """No Authorization header needed (so the link works in a browser tab): the signature in the URL is the proof."""
    attachment = comment_service.attachment_for_download(db, attachment_id, expires, signature)
    return FileResponse(
        storage.path_for(attachment.storage_key),
        media_type=attachment.content_type,
        filename=attachment.original_name,  # sent as Content-Disposition: attachment, so the browser downloads it
        headers={"X-Content-Type-Options": "nosniff"},
    )

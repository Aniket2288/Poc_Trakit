import uuid
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import security
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.models import Role


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> CurrentUser:
    if credentials is None:
        raise AuthenticationError("Not authenticated")

    claims = security.decode_token(credentials.credentials, security.ACCESS)
    return CurrentUser(
        user_id=uuid.UUID(claims["sub"]),
        workspace_id=uuid.UUID(claims["workspace_id"]),
        role=Role(claims["role"]),
    )


def require_role(*allowed_roles: Role):

    def check(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role not in allowed_roles:
            raise PermissionDeniedError("Your role cannot do this")
        return current

    return check

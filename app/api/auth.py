from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import auth_rate_limit
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, SignupRequest, TokenPair
from app.services import auth_service

# Every /auth/* route is rate limited per client IP (brute-force protection), see app/core/rate_limit.py.
router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(auth_rate_limit)])


@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    return auth_service.signup(db, data)


@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return auth_service.login(db, data)


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return auth_service.refresh(db, data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: LogoutRequest, db: Session = Depends(get_db)):
    auth_service.logout(db, data.refresh_token)


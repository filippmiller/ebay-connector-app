from datetime import datetime
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.db_models import Timesheet, User
from app.models.user import User as UserModel, UserRole
from app.services.auth import get_current_active_user
from app.config import settings

router = APIRouter(prefix="/api/timesheets", tags=["timesheets"])


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class Envelope(BaseModel):
    success: bool
    data: Optional[Any]
    error: Optional[ErrorDetail]


class UserResponse(BaseModel):
    id: str
    legacyId: Optional[int] = None
    username: str
    fullName: Optional[str] = None
    role: str
    hourlyRate: Optional[str] = None
    isActive: bool
    recordCreated: Optional[datetime] = None
    recordCreatedBy: Optional[str] = None
    recordUpdated: Optional[datetime] = None
    recordUpdatedBy: Optional[str] = None

    class Config:
        from_attributes = True


class TimesheetEntry(BaseModel):
    id: int
    userId: str
    username: str
    startTime: Optional[datetime]
    endTime: Optional[datetime]
    durationMinutes: Optional[int]
    rate: Optional[str]
    description: Optional[str]
    deleteFlag: bool
    recordCreated: datetime
    recordCreatedBy: Optional[str]
    recordUpdated: datetime
    recordUpdatedBy: Optional[str]

    class Config:
        from_attributes = True


class Pagination(BaseModel):
    items: List[TimesheetEntry]
    page: int
    pageSize: int
    totalItems: int
    totalPages: int


class StartStopRequest(BaseModel):
    description: Optional[str] = None


class AdminAddRequest(BaseModel):
    userId: str
    startTime: datetime
    endTime: datetime
    rate: Optional[str] = None
    description: Optional[str] = None


class AdminPatchRequest(BaseModel):
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    description: Optional[str] = None
    rate: Optional[str] = None
    deleteFlag: Optional[bool] = None


def _serialize_rate(val) -> Optional[str]:
    if val is None:
        return None
    return format(val, "0.2f")


def _to_timesheet_entry(ts: Timesheet) -> TimesheetEntry:
    return TimesheetEntry(
        id=ts.id,
        userId=ts.user_id,
        username=ts.username,
        startTime=ts.start_time,
        endTime=ts.end_time,
        durationMinutes=ts.duration_minutes,
        rate=_serialize_rate(ts.rate),
        description=ts.description,
        deleteFlag=bool(ts.delete_flag),
        recordCreated=ts.record_created,
        recordCreatedBy=ts.record_created_by,
        recordUpdated=ts.record_updated,
        recordUpdatedBy=ts.record_updated_by,
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "FORBIDDEN",
            "message": "Admin role required to access timesheet admin endpoints.",
        },
    )


@router.post("/start", response_model=Envelope)
async def start_timesheet(
    payload: StartStopRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    # Require at least an active user; any non-admin is treated as worker
    # Check for open timer
    open_entry = (
        db.query(Timesheet)
        .filter(
            Timesheet.user_id == current_user.id,
            Timesheet.end_time.is_(None),
            Timesheet.delete_flag.is_(False),
        )
        .order_by(Timesheet.start_time.desc())
        .first()
    )
    if open_entry:
        return Envelope(
            success=False,
            data=None,
            error=ErrorDetail(
                code="TIMER_ALREADY_RUNNING",
                message="You already have a running timer.",
                details={"timesheetId": open_entry.id},
            ),
        )

    user_row: User = db.query(User).filter(User.id == current_user.id).first()
    now = datetime.utcnow()

    ts = Timesheet(
        user_id=current_user.id,
        username=current_user.username,
        start_time=now,
        end_time=None,
        duration_minutes=None,
        rate=user_row.hourly_rate if user_row is not None else None,
        description=payload.description,
        delete_flag=False,
        record_created=now,
        record_created_by=current_user.username,
        record_updated=now,
        record_updated_by=current_user.username,
    )
    db.add(ts)
    db.commit()
    db.refresh(ts)

    return Envelope(success=True, data=_to_timesheet_entry(ts), error=None)


@router.post("/stop", response_model=Envelope)
async def stop_timesheet(
    payload: StartStopRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    ts: Optional[Timesheet] = (
        db.query(Timesheet)
        .filter(
            Timesheet.user_id == current_user.id,
            Timesheet.end_time.is_(None),
            Timesheet.delete_flag.is_(False),
        )
        .order_by(Timesheet.start_time.desc())
        .first()
    )
    if not ts:
        return Envelope(
            success=False,
            data=None,
            error=ErrorDetail(
                code="NO_ACTIVE_TIMER",
                message="You do not have an active timer to stop.",
            ),
        )

    now = datetime.utcnow()
    ts.end_time = now
    if payload.description is not None:
        ts.description = payload.description

    # duration in minutes, rounded
    if ts.start_time is not None:
        delta_sec = (now - ts.start_time).total_seconds()
        ts.duration_minutes = int(round(delta_sec / 60.0))

    ts.record_updated = now
    ts.record_updated_by = current_user.username

    db.commit()
    db.refresh(ts)

    return Envelope(success=True, data=_to_timesheet_entry(ts), error=None)


@router.get("/my", response_model=Envelope)
async def list_my_timesheets(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    pageSize: Optional[int] = Query(None, ge=1),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    query = db.query(Timesheet).filter(
        Timesheet.user_id == current_user.id,
        Timesheet.delete_flag.is_(False),
    )

    if from_ is not None:
        query = query.filter(Timesheet.start_time >= from_)
    if to is not None:
        query = query.filter(Timesheet.start_time < to)

    total_items = query.count()
    effective_page_size = pageSize or total_items or 1
    total_pages = (total_items + effective_page_size - 1) // effective_page_size if total_items else 1
    offset = (page - 1) * effective_page_size

    if pageSize is None:
        rows = query.order_by(Timesheet.start_time.desc()).all()
    else:
        rows = (
            query.order_by(Timesheet.start_time.desc())
            .offset(offset)
            .limit(pageSize)
            .all()
        )

    items = [_to_timesheet_entry(r) for r in rows]

    pagination = Pagination(
        items=items,
        page=page,
        pageSize=effective_page_size,
        totalItems=total_items,
        totalPages=total_pages,
    )

    return Envelope(success=True, data=pagination, error=None)


# ---- Admin endpoints ----


def _ensure_admin(current_user: UserModel) -> None:
    # Accept either plain string or UserRole enum; normalize to lowercase string.
    role_raw = getattr(current_user, "role", None)
    if hasattr(role_raw, "value"):
        role_ok = str(role_raw.value).lower() == "admin"
    else:
        role_ok = str(role_raw or "").lower() == "admin"
    allow_emails = (
        [e.strip().lower() for e in settings.ADMIN_EMAIL_ALLOWLIST.split(",") if e.strip()]
        if settings.ADMIN_EMAIL_ALLOWLIST
        else []
    )
    allow_usernames = (
        [u.strip().lower() for u in settings.ADMIN_USERNAME_ALLOWLIST.split(",") if u.strip()]
        if settings.ADMIN_USERNAME_ALLOWLIST
        else []
    )
    email = getattr(current_user, "email", "") or ""
    username = getattr(current_user, "username", "") or ""
    allowlist_ok = email.lower() in allow_emails or username.lower() in allow_usernames
    if not (role_ok or allowlist_ok):
        raise _forbidden()


@router.get("/", response_model=Envelope)
async def admin_list_timesheets(
    userId: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    pageSize: Optional[int] = Query(50, ge=1, le=200),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _ensure_admin(current_user)

    query = db.query(Timesheet).filter(Timesheet.delete_flag.is_(False))

    if userId:
        query = query.filter(Timesheet.user_id == userId)
    if username:
        like = f"%{username}%"
        query = query.filter(Timesheet.username.ilike(like))
    if from_ is not None:
        query = query.filter(Timesheet.start_time >= from_)
    if to is not None:
        query = query.filter(Timesheet.start_time < to)

    total_items = query.count()
    effective_page_size = pageSize or total_items or 1
    total_pages = (total_items + effective_page_size - 1) // effective_page_size if total_items else 1
    offset = (page - 1) * effective_page_size

    if pageSize is None:
        rows = query.order_by(Timesheet.start_time.desc()).all()
    else:
        rows = (
            query.order_by(Timesheet.start_time.desc())
            .offset(offset)
            .limit(pageSize)
            .all()
        )

    items = [_to_timesheet_entry(r) for r in rows]

    pagination = Pagination(
        items=items,
        page=page,
        pageSize=effective_page_size,
        totalItems=total_items,
        totalPages=total_pages,
    )

    return Envelope(success=True, data=pagination, error=None)


@router.post("/admin/add", response_model=Envelope)
async def admin_add_timesheet(
    payload: AdminAddRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _ensure_admin(current_user)

    # Validate times
    if payload.endTime <= payload.startTime:
        return Envelope(
            success=False,
            data=None,
            error=ErrorDetail(
                code="INVALID_TIME_RANGE",
                message="endTime must be after startTime.",
            ),
        )

    # Ensure user exists
    user_row: Optional[User] = db.query(User).filter(User.id == payload.userId).first()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    # Determine rate
    if payload.rate is not None:
        try:
            rate_dec = func.cast(payload.rate, sa.Numeric(18, 2))  # placeholder; we set directly below
        except Exception:
            rate_dec = None
    else:
        rate_dec = user_row.hourly_rate

    # Compute duration
    delta_sec = (payload.endTime - payload.startTime).total_seconds()
    duration_minutes = int(round(delta_sec / 60.0))

    now = datetime.utcnow()

    ts = Timesheet(
        user_id=user_row.id,
        username=user_row.username,
        start_time=payload.startTime,
        end_time=payload.endTime,
        duration_minutes=duration_minutes,
        rate=rate_dec if payload.rate is not None else user_row.hourly_rate,
        description=payload.description,
        delete_flag=False,
        record_created=now,
        record_created_by=current_user.username,
        record_updated=now,
        record_updated_by=current_user.username,
    )

    db.add(ts)
    db.commit()
    db.refresh(ts)

    return Envelope(success=True, data=_to_timesheet_entry(ts), error=None)


@router.patch("/admin/{timesheet_id}", response_model=Envelope)
async def admin_patch_timesheet(
    timesheet_id: int,
    payload: AdminPatchRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _ensure_admin(current_user)

    ts: Optional[Timesheet] = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        return Envelope(
            success=False,
            data=None,
            error=ErrorDetail(
                code="TIMESHEET_NOT_FOUND",
                message="Timesheet entry not found.",
            ),
        )

    # Apply partial updates
    if payload.startTime is not None:
        ts.start_time = payload.startTime
    if payload.endTime is not None:
        ts.end_time = payload.endTime
    if payload.description is not None:
        ts.description = payload.description
    if payload.rate is not None:
        # Parse rate as decimal-like string; let DB enforce precision
        try:
            ts.rate = func.cast(payload.rate, sa.Numeric(18, 2))  # placeholder
        except Exception:
            ts.rate = ts.rate
    if payload.deleteFlag is not None:
        ts.delete_flag = payload.deleteFlag

    # If either start or end is set, validate
    if ts.start_time is not None and ts.end_time is not None:
        if ts.end_time <= ts.start_time:
            return Envelope(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="INVALID_TIME_RANGE",
                    message="endTime must be after startTime.",
                ),
            )
        delta_sec = (ts.end_time - ts.start_time).total_seconds()
        ts.duration_minutes = int(round(delta_sec / 60.0))

    now = datetime.utcnow()
    ts.record_updated = now
    ts.record_updated_by = current_user.username

    db.commit()
    db.refresh(ts)

    return Envelope(success=True, data=_to_timesheet_entry(ts), error=None)

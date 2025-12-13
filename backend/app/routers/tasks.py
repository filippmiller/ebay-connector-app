from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models_sqlalchemy import get_db
from app.models_sqlalchemy.models import Task, TaskComment, TaskNotification, User as SAUser
from app.services.auth import get_current_active_user
from app.models.user import User as UserModel, UserRole
from app.utils.logger import logger


router = APIRouter()

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
notifications_router = APIRouter(prefix="/api/task-notifications", tags=["task-notifications"])


# ---- Pydantic Schemas ----


class TaskCommentResponse(BaseModel):
    id: str
    task_id: str
    author_id: Optional[str]
    author_name: Optional[str]
    body: str
    kind: str
    created_at: datetime


class TaskBasicResponse(BaseModel):
    id: str
    type: str
    title: str
    description: Optional[str]
    status: str
    priority: str
    due_at: Optional[datetime]
    snooze_until: Optional[datetime]
    is_popup: bool
    is_archived: bool
    is_important: bool
    creator_id: str
    creator_username: Optional[str]
    assignee_id: Optional[str]
    assignee_username: Optional[str]
    comment_count: int
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: List[TaskBasicResponse]
    total: int
    page: int
    page_size: int


class TaskDetailResponse(BaseModel):
    id: str
    type: str
    title: str
    description: Optional[str]
    status: str
    priority: str
    due_at: Optional[datetime]
    snooze_until: Optional[datetime]
    is_popup: bool
    is_archived: bool
    is_important: bool
    creator_id: str
    creator_username: Optional[str]
    assignee_id: Optional[str]
    assignee_username: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    comments: List[TaskCommentResponse]


class TaskCreateRequest(BaseModel):
    type: str  # 'task' or 'reminder'
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    due_at: Optional[datetime] = None
    is_popup: Optional[bool] = True
    priority: Optional[str] = "normal"  # low, normal, high


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    due_at: Optional[datetime] = None
    is_popup: Optional[bool] = None
    priority: Optional[str] = None


class TaskStatusChangeRequest(BaseModel):
    new_status: str
    comment: Optional[str] = None


class TaskCommentCreateRequest(BaseModel):
    body: str


class TaskSnoozeRequest(BaseModel):
    snooze_until: Optional[datetime] = None
    preset: Optional[str] = None  # "15m", "1h", "tomorrow"


class TaskImportantRequest(BaseModel):
    is_important: bool


class TaskNotificationResponse(BaseModel):
    id: str
    task_id: str
    user_id: str
    kind: str
    status: str
    created_at: datetime
    read_at: Optional[datetime]
    dismissed_at: Optional[datetime]
    task: Dict[str, Any]


class TaskNotificationsListResponse(BaseModel):
    items: List[TaskNotificationResponse]


# ---- Helper functions ----


def _is_admin(user: UserModel) -> bool:
    try:
        return user.role == UserRole.ADMIN
    except Exception:  # pragma: no cover - defensive fallback
        return str(getattr(user, "role", "")).lower() == "admin"


def _ensure_can_view(task: Task, current_user: UserModel) -> None:
    if _is_admin(current_user):
        return
    if current_user.id not in {task.creator_id, task.assignee_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this task")


def _ensure_can_modify(task: Task, current_user: UserModel) -> None:
    if _is_admin(current_user):
        return
    if current_user.id not in {task.creator_id, task.assignee_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this task")


def _notify_other_party(db: Session, task: Task, actor_user_id: Optional[str], kind: str) -> None:
    """Create TaskNotification rows for the counterparty (creator vs assignee)."""
    recipients = set()
    if task.creator_id:
        recipients.add(task.creator_id)
    if task.assignee_id:
        recipients.add(task.assignee_id)
    if actor_user_id:
        recipients.discard(actor_user_id)

    for user_id in recipients:
        db.add(
            TaskNotification(
                id=str(uuid.uuid4()),
                task_id=task.id,
                user_id=user_id,
                kind=kind,
                status="unread",
            )
        )


def _status_transition(task: Task, new_status: str, actor: Optional[UserModel]) -> str:
    """Validate and apply a status transition. Returns old_status.

    This encapsulates the allowed transitions for tasks vs reminders.
    """
    new_status = new_status.strip().lower()
    old_status = (task.status or "").lower()

    if task.type == "task":
        allowed_statuses = {"new", "in_progress", "snoozed", "done", "cancelled"}
        allowed_transitions = {
            "new": {"in_progress", "snoozed", "cancelled"},
            "in_progress": {"done", "snoozed", "cancelled"},
            "snoozed": {"in_progress", "done", "cancelled"},
            "done": set(),
            "cancelled": set(),
        }
    else:  # reminder
        allowed_statuses = {"scheduled", "fired", "snoozed", "done", "dismissed"}
        allowed_transitions = {
            "scheduled": {"fired", "done", "dismissed"},
            "fired": {"snoozed", "done", "dismissed"},
            "snoozed": {"fired", "done", "dismissed"},
            "done": set(),
            "dismissed": set(),
        }

    if new_status not in allowed_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status '{new_status}' for {task.type}")

    if old_status and old_status in allowed_transitions and new_status not in allowed_transitions[old_status]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transition from {old_status} to {new_status} is not allowed for {task.type}",
        )

    # Apply status
    task.status = new_status
    now = datetime.now(timezone.utc)
    if new_status == "done":
        task.completed_at = now
    elif old_status == "done" and new_status != "done":
        task.completed_at = None

    return old_status


def _build_user_map(db: Session, user_ids: List[str]) -> Dict[str, SAUser]:
    if not user_ids:
        return {}
    rows = db.query(SAUser).filter(SAUser.id.in_(user_ids)).all()
    return {u.id: u for u in rows}


# ---- Tasks endpoints ----


@tasks_router.get("", response_model=TaskListResponse)
async def list_tasks(
    task_type: Optional[str] = Query(None, alias="type"),
    role: str = Query("assigned_to_me", regex="^(assigned_to_me|created_by_me|all)$"),
    status_filter: Optional[List[str]] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    archived: bool = Query(False, description="When true, return archived tasks instead of active ones"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """List tasks/reminders for the current user.

    Non-admins are restricted to creator/assignee visibility.
    """
    query = db.query(Task).filter(Task.deleted_at.is_(None))

    is_admin = _is_admin(current_user)

    if not is_admin:
        query = query.filter(or_(Task.creator_id == current_user.id, Task.assignee_id == current_user.id))

    if task_type in {"task", "reminder"}:
        query = query.filter(Task.type == task_type)

    if role == "assigned_to_me":
        query = query.filter(Task.assignee_id == current_user.id)
    elif role == "created_by_me":
        query = query.filter(Task.creator_id == current_user.id)
    elif role == "all" and not is_admin:
        # Non-admins cannot see truly global list
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required for role=all")

    if archived:
        query = query.filter(Task.is_archived.is_(True))
    else:
        query = query.filter(Task.is_archived.is_(False))

    if status_filter:
        lowered = [s.lower() for s in status_filter]
        query = query.filter(func.lower(Task.status).in_(lowered))

    if search:
        like = f"%{search}%"
        query = query.filter(or_(Task.title.ilike(like), Task.description.ilike(like)))

    total = query.count()
    offset = (page - 1) * page_size

    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(page_size).all()

    if not tasks:
        return TaskListResponse(items=[], total=0, page=page, page_size=page_size)

    task_ids = [t.id for t in tasks]
    comment_counts_rows = (
        db.query(TaskComment.task_id, func.count(TaskComment.id))
        .filter(TaskComment.task_id.in_(task_ids))
        .group_by(TaskComment.task_id)
        .all()
    )
    comment_counts = {task_id: count for task_id, count in comment_counts_rows}

    user_ids: List[str] = []
    for t in tasks:
        if t.creator_id:
            user_ids.append(t.creator_id)
        if t.assignee_id:
            user_ids.append(t.assignee_id)
    user_map = _build_user_map(db, list({uid for uid in user_ids if uid}))

    items: List[TaskBasicResponse] = []
    for t in tasks:
        items.append(
            TaskBasicResponse(
                id=t.id,
                type=t.type,
                title=t.title,
                description=t.description,
                status=t.status,
                priority=t.priority or "normal",
                due_at=t.due_at,
                snooze_until=t.snooze_until,
                is_popup=bool(t.is_popup),
                is_archived=bool(getattr(t, "is_archived", False)),
                is_important=bool(getattr(t, "is_important", False)),
                creator_id=t.creator_id,
                creator_username=getattr(user_map.get(t.creator_id), "username", None),
                assignee_id=t.assignee_id,
                assignee_username=getattr(user_map.get(t.assignee_id), "username", None),
                comment_count=comment_counts.get(t.id, 0),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
        )

    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@tasks_router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_view(task, current_user)

    comments = (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task.id)
        .order_by(TaskComment.created_at.asc())
        .all()
    )

    author_ids = [c.author_id for c in comments if c.author_id]
    user_map = _build_user_map(db, list({uid for uid in author_ids}))

    creator = db.query(SAUser).filter(SAUser.id == task.creator_id).first() if task.creator_id else None
    assignee = db.query(SAUser).filter(SAUser.id == task.assignee_id).first() if task.assignee_id else None

    comment_items: List[TaskCommentResponse] = []
    for c in comments:
        author_name = None
        if c.author_id and c.author_id in user_map:
            author_name = user_map[c.author_id].username
        elif c.author_id is None:
            author_name = "System"

        comment_items.append(
            TaskCommentResponse(
                id=c.id,
                task_id=c.task_id,
                author_id=c.author_id,
                author_name=author_name,
                body=c.body,
                kind=c.kind,
                created_at=c.created_at,
            )
        )

    return TaskDetailResponse(
        id=task.id,
        type=task.type,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority or "normal",
        due_at=task.due_at,
        snooze_until=task.snooze_until,
        is_popup=bool(task.is_popup),
        is_archived=bool(getattr(task, "is_archived", False)),
        is_important=bool(getattr(task, "is_important", False)),
        creator_id=task.creator_id,
        creator_username=getattr(creator, "username", None),
        assignee_id=task.assignee_id,
        assignee_username=getattr(assignee, "username", None),
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        comments=comment_items,
    )


@tasks_router.post("", response_model=TaskDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreateRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task_type = payload.type.strip().lower()
    if task_type not in {"task", "reminder"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="type must be 'task' or 'reminder'")

    assignee_id = payload.assignee_id
    if task_type == "task" and not assignee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignee_id is required for tasks")

    if task_type == "reminder" and not assignee_id:
        assignee_id = current_user.id

    initial_status = "new" if task_type == "task" else "scheduled"

    task = Task(
        id=str(uuid.uuid4()),
        type=task_type,
        title=payload.title,
        description=payload.description,
        creator_id=current_user.id,
        assignee_id=assignee_id,
        status=initial_status,
        priority=payload.priority or "normal",
        due_at=payload.due_at,
        is_popup=True if payload.is_popup is None else payload.is_popup,
    )

    db.add(task)

    # Initial notification: when assigning a task to someone else
    if task.type == "task" and assignee_id and assignee_id != current_user.id:
        _notify_other_party(db, task, actor_user_id=current_user.id, kind="task_assigned")

    db.commit()
    db.refresh(task)

    # Reuse detail endpoint logic
    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.patch("/{task_id}", response_model=TaskDetailResponse)
async def update_task(
    task_id: str,
    payload: TaskUpdateRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    old_assignee_id = task.assignee_id

    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.due_at is not None:
        task.due_at = payload.due_at
    if payload.is_popup is not None:
        task.is_popup = payload.is_popup
    if payload.priority is not None:
        task.priority = payload.priority

    # Reassignment: restrict to creator or admin
    if payload.assignee_id is not None and payload.assignee_id != old_assignee_id:
        if not (_is_admin(current_user) or current_user.id == task.creator_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only creator or admin can reassign tasks",
            )
        task.assignee_id = payload.assignee_id

    db.commit()

    # Notify new assignee if reassigned
    if payload.assignee_id is not None and payload.assignee_id != old_assignee_id:
        _notify_other_party(db, task, actor_user_id=current_user.id, kind="task_assigned")
        db.commit()

    db.refresh(task)
    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.post("/{task_id}/status", response_model=TaskDetailResponse)
async def change_status(
    task_id: str,
    payload: TaskStatusChangeRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    # Additional restriction: only creator or admin can cancel tasks
    if task.type == "task" and payload.new_status.strip().lower() == "cancelled":
        if not (_is_admin(current_user) or current_user.id == task.creator_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only creator or admin can cancel tasks",
            )

    old_status = task.status or ""
    previous = old_status

    previous = _status_transition(task, payload.new_status, current_user)

    # Status change comment
    actor_name = getattr(current_user, "username", "User") if current_user else "System"
    comment_body = f"Status changed from {previous or 'unknown'} to {task.status} by {actor_name}"
    status_comment = TaskComment(
        id=str(uuid.uuid4()),
        task_id=task.id,
        author_id=current_user.id if current_user else None,
        body=comment_body,
        kind="status_change",
    )
    db.add(status_comment)

    # Optional freeform comment
    if payload.comment:
        db.add(
            TaskComment(
                id=str(uuid.uuid4()),
                task_id=task.id,
                author_id=current_user.id,
                body=payload.comment,
                kind="comment",
            )
        )

    _notify_other_party(db, task, actor_user_id=current_user.id, kind="task_status_changed")

    db.commit()
    db.refresh(task)

    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.post("/{task_id}/comments", response_model=TaskDetailResponse)
async def add_comment(
    task_id: str,
    payload: TaskCommentCreateRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    comment = TaskComment(
        id=str(uuid.uuid4()),
        task_id=task.id,
        author_id=current_user.id,
        body=payload.body,
        kind="comment",
    )
    db.add(comment)

    _notify_other_party(db, task, actor_user_id=current_user.id, kind="task_comment_added")

    db.commit()
    db.refresh(task)

    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.post("/{task_id}/snooze", response_model=TaskDetailResponse)
async def snooze_task(
    task_id: str,
    payload: TaskSnoozeRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    now = datetime.now(timezone.utc)

    snooze_until: Optional[datetime] = payload.snooze_until
    if payload.preset and not snooze_until:
        preset = payload.preset.lower()
        if preset == "15m":
            snooze_until = now + timedelta(minutes=15)
        elif preset == "1h":
            snooze_until = now + timedelta(hours=1)
        elif preset == "tomorrow":
            snooze_until = now + timedelta(days=1)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported snooze preset")

    if not snooze_until:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="snooze_until or preset required")

    # Only active-like states may be snoozed
    inactive_statuses = {"done", "cancelled", "dismissed"}
    if (task.status or "").lower() in inactive_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot snooze completed/cancelled tasks")

    # Apply snooze
    task.status = "snoozed"
    task.snooze_until = snooze_until

    actor_name = getattr(current_user, "username", "User") if current_user else "System"
    human_ts = snooze_until.astimezone(timezone.utc).isoformat()
    snooze_comment = TaskComment(
        id=str(uuid.uuid4()),
        task_id=task.id,
        author_id=current_user.id if current_user else None,
        body=f"Task snoozed until {human_ts} by {actor_name}",
        kind="snooze",
    )
    db.add(snooze_comment)

    _notify_other_party(db, task, actor_user_id=current_user.id, kind="task_status_changed")

    db.commit()
    db.refresh(task)

    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.post("/{task_id}/archive", response_model=TaskDetailResponse)
async def archive_task(
    task_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    task.is_archived = True
    db.commit()
    db.refresh(task)
    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.post("/{task_id}/unarchive", response_model=TaskDetailResponse)
async def unarchive_task(
    task_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    task.is_archived = False
    db.commit()
    db.refresh(task)
    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.post("/{task_id}/important", response_model=TaskDetailResponse)
async def set_task_important(
    task_id: str,
    payload: TaskImportantRequest,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskDetailResponse:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    task.is_important = bool(payload.is_important)
    db.commit()
    db.refresh(task)
    return await get_task(task.id, current_user=current_user, db=db)


@tasks_router.delete("/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
    task_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> dict:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _ensure_can_modify(task, current_user)

    if getattr(task, "is_important", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Important tasks cannot be deleted")

    task.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"deleted": 1}


# ---- Notifications endpoints ----


@notifications_router.get("/unread", response_model=TaskNotificationsListResponse)
async def list_unread_notifications(
    since: Optional[datetime] = Query(None),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TaskNotificationsListResponse:
    query = db.query(TaskNotification).filter(
        TaskNotification.user_id == current_user.id,
        TaskNotification.status == "unread",
    )

    if since is not None:
        query = query.filter(TaskNotification.created_at > since)

    notifications = query.order_by(TaskNotification.created_at.desc()).limit(200).all()

    if not notifications:
        return TaskNotificationsListResponse(items=[])

    task_ids = [n.task_id for n in notifications]
    tasks = db.query(Task).filter(Task.id.in_(task_ids)).all()
    tasks_map = {t.id: t for t in tasks}

    user_ids: List[str] = []
    for t in tasks:
        if t.creator_id:
            user_ids.append(t.creator_id)
        if t.assignee_id:
            user_ids.append(t.assignee_id)
    users_map = _build_user_map(db, list({uid for uid in user_ids if uid}))

    items: List[TaskNotificationResponse] = []
    for n in notifications:
        task = tasks_map.get(n.task_id)
        task_payload: Dict[str, Any] = {
            "id": n.task_id,
        }
        if task:
            task_payload.update(
                {
                    "type": task.type,
                    "title": task.title,
                    "status": task.status,
                    "priority": task.priority or "normal",
                    "due_at": task.due_at,
                    "creator_id": task.creator_id,
                    "creator_username": getattr(users_map.get(task.creator_id), "username", None),
                    "assignee_id": task.assignee_id,
                    "assignee_username": getattr(users_map.get(task.assignee_id), "username", None),
                }
            )

        items.append(
            TaskNotificationResponse(
                id=n.id,
                task_id=n.task_id,
                user_id=n.user_id,
                kind=n.kind,
                status=n.status,
                created_at=n.created_at,
                read_at=n.read_at,
                dismissed_at=n.dismissed_at,
                task=task_payload,
            )
        )

    return TaskNotificationsListResponse(items=items)


@notifications_router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    n = (
        db.query(TaskNotification)
        .filter(TaskNotification.id == notification_id, TaskNotification.user_id == current_user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if n.status != "read":
        n.status = "read"
        n.read_at = datetime.now(timezone.utc)
        db.commit()

    return {"status": "ok"}


@notifications_router.post("/{notification_id}/dismiss")
async def dismiss_notification(
    notification_id: str,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    n = (
        db.query(TaskNotification)
        .filter(TaskNotification.id == notification_id, TaskNotification.user_id == current_user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    n.status = "dismissed"
    n.dismissed_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "ok"}


# Mount sub-routers under a single module-level router
router.include_router(tasks_router)
router.include_router(notifications_router)

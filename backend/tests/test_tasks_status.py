import pytest
from fastapi import HTTPException

from app.routers.tasks import _status_transition


class DummyTask:
  def __init__(self, task_type: str, status: str | None = None):
    self.type = task_type
    self.status = status
    self.completed_at = None


def test_task_status_valid_transitions():
  task = DummyTask('task', 'new')
  prev = _status_transition(task, 'in_progress', actor=None)
  assert prev == 'new'
  assert task.status == 'in_progress'

  prev = _status_transition(task, 'done', actor=None)
  assert prev == 'in_progress'
  assert task.status == 'done'
  assert task.completed_at is not None


def test_task_status_invalid_transition_raises():
  task = DummyTask('task', 'new')
  with pytest.raises(HTTPException):
    _status_transition(task, 'done', actor=None)


def test_reminder_status_transitions():
  task = DummyTask('reminder', 'scheduled')
  prev = _status_transition(task, 'fired', actor=None)
  assert prev == 'scheduled'
  assert task.status == 'fired'

  prev = _status_transition(task, 'snoozed', actor=None)
  assert prev == 'fired'
  assert task.status == 'snoozed'

  prev = _status_transition(task, 'done', actor=None)
  assert prev == 'snoozed'
  assert task.status == 'done'
  assert task.completed_at is not None

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from challsmith_api.models import Challenge, PublishRun


def get(db: Session, run_id: int) -> PublishRun | None:
    return db.get(PublishRun, run_id)


def get_running(db: Session, challenge: Challenge) -> PublishRun | None:
    return db.scalar(select(PublishRun).where(PublishRun.challenge_id == challenge.id, PublishRun.status == "running"))


def add_running(db: Session, challenge: Challenge) -> PublishRun:
    run = PublishRun(challenge_id=challenge.id, status="running", log="")
    db.add(run)
    return run


def append_log(db: Session, run_id: int, line: str) -> None:
    db.execute(update(PublishRun).where(PublishRun.id == run_id).values(log=PublishRun.log + line + "\n"))


def set_status(db: Session, run_id: int, status: str) -> None:
    db.execute(update(PublishRun).where(PublishRun.id == run_id).values(status=status, finished_at=func.now()))


def fail_running(db: Session, note: str) -> None:
    db.execute(update(PublishRun).where(PublishRun.status == "running").values(
        status="failed", finished_at=func.now(), log=PublishRun.log + note))

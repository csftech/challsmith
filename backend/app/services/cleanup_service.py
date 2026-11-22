from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.repositories import publish_run_repository, setting_repository
from app.services import auth_service, image_cleanup_service
from app.services.errors import BadGateway, Conflict

CONFIRM = "CLEANUP"
GATE = 0x636C6E  # advisory lock shared by publish start and cleanup start
MARK = "cleanup_running"
STALE = timedelta(hours=1)  # a mark older than this is from a killed cleanup, not a running one
BUSY = "a publish is running; wait for it to finish before the cleanup (it would delete the new image)"


def refuse_if_publishing(db: Session) -> None:
    if publish_run_repository.any_running(db):
        raise Conflict(BUSY)


def cleanup_running(db: Session) -> bool:
    """Call with the GATE lock held (lock_gate) for a race-free answer."""
    mark = setting_repository.get(db, MARK)
    return bool(mark) and datetime.now(UTC) - datetime.fromisoformat(mark["since"]) < STALE


def lock_gate(db: Session) -> None:
    setting_repository.lock_key(db, GATE)


def _begin(db: Session) -> None:
    lock_gate(db)
    refuse_if_publishing(db)
    if cleanup_running(db):
        db.rollback()
        raise Conflict("another cleanup is running")
    setting_repository.put(db, MARK, {"since": datetime.now(UTC).isoformat()})
    db.commit()


def _end(db: Session) -> None:
    db.rollback()
    setting_repository.delete(db, MARK)
    db.commit()


def reset_instances(cm, docker, log) -> tuple[int, int, int]:
    """Delete every chall-manager instance, then remove leftover challenge-* containers and networks."""
    instances = cm.list_instances()
    for cid, sid in instances:
        cm.delete_instance(cid, sid)
    log(f"deleted {len(instances)} instances")
    containers = docker.remove_containers("challenge-", log)
    networks = docker.remove_networks("challenge-", log)
    log(f"removed {containers} containers, {networks} networks")
    return len(instances), containers, networks


def run_cleanup(db: Session, cm, ctfd, docker, registry, log) -> dict:
    """Instances, leftover scenario containers/networks, trainee users, web sessions, then unused images;
    stops at the first failure. Refused while a publish runs; publishes are refused while it runs."""
    try:
        _begin(db)
    except Conflict:
        db.rollback()
        raise
    try:
        return _run(db, cm, ctfd, docker, registry, log)
    finally:
        _end(db)


def _run(db: Session, cm, ctfd, docker, registry, log) -> dict:
    try:
        instances, containers, networks = reset_instances(cm, docker, log)
        trainees = [u["id"] for u in ctfd.list_users() if ctfd.get_user(u["id"])["type"] != "admin"]
        for uid in trainees:
            ctfd.delete_user(uid)
        log(f"deleted {len(trainees)} CTFd users")
    except Exception as e:
        log(f"failed: {e}")
        raise BadGateway(f"cleanup stopped: {e}")
    sessions = auth_service.clear_sessions(db)
    log(f"cleared {sessions} web sessions")
    refuse_if_publishing(db)  # cannot happen while the mark is set; checked again because deleting is final
    try:
        # planned only now: the instance containers are gone, so their images no longer count as in use
        images = image_cleanup_service.execute(image_cleanup_service.plan(docker, registry, ctfd, log), docker, registry, log)
        log(f"removed {images['images']} images and {images['registry_tags']} registry tags")
    except Exception as e:
        log(f"failed: {e}")
        raise BadGateway(f"cleanup stopped at unused images: {e}")
    return {"instances": instances, "containers": containers, "networks": networks, "users": len(trainees),
            "sessions": sessions, **images}

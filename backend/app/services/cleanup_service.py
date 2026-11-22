from sqlalchemy.orm import Session

from app.services import auth_service, image_cleanup_service
from app.services.errors import BadGateway

CONFIRM = "CLEANUP"


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
    stops at the first failure."""
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
    try:
        # planned only now: the instance containers are gone, so their images no longer count as in use
        images = image_cleanup_service.execute(image_cleanup_service.plan(docker, registry, ctfd, log), docker, registry, log)
        log(f"removed {images['images']} images and {images['registry_tags']} registry tags")
    except Exception as e:
        log(f"failed: {e}")
        raise BadGateway(f"cleanup stopped at unused images: {e}")
    return {"instances": instances, "containers": containers, "networks": networks, "users": len(trainees),
            "sessions": sessions, **images}

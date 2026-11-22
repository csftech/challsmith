from sqlalchemy.orm import Session

from app.services import auth_service
from app.services.errors import BadGateway

CONFIRM = "CLEANUP"


def run_cleanup(db: Session, cm, ctfd, docker, log) -> dict:
    """Instances, leftover scenario containers/networks, trainee users, then web sessions; stops at the first failure."""
    try:
        instances = cm.list_instances()
        for cid, sid in instances:
            cm.delete_instance(cid, sid)
        log(f"deleted {len(instances)} instances")
        containers = docker.remove_containers("challenge-", log)
        networks = docker.remove_networks("challenge-", log)
        log(f"removed {containers} containers, {networks} networks")
        trainees = [u["id"] for u in ctfd.list_users() if u["type"] != "admin"]
        for uid in trainees:
            ctfd.delete_user(uid)
        log(f"deleted {len(trainees)} CTFd users")
    except Exception as e:
        log(f"failed: {e}")
        raise BadGateway(f"cleanup stopped: {e}")
    sessions = auth_service.clear_sessions(db)
    log(f"cleared {sessions} web sessions")
    return {"instances": len(instances), "containers": containers, "networks": networks, "users": len(trainees), "sessions": sessions}

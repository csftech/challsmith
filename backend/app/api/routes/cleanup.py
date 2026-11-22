from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.core.db import get_session
from app.schemas.cleanup_schema import CleanupBody
from app.services import cleanup_service
from app.services.errors import BadRequest

router = APIRouter()


@router.post("/cleanup")
def cleanup(
    body: CleanupBody,
    db: Session = Depends(get_session),
    cm=Depends(deps.get_chall_manager),
    ctfd=Depends(deps.get_ctfd_client),
    docker=Depends(deps.get_docker_ops),
):
    if body.confirm != cleanup_service.CONFIRM:
        raise BadRequest(f'confirm must be "{cleanup_service.CONFIRM}"')
    return cleanup_service.run_cleanup(db, cm, ctfd, docker, lambda _: None)

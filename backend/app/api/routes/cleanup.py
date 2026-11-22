from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.core.db import get_session
from app.schemas.cleanup_schema import CleanupBody
from app.services import cleanup_service, image_cleanup_service
from app.services.errors import BadGateway, BadRequest

router = APIRouter()


@router.post("/cleanup")
def cleanup(
    body: CleanupBody,
    db: Session = Depends(get_session),
    cm=Depends(deps.get_chall_manager),
    ctfd=Depends(deps.get_ctfd_client),
    docker=Depends(deps.get_docker_ops),
    registry=Depends(deps.get_registry_client),
):
    if body.confirm != cleanup_service.CONFIRM:
        raise BadRequest(f'confirm must be "{cleanup_service.CONFIRM}"', code="confirm_mismatch")
    return cleanup_service.run_cleanup(db, cm, ctfd, docker, registry, lambda _: None)


@router.get("/cleanup/images")
def image_plan(
    db: Session = Depends(get_session),
    ctfd=Depends(deps.get_ctfd_client),
    docker=Depends(deps.get_docker_ops),
    registry=Depends(deps.get_registry_client),
):
    cleanup_service.refuse_if_publishing(db)
    try:
        return asdict(image_cleanup_service.plan(docker, registry, ctfd, lambda _: None))
    except Exception as e:
        raise BadGateway(f"could not plan the image cleanup: {e}", code="cleanup_plan_failed")

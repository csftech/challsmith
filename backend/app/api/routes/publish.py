from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.clients import ctfd_client, docker_client
from app.core.db import get_engine, get_session
from app.api.deps import get_ctfd_client, get_docker_ops
from app.services import publish_service

router = APIRouter()


@router.post("/challenges/{slug}/publish")
def publish(
    slug: str,
    tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    docker: docker_client.DockerOps = Depends(get_docker_ops),
    ctfd: ctfd_client.CtfdClient = Depends(get_ctfd_client),
):
    run_id = publish_service.start_run(db, slug)
    tasks.add_task(publish_service.run_publish, lambda: Session(get_engine()), run_id, slug, docker, ctfd)
    return {"run_id": run_id}


@router.get("/publish-runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_session)):
    return publish_service.get_run(db, run_id)

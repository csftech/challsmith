from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .core.db import get_engine
from .core.deps import require_session
from .routers import auth, challenges, publish, sync, templates
from .services import publish_service
from .services.errors import DomainError


@asynccontextmanager
async def lifespan(_):
    with Session(get_engine()) as db:
        publish_service.fail_interrupted(db)
    yield


app = FastAPI(title="challsmith", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.exception_handler(DomainError)
def domain_error(_, e: DomainError):
    headers = {"WWW-Authenticate": "Bearer"} if e.status == 401 else None
    return JSONResponse({"detail": e.detail}, status_code=e.status, headers=headers)


app.include_router(auth.public)
# Every later router must be mounted with dependencies=[Depends(require_session)].
app.include_router(auth.router)
app.include_router(templates.router, dependencies=[Depends(require_session)])
app.include_router(challenges.router, dependencies=[Depends(require_session)])
app.include_router(publish.router, dependencies=[Depends(require_session)])
app.include_router(sync.router, dependencies=[Depends(require_session)])


@app.get("/health")
def health():
    return {"ok": True}

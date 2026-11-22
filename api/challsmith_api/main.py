from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from .core.deps import require_session
from .routers import auth, challenges, templates
from .services.errors import DomainError

app = FastAPI(title="challsmith", docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(DomainError)
def domain_error(_, e: DomainError):
    headers = {"WWW-Authenticate": "Bearer"} if e.status == 401 else None
    return JSONResponse({"detail": e.detail}, status_code=e.status, headers=headers)


app.include_router(auth.public)
# Every later router must be mounted with dependencies=[Depends(require_session)].
app.include_router(auth.router)
app.include_router(templates.router, dependencies=[Depends(require_session)])
app.include_router(challenges.router, dependencies=[Depends(require_session)])


@app.get("/health")
def health():
    return {"ok": True}

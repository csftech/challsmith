from fastapi import Depends, FastAPI

from .core.deps import require_session
from .routers import auth, challenges, templates

app = FastAPI(title="challsmith", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.public)
# Every later router must be mounted with dependencies=[Depends(require_session)].
app.include_router(auth.router)
app.include_router(templates.router, dependencies=[Depends(require_session)])
app.include_router(challenges.router, dependencies=[Depends(require_session)])


@app.get("/health")
def health():
    return {"ok": True}

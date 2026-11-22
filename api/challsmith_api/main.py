from fastapi import Depends, FastAPI

from . import auth, routes_templates

app = FastAPI(title="challsmith", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.public)
# Every later router must be mounted with dependencies=[Depends(auth.require_session)].
app.include_router(auth.router)
app.include_router(routes_templates.router, dependencies=[Depends(auth.require_session)])


@app.get("/health")
def health():
    return {"ok": True}

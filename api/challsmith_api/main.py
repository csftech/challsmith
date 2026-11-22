from fastapi import FastAPI

from . import auth

app = FastAPI(title="challsmith", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.public)
# Every later router must be mounted with dependencies=[Depends(auth.require_session)].
app.include_router(auth.router)


@app.get("/health")
def health():
    return {"ok": True}

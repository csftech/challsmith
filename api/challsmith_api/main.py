from fastapi import FastAPI

app = FastAPI(title="challsmith")


@app.get("/health")
def health():
    return {"ok": True}

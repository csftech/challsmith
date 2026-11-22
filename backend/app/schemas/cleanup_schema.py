from pydantic import BaseModel


class CleanupBody(BaseModel):
    confirm: str

from typing import Literal

from pydantic import BaseModel


class GitSettings(BaseModel):
    remote_url: str
    username: str = ""
    token: str | None = None
    branch: str = "main"
    dir: str = "challenges"
    author_name: str = "challsmith"
    author_email: str = "challsmith@localhost"


class ExportBody(BaseModel):
    push: bool = True


class ApplyBody(BaseModel):
    preview_id: str
    decisions: dict[str, Literal["source", "db"]] = {}

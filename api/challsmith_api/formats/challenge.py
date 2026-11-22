import posixpath
import re
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SERVICE_RE = re.compile(r"^[a-z0-9-]+$")
MEMORY_RE = re.compile(r"^\d+[mg]$")


class ServiceSpec(BaseModel):
    name: str
    port: int | None = None
    entry: bool = False
    image: str | None = None
    env: dict[str, str] = {}

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not SERVICE_RE.fullmatch(v):
            raise ValueError(f"service name {v!r} must match {SERVICE_RE.pattern}")
        return v


class InstanceSpec(BaseModel):
    timeout: int = Field(3600, gt=0)
    mana: int = Field(1, gt=0)
    memory: str = "256m"
    cpus: str = "0.5"

    @field_validator("memory")
    @classmethod
    def _memory(cls, v: str) -> str:
        if not MEMORY_RE.fullmatch(v):
            raise ValueError(f"memory {v!r} must match {MEMORY_RE.pattern}")
        return v


class ChallengeMeta(BaseModel):
    # field order is the output order of challenge.yml
    slug: str
    name: str
    category: str
    tags: list[str] = []
    description: str = ""
    value: int = Field(gt=0)
    template: str | None = None
    scenario: Literal["single", "multi"]
    flag: str
    flag_prefix: str = "CTF"
    protocol: Literal["http", "tcp"] = "http"
    instance: InstanceSpec = InstanceSpec()
    services: list[ServiceSpec]
    visible: bool = True

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.fullmatch(v):
            raise ValueError(f"slug {v!r} must match {SLUG_RE.pattern}")
        return v

    @model_validator(mode="after")
    def _services(self):
        names = [s.name for s in self.services]
        if len(set(names)) != len(names):
            raise ValueError("services: names must be unique")
        entries = [s for s in self.services if s.entry]
        if len(entries) != 1 or entries[0].port is None:
            raise ValueError("services: exactly one entry service with a port is required")
        if self.scenario == "single" and (len(self.services) != 1 or self.services[0].image):
            raise ValueError("services: single scenario needs exactly one service built from a folder")
        return self


def dump_challenge_yml(meta: ChallengeMeta) -> bytes:
    d = meta.model_dump(mode="json")
    if d["template"] is None:
        del d["template"]
    for s in d["services"]:
        for key in ("port", "image"):
            if s[key] is None:
                del s[key]
        if not s["env"]:
            del s["env"]
    return yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=False).encode()


def parse_challenge_yml(data: bytes) -> ChallengeMeta:
    try:
        raw = yaml.safe_load(data)
    except yaml.YAMLError as e:
        raise ValueError(f"challenge.yml: invalid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError("challenge.yml: top level must be a mapping")
    return ChallengeMeta.model_validate(raw)


def safe_relpath(path: str) -> str:
    if not path or "\\" in path or "\0" in path or path.startswith("/"):
        raise ValueError(f"unsafe path: {path!r}")
    if ".." in path.split("/"):
        raise ValueError(f"unsafe path: {path!r}")
    norm = posixpath.normpath(path)
    if norm == ".":
        raise ValueError(f"unsafe path: {path!r}")
    return norm


def to_folder(meta: ChallengeMeta, files: dict[str, bytes]) -> dict[str, bytes]:
    folder = {safe_relpath(p): b for p, b in files.items()}
    if "challenge.yml" in folder:
        raise ValueError("files must not contain challenge.yml")
    folder["challenge.yml"] = dump_challenge_yml(meta)
    return folder


def from_folder(folder: dict[str, bytes]) -> tuple[ChallengeMeta, dict[str, bytes]]:
    if "challenge.yml" not in folder:
        raise ValueError("challenge.yml is missing")
    meta = parse_challenge_yml(folder["challenge.yml"])
    return meta, {safe_relpath(p): b for p, b in folder.items() if p != "challenge.yml"}

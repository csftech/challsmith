from pathlib import Path

import yaml
from pydantic import BaseModel

from challsmith_api.formats import challenge_format
from challsmith_api.core.config import get_settings


class TemplateInfo(BaseModel):
    name: str
    description: str
    scenario: str


def _dir(name: str) -> Path:
    root = Path(get_settings().templates_dir)
    path = root / name
    # name comes from the request: only real child directories of the templates dir count
    if name not in {p.name for p in root.iterdir()} or not (path / "template.yml").is_file():
        raise KeyError(name)
    return path


def _spec(path: Path) -> dict:
    return yaml.safe_load((path / "template.yml").read_text(encoding="utf-8"))


def list_templates() -> list[TemplateInfo]:
    root = Path(get_settings().templates_dir)
    return [
        TemplateInfo(name=p.name, description=s["description"], scenario=s["scenario"])
        for p in sorted(root.iterdir())
        if (p / "template.yml").is_file()
        for s in [_spec(p)]
    ]


def instantiate(name: str, slug: str, title: str) -> tuple[challenge_format.ChallengeMeta, dict[str, bytes]]:
    path = _dir(name)
    spec = _spec(path)
    meta = challenge_format.ChallengeMeta(
        slug=slug,
        name=title,
        category=spec.get("category", "Web"),
        value=100,
        template=name,
        scenario=spec["scenario"],
        flag=slug.replace("-", "_"),
        flag_prefix=spec.get("flag_prefix", "CTF"),
        protocol=spec.get("protocol", "http"),
        instance=challenge_format.InstanceSpec(**spec.get("instance", {})),
        services=[challenge_format.ServiceSpec(**s) for s in spec["services"]],
    )
    files = {
        "services/" + f.relative_to(path).as_posix(): f.read_bytes()
        for f in sorted(path.rglob("*"))
        if f.is_file() and f.relative_to(path).as_posix() != "template.yml"
    }
    return meta, files

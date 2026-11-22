import pytest

from challsmith_api.services import templates
from challsmith_api.formats.challenge import from_folder, to_folder
from test_auth import admin_env, bearer, login  # noqa: F401  (fixture reused)

NAMES = {"php", "python-flask", "node-nextjs", "nginx-php-db", "tcp"}


def test_lists_all_templates():
    infos = templates.list_templates()
    assert {t.name for t in infos} == NAMES
    assert all(t.description and t.scenario in ("single", "multi") for t in infos)


@pytest.mark.parametrize("name", sorted(NAMES))
def test_instantiate_roundtrip(name):
    meta, files = templates.instantiate(name, "my-chall", "My Chall")
    assert (meta.slug, meta.name, meta.template, meta.value) == ("my-chall", "My Chall", name, 100)
    assert (meta.flag, meta.tags, meta.description) == ("my_chall", [], "")
    assert meta.category == ("Pwn" if name == "tcp" else "Web")
    assert "template.yml" not in files
    for s in meta.services:
        if not s.image:
            assert f"services/{s.name}/Dockerfile" in files
    assert from_folder(to_folder(meta, files)) == (meta, files)


def test_unknown_template():
    with pytest.raises(KeyError):
        templates.instantiate("nope", "x", "X")


def test_route(client, db):
    token = login(client).json()["token"]
    r = client.get("/templates", headers=bearer(token))
    assert r.status_code == 200
    assert {t["name"] for t in r.json()} == NAMES


@pytest.mark.parametrize("name", ["..", "php/../php", ".", "", "/etc"])
def test_instantiate_rejects_path_tricks(name):
    with pytest.raises(KeyError):
        templates.instantiate(name, "x", "X")

import pytest

from challsmith_api.challenge_format import (
    ChallengeMeta, dump_challenge_yml, from_folder, parse_challenge_yml, safe_relpath, to_folder,
)

SPEC = """\
slug: php-strcmp
name: strcmp 的陷阱
category: Web
tags: [php, type-juggling]
description: |
  （Markdown）
value: 100
template: php
scenario: single          # single 或 multi
flag: php_strcmp_array
instance:
  timeout: 3600           # 秒，instance 存活時間
  mana: 1
services:
  - name: app
    port: 80
    entry: true
visible: true
""".encode()


def test_yaml_roundtrip():
    meta = parse_challenge_yml(SPEC)
    out = dump_challenge_yml(meta)
    assert parse_challenge_yml(out) == meta
    assert dump_challenge_yml(meta) == out
    assert b"flag_prefix: CTF" in out and b"memory: 256m" in out


def _svc(**kw):
    return {"name": "app", "port": 80, **kw}


@pytest.mark.parametrize("patch", [
    {"slug": "Bad_Slug"},
    {"scenario": "multi", "services": [_svc(entry=True), _svc(name="b", entry=True)]},
    {"scenario": "multi", "services": [_svc(entry=True, port=None)]},
    {"services": [_svc(entry=True), _svc(name="b")]},
    {"instance": {"memory": "256"}},
    {"slug": "abc\n"},
    {"instance": {"memory": "256m\n"}},
])
def test_validation_errors(patch):
    meta = parse_challenge_yml(SPEC).model_dump(mode="json") | patch
    with pytest.raises(ValueError):
        ChallengeMeta.model_validate(meta)


@pytest.mark.parametrize("p", ["../x", "/etc/passwd", "a/../../b", "a\\b", ""])
def test_safe_relpath_rejects(p):
    with pytest.raises(ValueError):
        safe_relpath(p)


def test_safe_relpath_normalizes():
    assert safe_relpath("services/app/./index.php") == "services/app/index.php"


def test_folder_roundtrip_and_missing_yml():
    meta = parse_challenge_yml(SPEC)
    folder = to_folder(meta, {"services/app/index.php": b"x"})
    assert from_folder(folder) == (meta, {"services/app/index.php": b"x"})
    with pytest.raises(ValueError):
        from_folder({"a": b""})

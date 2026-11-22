from app.schemas import challenge_schema
from app.utils import hash_util

from test_challenge_format import SPEC

META = challenge_schema.parse_challenge_yml(SPEC)

OTHER = """\
visible: true
services:
    - {entry: true, port: 80, name: app}
flag: php_strcmp_array
scenario: single
template: php
value: 100
description: "（Markdown）\\n"
tags:
    - php
    - type-juggling
category: Web
name: "strcmp 的陷阱"
instance: {mana: 1, timeout: 3600}
slug: php-strcmp
""".encode()


def test_hash_ignores_crlf():
    assert hash_util.content_hash(META, {"a": b"a\r\nb"}) == hash_util.content_hash(META, {"a": b"a\nb"})
    assert hash_util.content_hash(META, {"a": b"a\r\n\0"}) != hash_util.content_hash(META, {"a": b"a\n\0"})


def test_hash_changes_with_meta():
    assert hash_util.content_hash(META, {}) != hash_util.content_hash(META.model_copy(update={"value": 200}), {})


def test_hash_ignores_yaml_formatting():
    a, b = challenge_schema.from_folder({"challenge.yml": SPEC}), challenge_schema.from_folder({"challenge.yml": OTHER})
    assert a[0] == b[0]
    assert hash_util.content_hash(*a) == hash_util.content_hash(*b)


def test_service_hash_scoped():
    f = {"services/app/x": b"1", "services/db/x": b"1"}
    assert hash_util.service_hash(f, "app") == hash_util.service_hash({**f, "services/db/x": b"2"}, "app")
    assert hash_util.service_hash(f, "app") != hash_util.service_hash({**f, "services/app/x": b"2"}, "app")


def test_service_hash_is_blake3():
    from blake3 import blake3

    body = b"hi"
    expected = blake3(b"\0F\0services/a/x\0" + b"2\0" + body).hexdigest()
    assert hash_util.service_hash({"services/a/x": body}, "a") == expected
    assert len(expected) == 64

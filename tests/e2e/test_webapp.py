"""The authoring web app against the real stack: everything goes through the BFF on :3000."""
import re

import requests
from conftest import (CTFD, WEB, check, ctfd_challenge, get_until, put_file, publish, start_instance,
                      submit, web_login)

DOCKERFILE = "services/app/Dockerfile"


def flag_of(url):
    return re.search(r"CTF\{[^}]*\}", get_until(url + "/", "CTF{")).group(0)


def published(web, admin, slug):
    status, log = publish(web, slug)
    assert status == "succeeded", log
    return ctfd_challenge(admin, slug)


def test_single_template_publish(web, admin, new_challenge, register_user):
    slug = new_challenge("php")
    put_file(web, slug, "services/app/index.php", "<?php readfile('/flag.txt');")
    cid = published(web, admin, slug)["id"]
    alice, bob = register_user("alice"), register_user("bob")
    flag_a, flag_b = flag_of(start_instance(alice, cid)), flag_of(start_instance(bob, cid))
    assert flag_a != flag_b
    assert submit(alice, cid, flag_a) == "correct"
    assert submit(bob, cid, flag_a) == "incorrect"


def test_multi_template_publish(web, admin, new_challenge, register_user):
    slug = new_challenge("nginx-php-db")
    put_file(web, slug, "services/php/index.php", "<?php echo getenv('FLAG');")
    cid = published(web, admin, slug)["id"]
    user = register_user("carol")
    assert submit(user, cid, flag_of(start_instance(user, cid))) == "correct"
    catalog = requests.get("http://127.0.0.1:5000/v2/_catalog", timeout=30).json()["repositories"]
    assert "challsmith/mirror/mariadb" in catalog


def test_republish_updates_same_challenge(web, admin, new_challenge):
    slug = new_challenge("php")
    first = published(web, admin, slug)
    meta = check(web.get(f"{WEB}/api/challenges/{slug}"))["meta"]
    new_value = first["value"] + 37
    check(web.put(f"{WEB}/api/challenges/{slug}", json={**meta, "value": new_value}))
    assert check(web.get(f"{WEB}/api/challenges/{slug}"))["status"]["publish"] == "modified"
    second = published(web, admin, slug)
    assert second["id"] == first["id"]  # PATCH, not a new challenge
    assert second["value"] == new_value
    assert check(web.get(f"{WEB}/api/challenges/{slug}"))["status"]["publish"] == "published"


def test_publish_failure_keeps_ctfd(web, admin, new_challenge):
    slug = new_challenge("php")
    before = published(web, admin, slug)
    assert before["additional"]
    put_file(web, slug, DOCKERFILE, "FROM scratch\nRUN false\n")
    status, log = publish(web, slug)
    assert status == "failed"
    assert "docker" in log.lower() and "false" in log, log
    after = ctfd_challenge(admin, slug)
    assert after["id"] == before["id"] and after["additional"] == before["additional"]


def test_requires_login():
    assert requests.get(WEB + "/api/challenges").status_code == 401
    s = web_login()
    r = s.post(WEB + "/api/challenges", json={"slug": "x", "template": "php", "name": "x"},
               headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_backup_roundtrip(web, new_challenge):
    new_challenge("php")
    r = web.get(f"{WEB}/api/backup")
    assert r.ok and r.content
    items = check(web.post(f"{WEB}/api/sync/archive/preview", files={"file": ("b.tar.gz", r.content)}))["items"]
    assert items and all(i["status"] == "unchanged" for i in items), items

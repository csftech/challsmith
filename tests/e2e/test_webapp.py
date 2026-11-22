"""The authoring web app against the real stack: everything goes through the BFF on :3000."""
import re
import secrets

import requests
from conftest import (CTFD, WEB, check, ctfd_challenge, get_until, put_file, publish, start_instance,
                      submit, web_login)

DOCKERFILE = "services/app/Dockerfile"


def flag_of(url):
    return re.search(r"APS\{[^}]*\}", get_until(url + "/", "APS{")).group(0)


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
    cid = published(web, admin, slug)["id"]
    # the template's own files must be readable by php-fpm (build-context modes), before we replace any
    get_until(start_instance(register_user("dave"), cid) + "/", "Replace this page")
    put_file(web, slug, "services/php/index.php", "<?php echo getenv('FLAG');")
    assert published(web, admin, slug)["id"] == cid
    user = register_user("carol")
    assert submit(user, cid, flag_of(start_instance(user, cid))) == "correct"
    # ask the repo directly: the catalog is paged and keeps emptied repos, so it can grow past one page
    tags = requests.get("http://127.0.0.1:5000/v2/challsmith/mirror/mariadb/tags/list", timeout=30).json()["tags"]
    assert "11" in tags


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


def _categorised(web, new_challenge, category):
    slug = new_challenge("php")
    meta = check(web.get(f"{WEB}/api/challenges/{slug}"))["meta"]
    check(web.put(f"{WEB}/api/challenges/{slug}", json={**meta, "category": category}))
    return slug


def _order(web):
    return [i["slug"] for i in check(web.get(f"{WEB}/api/challenges"))["items"]]


def _public_names(user):
    return [c["name"] for c in check(user.get(CTFD + "/api/v1/challenges"))["data"]]


def _save_order(web, order):
    assert check(web.put(f"{WEB}/api/challenges/order", json={"order": order})) == {"ok": True}


def test_reorder_syncs_to_ctfd(web, admin, new_challenge, register_user):
    cat_a, cat_b = f"e2e-a-{secrets.token_hex(3)}", f"e2e-b-{secrets.token_hex(3)}"
    one, two = _categorised(web, new_challenge, cat_a), _categorised(web, new_challenge, cat_a)
    for slug in (one, two):
        published(web, admin, slug)
    user = register_user("order")
    order = _order(web)
    assert order.index(one) < order.index(two)

    swapped = list(order)
    i, j = swapped.index(one), swapped.index(two)
    swapped[i], swapped[j] = two, one
    _save_order(web, swapped)
    assert _order(web) == swapped
    for slug in (one, two):  # CTFd's admin view agrees with the web app's order
        assert ctfd_challenge(admin, slug)["position"] == swapped.index(slug) + 1
    names = _public_names(user)
    assert names.index(two) < names.index(one)

    third = _categorised(web, new_challenge, cat_b)
    published(web, admin, third)
    order = _order(web)
    assert order[-1] == third  # a new challenge goes last
    front = [s for s in order if s == third] + [s for s in order if s != third]
    _save_order(web, front)
    assert _public_names(user)[0] == third

import pytest

from app.repositories import challenge_repository
from app.services import challenge_service, order_service
from app.services.errors import BadRequest
from test_challenges import api, make  # noqa: F401  (fixture reused)
from test_auth import admin_env  # noqa: F401

R = order_service.Row
P = order_service.CtfdPos


def test_reconcile_follows_ctfd():
    rows = [R("a", "web", 1), R("b", "web", 2), R("d", "web", None)]
    assert order_service.reconcile(rows, {1: P(2, 100), 2: P(1, 100)}) == ["b", "a", "d"]


def test_reconcile_keeps_draft_slots():
    rows = [R("a", "web", 1), R("d", "web", None), R("b", "web", 2)]
    assert order_service.reconcile(rows, {1: P(2, 0), 2: P(1, 0)}) == ["b", "d", "a"]


def test_reconcile_zero_positions_by_value():
    rows = [R("a", "web", 1), R("b", "web", 2), R("c", "web", 3), R("d", "web", 4)]
    ctfd = {1: P(0, 300), 2: P(0, 100), 3: P(0, 200), 4: P(0, 100)}
    assert order_service.reconcile(rows, ctfd) == ["b", "d", "c", "a"]


def test_reconcile_regroups_split_category():
    rows = [R("a", "web", 1), R("x", "pwn", 2), R("b", "web", 3)]
    ctfd = {1: P(1, 0), 2: P(2, 0), 3: P(3, 0)}
    assert order_service.reconcile(rows, ctfd) == ["a", "b", "x"]


def test_reconcile_missing_ctfd_id_is_draft():
    rows = [R("a", "web", 9), R("b", "web", 2), R("c", "web", 3)]
    assert order_service.reconcile(rows, {2: P(2, 0), 3: P(1, 0)}) == ["a", "c", "b"]


def test_reconcile_empty_category_is_a_group():
    rows = [R("a", "", None), R("b", "web", None), R("c", "", None)]
    assert order_service.reconcile(rows, {}) == ["a", "c", "b"]


def test_validate_order():
    rows = [R("a", "web", 1), R("x", "pwn", 2), R("b", "web", 3)]
    order_service.validate_order(["a", "b", "x"], rows)
    for bad in (["a", "b"], ["a", "b", "x", "z"], ["a", "b", "b"]):
        with pytest.raises(BadRequest) as e:
            order_service.validate_order(bad, rows)
        assert e.value.code == "order_mismatch"
    with pytest.raises(BadRequest) as e:
        order_service.validate_order(["a", "x", "b"], rows)
    assert e.value.code == "order_category_split"


def test_move_to_category_end():
    rows = [R("a", "web", 1), R("x", "pwn", 2), R("b", "web", 3), R("y", "pwn", 4)]
    assert order_service.move_to_category_end(rows, "a", "pwn") == ["x", "b", "y", "a"]
    assert order_service.move_to_category_end(rows, "x", "new") == ["a", "b", "y", "x"]


def test_new_challenge_goes_last(api, db):
    assert make(api, "one").status_code == 200
    assert make(api, "two").status_code == 200
    rows = challenge_repository.list_all(db)
    assert [(c.slug, c.position) for c in rows] == [("one", 1), ("two", 2)]


def test_order_slug_reserved(api):
    r = make(api, "order")
    assert r.status_code == 400 and r.json()["code"] == "slug_reserved"

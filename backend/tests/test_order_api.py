import pytest
from sqlalchemy import select

from app.api import deps
from app.clients import ctfd_client
from app.main import app
from app.models import Challenge
from app.repositories import challenge_repository
from app.services import challenge_service
from test_auth import admin_env, bearer, login  # noqa: F401  (fixture reused)


class FakeCtfd:
    def __init__(self, positions=None, down=False, fail_ids=()):
        self.positions, self.down, self.fail_ids, self.set = positions or {}, down, set(fail_ids), []

    def list_positions(self):
        if self.down:
            raise ctfd_client.CtfdError("down")
        return self.positions

    def set_position(self, cid, position):
        if cid in self.fail_ids:
            raise ctfd_client.CtfdError("boom")
        self.set.append((cid, position))


@pytest.fixture
def api(client, db):
    client.headers.update(bearer(login(client).json()["token"]))
    yield client
    app.dependency_overrides.clear()


def use(ctfd):
    app.dependency_overrides[deps.get_ctfd_client] = lambda: ctfd


def seed(api, db, *slugs, published=True):
    for i, s in enumerate(slugs, 1):
        api.post("/challenges", json={"slug": s, "template": "php", "name": s})
        if published:
            db.execute(Challenge.__table__.update().where(Challenge.slug == s).values(ctfd_id=i * 10))
    db.commit()


def slugs(api):
    return [i["slug"] for i in api.get("/challenges").json()["items"]]


def positions(db):
    db.expire_all()
    return {c.slug: c.position for c in challenge_repository.list_all(db)}


def stamps(db):
    db.expire_all()
    return {c.slug: c.updated_at for c in challenge_repository.list_all(db)}


def test_list_reorders_by_ctfd(api, db):
    seed(api, db, "a", "b")
    before = stamps(db)
    use(FakeCtfd({10: (2, 100), 20: (1, 100)}))
    assert slugs(api) == ["b", "a"]
    assert positions(db) == {"b": 1, "a": 2}
    assert stamps(db) == before  # a reorder is not an edit


def test_list_ignores_foreign_ctfd_challenges(api, db):
    seed(api, db, "a")
    use(FakeCtfd({10: (1, 100), 99: (2, 100)}))
    r = api.get("/challenges")
    assert r.status_code == 200 and slugs(api) == ["a"]


def test_list_ctfd_down(api, db):
    seed(api, db, "a", "b")
    use(FakeCtfd({10: (2, 100), 20: (1, 100)}, down=True))
    r = api.get("/challenges").json()
    assert r["ctfd_ok"] is False and [i["slug"] for i in r["items"]] == ["a", "b"]
    assert positions(db) == {"a": 1, "b": 2}


def test_list_marks_missing(api, db):
    seed(api, db, "a")
    use(FakeCtfd({}))
    it = api.get("/challenges").json()["items"][0]
    assert it["ctfd_missing"] is True and it["ctfd_id"] == 10 and it["services"] >= 1


def test_save_order_updates_db_and_ctfd(api, db):
    seed(api, db, "a", "b")
    before = stamps(db)
    f = FakeCtfd({10: (1, 1), 20: (2, 1)})
    use(f)
    assert api.put("/challenges/order", json={"order": ["b", "a"]}).status_code == 200
    assert positions(db) == {"b": 1, "a": 2}
    assert sorted(f.set) == [(10, 2), (20, 1)]
    assert stamps(db) == before


def test_save_order_ctfd_down(api, db):
    seed(api, db, "a", "b")
    use(FakeCtfd(down=True))
    r = api.put("/challenges/order", json={"order": ["b", "a"]})
    assert r.status_code == 502 and r.json()["code"] == "ctfd_unreachable"
    assert positions(db) == {"a": 1, "b": 2}


def test_save_order_skips_missing(api, db):
    seed(api, db, "a", "b")
    f = FakeCtfd({20: (2, 1)})
    use(f)
    assert api.put("/challenges/order", json={"order": ["b", "a"]}).status_code == 200
    assert f.set == [(20, 1)]


def test_save_order_ctfd_failure_rolls_back(api, db):
    seed(api, db, "a", "b")
    use(FakeCtfd({10: (1, 1), 20: (2, 1)}, fail_ids=[10]))
    r = api.put("/challenges/order", json={"order": ["b", "a"]})
    assert r.status_code == 502 and r.json()["code"] == "ctfd_order_failed" and "a" in r.json()["detail"]
    assert positions(db) == {"a": 1, "b": 2}


def test_save_order_validation(api, db):
    seed(api, db, "a", "b", "c", published=False)
    use(FakeCtfd())
    r = api.put("/challenges/order", json={"order": ["a", "b"]})
    assert r.status_code == 400 and r.json()["code"] == "order_mismatch"
    for s, c in (("a", "x"), ("b", "y"), ("c", "x")):
        meta = api.get(f"/challenges/{s}").json()["meta"]
        meta["category"] = c
        api.put(f"/challenges/{s}", json=meta)
    r = api.put("/challenges/order", json={"order": ["a", "b", "c"]})
    assert r.status_code == 400 and r.json()["code"] == "order_category_split"


def order(db):
    db.expire_all()
    return [c.slug for c in challenge_repository.list_all(db)]


def recategorise(api, slug, category):
    meta = api.get(f"/challenges/{slug}").json()["meta"]
    meta["category"] = category
    assert api.put(f"/challenges/{slug}", json=meta).status_code == 200


def test_category_change_moves_to_end(api, db):
    seed(api, db, "a", "b", "c", "d", published=False)
    cat_b = api.get("/challenges/b").json()["meta"]["category"]
    recategorise(api, "d", "other")
    recategorise(api, "a", "other")
    assert order(db) == ["b", "c", "d", "a"]
    recategorise(api, "a", cat_b)  # lands after c, the last of its new category, not at the very end
    assert order(db) == ["b", "c", "a", "d"]


def test_push_positions_skips_missing(api, db):
    seed(api, db, "a", "b")
    f = FakeCtfd({20: (5, 1)})
    assert challenge_service.push_positions(db, f) == [] and f.set == [(20, 2)]

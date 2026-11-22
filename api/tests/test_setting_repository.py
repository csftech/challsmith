from challsmith_api.repositories import setting_repository


def test_get_put_roundtrip(db):
    assert setting_repository.get(db, "git") is None
    setting_repository.put(db, "git", {"url": "a"})
    setting_repository.put(db, "git", {"url": "b"})
    db.commit()
    assert setting_repository.get(db, "git") == {"url": "b"}

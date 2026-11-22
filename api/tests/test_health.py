from sqlalchemy import inspect


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_schema_has_all_tables(db):
    assert {"challenges", "challenge_files", "web_sessions", "settings", "publish_runs"} <= set(
        inspect(db.get_bind()).get_table_names()
    )

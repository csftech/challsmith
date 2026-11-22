import json
import re

from conftest import get_until, start_instance, submit

SERVICES = [
    {"name": "web", "image": "localhost:5000/challsmith/examples/hello-multi-web:test",
     "port": 80, "entry": True},
    {"name": "app", "image": "localhost:5000/challsmith/examples/hello-multi-app:test",
     "env": {"DB_PASSWORD": "example"}},
    {"name": "db", "image": "mariadb:11",
     "env": {"MARIADB_ROOT_PASSWORD": "example", "MARIADB_DATABASE": "app"}},
]


def test_multi_container_flag_through_db(admin, register_user, create_challenge):
    cid = create_challenge("hello-multi", "registry:5000/challsmith/scenarios/multi:v1",
                           {"services": json.dumps(SERVICES), "flag": "hello_multi",
                            "memory": "512m"})
    user = register_user("dave")
    body = get_until(start_instance(user, cid) + "/", "APS{", timeout=60)
    flag = re.search(r"APS\{[^}]*\}", body).group(0)
    assert submit(user, cid, flag) == "correct"

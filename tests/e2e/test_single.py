from urllib.parse import urlparse

from conftest import get_until, start_instance, submit

SCENARIO = "registry:5000/challsmith/scenarios/single:v1"
HELLO_PHP = {"image": "localhost:5000/challsmith/examples/hello-php:test",
             "port": "80", "flag": "hello_php"}


def test_two_users_get_distinct_working_flags(admin, register_user, create_challenge):
    cid = create_challenge("hello-php", SCENARIO, HELLO_PHP)
    alice, bob = register_user("alice"), register_user("bob")
    url_a, url_b = start_instance(alice, cid), start_instance(bob, cid)
    flag_a = get_until(url_a + "/?give=1", "CTF{").strip()
    flag_b = get_until(url_b + "/?give=1", "CTF{").strip()
    assert flag_a.startswith("CTF{") and flag_b.startswith("CTF{")
    assert flag_a != flag_b
    assert submit(bob, cid, flag_a) == "incorrect"
    assert submit(alice, cid, flag_a) == "correct"


def listeners(path):
    """(local ip hex, port) of every LISTEN socket in a /proc/net/tcp* file."""
    out = []
    with open(path) as f:
        for line in f.readlines()[1:]:
            local, state = line.split()[1], line.split()[3]
            if state == "0A":
                ip, port = local.split(":")
                out.append((ip, int(port, 16)))
    return out


def test_instance_ports_bound_to_localhost_only(admin, register_user, create_challenge):
    cid = create_challenge("hello-php-ports", SCENARIO, HELLO_PHP)
    port = urlparse(start_instance(register_user("carol"), cid)).port
    # The test container uses the host network, so /proc/net is the host's.
    v4, v6 = listeners("/proc/net/tcp"), listeners("/proc/net/tcp6")
    for p in (port, 8000, 5000):
        addrs = {ip for ip, lp in v4 if lp == p}
        assert addrs == {"0100007F"}, f"port {p} IPv4 listeners: {addrs or 'none'}"
        assert not [ip for ip, lp in v6 if lp == p], f"port {p} listens on IPv6"

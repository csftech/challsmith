#!/usr/bin/env bash
# Check that ops cannot reach the service containers, chall-manager or the registry,
# but can reach CTFd and the challenge instances. Run on the installed VM: sudo tests/ops-isolation.sh
set -u
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo $0" >&2; exit 1; }
fail=0
open_as() { sudo -u "$1" timeout 3 bash -c "</dev/tcp/$2/$3" 2>/dev/null; }
expect() { # $1 = open|closed for ops, $2 = host, $3 = port, $4 = label
  local got=closed
  open_as ops "$2" "$3" && got=open
  if [ "$got" = "$1" ]; then echo "ok   ops $4 $2:$3 $got"; else echo "FAIL ops $4 $2:$3 $got, want $1"; fail=1; fi
}
# closed for ops but open for root, so "closed" means filtered, not down
blocked() {
  open_as root "$1" "$2" || { echo "FAIL root $3 $1:$2 unreachable, cannot test"; fail=1; return; }
  expect closed "$@"
}
ips() { docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$1"; }

for svc in ctfd:8000 ctfd-db:3306 ctfd-redis:6379 chall-manager:8080 registry:5000 api:8000 app-db:5432 web:3000; do
  name=${svc%:*} port=${svc#*:}
  c=$(docker ps -q -f label=com.docker.compose.project=challsmith -f label=com.docker.compose.service="$name")
  [ -n "$c" ] || { echo "FAIL $name is not running"; fail=1; continue; }
  for ip in $(ips "$c"); do blocked "$ip" "$port" "$name"; done
done
blocked 127.0.0.1 5000 registry
expect open 127.0.0.1 8000 ctfd
blocked 127.0.0.1 3000 web
open_as aps 127.0.0.1 3000 && echo "ok   aps web 127.0.0.1:3000 open" || { echo "FAIL aps web 127.0.0.1:3000 closed"; fail=1; }

# default deny: ops cannot reach the internet (root can, so "closed" means filtered, not offline)
if open_as root 1.1.1.1 443 || open_as root 8.8.8.8 53; then
  for t in 1.1.1.1:443 8.8.8.8:53; do expect closed "${t%:*}" "${t#*:}" external; done
else echo "note: no internet, external check skipped"; fi

# loopback stays open for ops: a listener on a random high port (Burp's proxy and browser use such ports)
lport=$((20000 + RANDOM % 20000))
sudo -u ops python3 -m http.server "$lport" --bind 127.0.0.1 >/dev/null 2>&1 & lpid=$!
sleep 1
expect open 127.0.0.1 "$lport" loopback-listener
kill "$lpid" 2>/dev/null

# instance networks: a container on a challenge-* network must not reach any platform service
iso_clean() { docker rm -f challenge-isocheck-c challenge-isocheck-srv >/dev/null 2>&1; docker network rm challenge-isocheck >/dev/null 2>&1; }
iso_clean; trap iso_clean EXIT
IMG=${ISOCHECK_IMAGE:-alpine:3.24.4}
iso_ok=1
docker network create challenge-isocheck >/dev/null   && docker run -d --name challenge-isocheck-srv --network challenge-isocheck "$IMG" sh -c 'while :; do nc -l -p 9999; done' >/dev/null   && docker run -d --name challenge-isocheck-c --network challenge-isocheck "$IMG" sleep infinity >/dev/null   || { echo "FAIL cannot start the challenge-isocheck containers"; fail=1; iso_ok=0; }
if [ "$iso_ok" = 1 ]; then
  sleep 1
  # positive control: the same nc command must reach a listener on the same network, else "blocked" proves nothing
  if docker exec challenge-isocheck-c nc -z -w 3 $(ips challenge-isocheck-srv) 9999 >/dev/null 2>&1; then
    echo "ok   instance network control: probe reaches a listener on its own network"
  else echo "FAIL instance network control: probe cannot reach a listener on its own network"; fail=1; iso_ok=0; fi
fi
if [ "$iso_ok" = 1 ]; then
  for svc in ctfd:8000 chall-manager:8080 ctfd-redis:6379 ctfd-db:3306 api:8000 app-db:5432 web:3000 registry:5000; do
    name=${svc%:*} port=${svc#*:}
    c=$(docker ps -q -f label=com.docker.compose.project=challsmith -f label=com.docker.compose.service="$name")
    [ -n "$c" ] || { echo "FAIL $name is not running (instance network check)"; fail=1; continue; }
    for ip in $(ips "$c"); do
      docker exec challenge-isocheck-c true 2>/dev/null || { echo "FAIL probe container is not running"; fail=1; break 2; }
      if docker exec challenge-isocheck-c nc -z -w 3 "$ip" "$port" 2>/dev/null; then echo "FAIL instance network reaches $name $ip:$port"; fail=1
      else echo "ok   instance network blocked from $name $ip:$port"; fi
    done
  done
fi

# challenge instances: containers outside the compose project; published port open, container IP closed
n=0
for c in $(docker ps -q); do
  [ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$c")" = challsmith ] && continue
  while read -r cport _ host; do  # "80/tcp -> 127.0.0.1:32781"
    case $host in 127.0.0.1:*) ;; *) continue ;; esac
    n=$((n+1))
    expect open 127.0.0.1 "${host#*:}" instance
    for ip in $(ips "$c"); do blocked "$ip" "${cport%/tcp}" instance; done
  done < <(docker port "$c")
done
[ "$n" -gt 0 ] || echo "note: no challenge instance running, instance checks skipped"

[ "$fail" -eq 0 ] && echo "ops isolation: PASS" || echo "ops isolation: FAIL"
exit "$fail"

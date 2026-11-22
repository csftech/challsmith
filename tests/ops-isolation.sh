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

# instance networks: a container on a challenge-* network must not reach any platform service
docker rm -f challenge-isocheck-c >/dev/null 2>&1; docker network rm challenge-isocheck >/dev/null 2>&1
trap 'docker rm -f challenge-isocheck-c >/dev/null 2>&1; docker network rm challenge-isocheck >/dev/null 2>&1' EXIT
docker network create challenge-isocheck >/dev/null && docker run -d --name challenge-isocheck-c --network challenge-isocheck alpine:3.24.4 sleep 120 >/dev/null   || { echo "FAIL cannot start the challenge-isocheck container"; fail=1; }
for svc in ctfd:8000 chall-manager:8080 ctfd-redis:6379 ctfd-db:3306 api:8000 app-db:5432 web:3000 registry:5000; do
  name=${svc%:*} port=${svc#*:}
  c=$(docker ps -q -f label=com.docker.compose.project=challsmith -f label=com.docker.compose.service="$name")
  for ip in $(ips "$c"); do
    if docker exec challenge-isocheck-c nc -z -w 3 "$ip" "$port" 2>/dev/null; then echo "FAIL instance network reaches $name $ip:$port"; fail=1
    else echo "ok   instance network blocked from $name $ip:$port"; fi
  done
done

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

#!/bin/sh
# Build and run every template service folder. Run on the dev VM as a docker-group user.
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
sfx=$$
fail=0
net=cs-smoke-$sfx
cleanup() {
  docker ps -aq --filter "label=cs-smoke=$sfx" | xargs -r docker rm -f >/dev/null 2>&1
  docker network rm "$net" >/dev/null 2>&1
  docker images -q --filter "label=cs-smoke=$sfx" | xargs -r docker rmi -f >/dev/null 2>&1
}
trap cleanup EXIT INT TERM
docker network create "$net" >/dev/null

ok() { echo "PASS $1"; }
bad() { echo "FAIL $1"; fail=1; }
build() { # template service -> image name
  docker build -q --label "cs-smoke=$sfx" -t "cs-smoke-$1-$2:$sfx" "$repo/templates/$1/$2" >/dev/null
}
run() { # name image [extra docker args]
  n=$1; i=$2; shift 2
  docker run -d --label "cs-smoke=$sfx" --name "$n" --network "$net" "$@" "$i" >/dev/null
}
wait_for() { # tries cmd...
  tries=$1; shift
  while [ "$tries" -gt 0 ]; do "$@" >/dev/null 2>&1 && return 0; tries=$((tries - 1)); sleep 1; done
  return 1
}
probe() { docker run --rm --network "$net" --label "cs-smoke=$sfx" curlimages/curl:latest -fsS --max-time 3 "$@"; }

# no FLAG: container must exit non-zero
noflag() { # template service
  build "$1" "$2" || { bad "$1/$2 build"; return; }
  docker run --rm --label "cs-smoke=$sfx" "cs-smoke-$1-$2:$sfx" >/dev/null 2>&1 && bad "$1/$2 without FLAG exited 0" || ok "$1/$2 fails without FLAG"
}

for spec in php:app:80 python-flask:app:5000 node-nextjs:app:3000; do
  t=${spec%%:*}; rest=${spec#*:}; s=${rest%%:*}; port=${rest#*:}
  n=cs-smoke-$t-$sfx
  if build "$t" "$s" && run "$n" "cs-smoke-$t-$s:$sfx" -e FLAG='APS{smoke}'; then
    wait_for 60 probe "http://$n:$port/" && ok "$t responds" || { bad "$t responds"; docker logs "$n" 2>&1 | tail -5; }
    docker exec "$n" cat /flag.txt 2>/dev/null | grep -qx 'APS{smoke}' && ok "$t flag.txt" || bad "$t flag.txt"
  else bad "$t build/run"; fi
  noflag "$t" "$s"
done

# tcp
n=cs-smoke-tcp-$sfx
if build tcp app && run "$n" "cs-smoke-tcp-app:$sfx" -e FLAG='APS{smoke}'; then
  tcp_out() { [ -n "$(docker run --rm --network "$net" --label "cs-smoke=$sfx" alpine:3.24.4 sh -c "nc -w 3 $n 9000 </dev/null")" ]; }
  wait_for 30 tcp_out && ok "tcp output" || bad "tcp output"
else bad "tcp build/run"; fi
noflag tcp app

# nginx-php-db
if build nginx-php-db web && build nginx-php-db php; then
  run cs-smoke-nx-db-$sfx mariadb:11.8 --network-alias db -e MARIADB_ROOT_PASSWORD=change-me -e MARIADB_DATABASE=app
  run cs-smoke-nx-php-$sfx "cs-smoke-nginx-php-db-php:$sfx" --network-alias php -e FLAG='APS{smoke}' -e DB_PASSWORD=change-me
  run cs-smoke-nx-web-$sfx "cs-smoke-nginx-php-db-web:$sfx" --network-alias web -e FLAG='APS{smoke}'
  wait_for 60 probe "http://web/" && ok "nginx-php-db responds 200" || { bad "nginx-php-db responds 200"; docker logs cs-smoke-nx-web-$sfx 2>&1 | tail -5; }
else bad "nginx-php-db build"; fi
noflag nginx-php-db php

[ "$fail" -eq 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $fail

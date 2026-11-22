#!/bin/sh
# Build the api test image and run pytest against a throwaway postgres. Run as a docker-group user (aps).
set -eu
repo=$(cd "$(dirname "$0")/../.." && pwd)
net=challsmith-apitest-$$
pg=$net-pg
cleanup() { docker rm -f "$pg" >/dev/null 2>&1 || true; docker network rm "$net" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

docker build -q -f "$repo/backend/Dockerfile" --target test -t challsmith/api-test "$repo" >/dev/null
docker network create "$net" >/dev/null
docker run -d --name "$pg" --network "$net" -e POSTGRES_USER=t -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t \
  postgres:19-alpine >/dev/null
until docker exec "$pg" pg_isready -h 127.0.0.1 -U t -d t >/dev/null 2>&1; do sleep 1; done
docker run --rm --network "$net" -e DATABASE_URL="postgresql+psycopg://t:t@$pg/t" \
  challsmith/api-test python -m pytest -v -p no:cacheprovider "$@"

#!/bin/sh
# Build and push the example challenges, then run the e2e tests against the installed stack.
# Run on the challsmith host as a docker-group user (aps).
set -eu
repo=$(cd "$(dirname "$0")/../.." && pwd)
envfile=${CHALLSMITH_ENV:-/opt/challsmith/challsmith.env}
reg=localhost:5000/challsmith/examples

build() { docker build -q -t "$reg/$1:test" "$repo/examples/$2" && docker push -q "$reg/$1:test"; }
build hello-php hello-php
build hello-multi-web hello-multi/web
build hello-multi-app hello-multi/app

CTFD_ADMIN_NAME=$(sed -n 's/^CTFD_ADMIN_NAME=//p' "$envfile")
CTFD_ADMIN_PASSWORD=$(sed -n 's/^CTFD_ADMIN_PASSWORD=//p' "$envfile")
export CTFD_ADMIN_NAME CTFD_ADMIN_PASSWORD

docker run --rm --network host -e CTFD_ADMIN_NAME -e CTFD_ADMIN_PASSWORD -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -v "$repo/tests/e2e:/t" -w /t python:3.15-alpine \
  sh -c "pip install -q --root-user-action=ignore -r requirements.txt && pytest -v -p no:cacheprovider $*"

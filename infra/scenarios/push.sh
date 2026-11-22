#!/usr/bin/env bash
# Build the Go scenarios in a container and push them as OCI artifacts to the local registry.
# Usage: infra/scenarios/push.sh [tag]   (env: GOPROXY, GOSUMDB, HTTP_PROXY, HTTPS_PROXY, NO_PROXY, ORAS_BIN)
set -euo pipefail

TAG="${1:-v1}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$SRC/bin/.cache"

# Exception: the golang build container is a build step, not a challenge, so it may use the
# company proxy for `go build` module downloads. Challenge containers never get it.
PROXY_ARGS=()
if [ -n "${HTTP_PROXY:-}${HTTPS_PROXY:-}" ]; then
  for v in HTTP_PROXY HTTPS_PROXY NO_PROXY; do
    [ -z "${!v:-}" ] || PROXY_ARGS+=(-e "$v=${!v}")
  done
fi

# GOSUMDB is forwarded only when set; GOTOOLCHAIN=local stops Go from downloading a toolchain.
[ -z "${GOSUMDB:-}" ] || PROXY_ARGS+=(-e "GOSUMDB=$GOSUMDB")

for name in single multi; do
  docker run --rm -u "$(id -u):$(id -g)" -v "$SRC:/src" -w /src \
    -e HOME=/src/bin/.cache -e GOCACHE=/src/bin/.cache/gocache -e GOMODCACHE=/src/bin/.cache/gomod \
    -e CGO_ENABLED=0 -e GOTOOLCHAIN=local -e GOPROXY "${PROXY_ARGS[@]}" \
    golang:1.27-alpine go build -o "bin/$name/main" "./$name"

  cat > "$SRC/bin/$name/Pulumi.yaml" <<YAML
name: $name
runtime:
  name: go
  options:
    binary: ./main
YAML

  (cd "$SRC/bin/$name" && "${ORAS_BIN:-oras}" \
    push --plain-http "localhost:5000/challsmith/scenarios/$name:$TAG" \
    --artifact-type application/vnd.ctfer-io.scenario \
    main:application/vnd.ctfer-io.file Pulumi.yaml:application/vnd.ctfer-io.file)
done

#!/usr/bin/env bash
# Build the Go scenarios in a container and push them as OCI artifacts to the local registry.
# Usage: scripts/push-scenarios.sh [tag]   (env: GOPROXY, ORAS_BIN)
set -euo pipefail

TAG="${1:-v1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scenarios"
mkdir -p "$SRC/bin/.cache"

for name in single multi; do
  docker run --rm -u "$(id -u):$(id -g)" -v "$SRC:/src" -w /src \
    -e HOME=/src/bin/.cache -e GOCACHE=/src/bin/.cache/gocache -e GOMODCACHE=/src/bin/.cache/gomod \
    -e CGO_ENABLED=0 -e GOPROXY \
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

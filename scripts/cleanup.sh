#!/bin/sh
# Pre-export cleanup (instances, trainee users, sessions). Runs app.cli.cleanup inside the api container as aps.
# Usage: scripts/cleanup.sh [options]   (asks for confirmation; see the README)
self=$(readlink -f "$0"); cd "$(dirname "$self")/.." || exit 1
if [ "$(id -u)" -eq 0 ]; then exec sudo -u aps sh "$self" "$@"; fi
id -nG | tr ' ' '\n' | grep -qx docker || { echo "Run as aps (or root): this user is not in the docker group." >&2; exit 1; }
t=; [ -t 0 ] || t=-T
exec docker compose -p challsmith --env-file "$PWD/challsmith.env" -f "$PWD/infra/compose.yaml" exec $t api python -m app.cli.cleanup "$@"

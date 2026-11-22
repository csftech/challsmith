#!/bin/sh
set -eu
if [ -z "${FLAG:-}" ]; then echo "FLAG is empty" >&2; exit 1; fi
printf '%s\n' "$FLAG" > /flag.txt
exec "$@"

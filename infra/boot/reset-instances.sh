#!/bin/sh
# Boot-time instance reset: retries the instances-only cleanup until the api and chall-manager answer (bounded).
# Run by challsmith-boot-reset.service; output goes to the journal.
cd "$(dirname "$(readlink -f "$0")")/../.." || exit 1
deadline=$(( $(date +%s) + ${RESET_TIMEOUT:-300} ))
while :; do
  if ./cleanup.sh --instances-only --yes; then echo "instances reset"; exit 0; fi
  [ "$(date +%s)" -lt "$deadline" ] || { echo "instance reset gave up: api or chall-manager not ready in time" >&2; exit 1; }
  echo "api or chall-manager not ready, retrying in 5s" >&2
  sleep 5
done

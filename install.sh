#!/usr/bin/env bash
# challsmith one-shot installer. Run: sudo ./install.sh (safe to re-run).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST=/opt/challsmith
ENVF="$DEST/challsmith.env"
export DEBIAN_FRONTEND=noninteractive

# 1. preconditions
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo ./install.sh" >&2; exit 1; }
. /etc/os-release
[ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = 26.04 ] || { echo "Ubuntu 26.04 required (found ${PRETTY_NAME:-unknown})" >&2; exit 1; }
[ -f "$SRC/challsmith.env" ] || { echo "Missing challsmith.env: copy challsmith.env.example to challsmith.env and fill it in first." >&2; exit 1; }

# values may be single-quoted (e.g. URLs containing &), which sourcing handles
set -a; . "$SRC/challsmith.env"; set +a
: "${HTTP_PROXY:=}" "${HTTPS_PROXY:=}" "${NO_PROXY:=}" "${DOCKER_REGISTRY_MIRROR:=}"
NO_PROXY_ALL="localhost,127.0.0.1,registry${NO_PROXY:+,$NO_PROXY}"
[ -z "$HTTP_PROXY$HTTPS_PROXY" ] || export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" no_proxy="$NO_PROXY_ALL"

# 2. apt proxy
if [ -n "$HTTP_PROXY$HTTPS_PROXY" ]; then
  {
    [ -z "$HTTP_PROXY" ] || echo "Acquire::http::Proxy \"$HTTP_PROXY\";"
    [ -z "$HTTPS_PROXY" ] || echo "Acquire::https::Proxy \"$HTTPS_PROXY\";"
  } > /etc/apt/apt.conf.d/90challsmith-proxy
fi

# 3. packages (skip Docker if already usable; docker.io conflicts with docker-ce)
apt-get update -y
apt-get install -y curl gettext-base rsync openssl
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  echo "Docker and compose plugin already present, skipping Docker install."
else
  apt-get install -y docker.io docker-compose-v2
fi

# 4. docker daemon config; restart only when something changed
changed=0
install -d /etc/docker /etc/systemd/system/docker.service.d
if [ -n "$DOCKER_REGISTRY_MIRROR" ]; then
  new="{\"registry-mirrors\": [\"$DOCKER_REGISTRY_MIRROR\"]}"
else
  new="{}"
fi
if [ ! -f /etc/docker/daemon.json ] || [ "$(cat /etc/docker/daemon.json)" != "$new" ]; then
  [ ! -f /etc/docker/daemon.json ] || cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
  echo "$new" > /etc/docker/daemon.json; changed=1
fi
dropin=/etc/systemd/system/docker.service.d/http-proxy.conf
if [ -n "$HTTP_PROXY$HTTPS_PROXY" ]; then
  new="[Service]
Environment=\"HTTP_PROXY=$HTTP_PROXY\"
Environment=\"HTTPS_PROXY=$HTTPS_PROXY\"
Environment=\"NO_PROXY=$NO_PROXY_ALL\""
  if [ ! -f "$dropin" ] || [ "$(cat "$dropin")" != "$new" ]; then echo "$new" > "$dropin"; changed=1; fi
elif [ -f "$dropin" ]; then
  rm "$dropin"; changed=1
fi
systemctl daemon-reload
systemctl enable --now docker
[ "$changed" -eq 0 ] || systemctl restart docker

# 5. accounts (no passwords set here)
getent group docker >/dev/null || groupadd docker
id aps >/dev/null 2>&1 || useradd -m -s /bin/bash -G docker aps
id ops >/dev/null 2>&1 || useradd -m -s /bin/bash ops

# 6. copy repo
install -d -o aps -g aps -m 750 "$DEST"
OLD_ENV=/dev/null; [ ! -f "$ENVF" ] || { OLD_ENV="$(mktemp)"; cp "$ENVF" "$OLD_ENV"; }
rsync -a --exclude=.git --exclude=.env --exclude=.superpowers --exclude=scenarios/bin "$SRC/" "$DEST/"
chown -R aps:aps "$DEST"
chmod 750 "$DEST"
chmod 600 "$ENVF"

# 7. secrets: fill only when empty (rsync replaced the env file, so prefer the previous install's value)
fill() { # $1 = key
  if ! grep -qE "^$1=.+" "$ENVF"; then
    val="$(sed -n "s/^$1=//p" "$OLD_ENV" | head -n1)"
    [ -n "$val" ] || val="$(openssl rand -hex 32)"
    if grep -qE "^$1=" "$ENVF"; then sed -i "s|^$1=.*|$1=$val|" "$ENVF"; else echo "$1=$val" >> "$ENVF"; fi
  fi
}
fill CTFD_SECRET_KEY
fill CTFD_DB_PASSWORD
[ "$OLD_ENV" = /dev/null ] || rm -f "$OLD_ENV"

# 8. render ctfd-setup.yaml (reload env so generated secrets and admin values are current)
set -a; . "$ENVF"; set +a
envsubst '${CTFD_ADMIN_NAME} ${CTFD_ADMIN_EMAIL} ${CTFD_ADMIN_PASSWORD}' \
  < "$DEST/infra/ctfd-setup.yaml.tmpl" > "$DEST/infra/ctfd-setup.yaml"
chown aps:aps "$DEST/infra/ctfd-setup.yaml"
chmod 600 "$DEST/infra/ctfd-setup.yaml"

# 9. start the stack, wait for the registry, push scenarios
sudo -u aps -H docker compose --env-file "$ENVF" -f "$DEST/infra/compose.yaml" up -d --build
for _ in $(seq 60); do
  curl -fsS --noproxy '*' -o /dev/null http://127.0.0.1:5000/v2/ && break
  sleep 2
done
curl -fsS --noproxy '*' -o /dev/null http://127.0.0.1:5000/v2/ || { echo "Registry did not come up" >&2; exit 1; }
sudo -u aps -H env GOPROXY="${GOPROXY:-}" ORAS_IMAGE="${ORAS_IMAGE:-ghcr.io/oras-project/oras:v1.3.0}" \
  "$DEST/scripts/push-scenarios.sh" v1

# 10. Burp Suite Community
BURP=/opt/BurpSuiteCommunity
if [ ! -e "$BURP" ]; then
  url="${BURP_DOWNLOAD_URL:-https://portswigger.net/burp/releases/download?product=community&type=Linux}"
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/burp.sh" "$url"
  chmod +x "$tmp/burp.sh"
  "$tmp/burp.sh" -q -dir "$BURP"
  rm -rf "$tmp"
fi
cat > /usr/share/applications/burpsuite-community.desktop <<DESK
[Desktop Entry]
Type=Application
Name=Burp Suite Community
Exec=$BURP/BurpSuiteCommunity
Terminal=false
Categories=Development;Security;
DESK

# 11. done
cat <<MSG

challsmith installed. CTFd: http://127.0.0.1:8000
TODO: set passwords with 'sudo passwd aps' and 'sudo passwd ops'.
MSG

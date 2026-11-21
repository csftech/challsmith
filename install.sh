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
apt-get install -y curl gettext-base rsync openssl python3 nftables
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  echo "Docker and compose plugin already present, skipping Docker install."
else
  apt-get install -y docker.io docker-compose-v2
fi

# 4. docker daemon config; restart only when something changed
changed=0
install -d /etc/docker /etc/systemd/system/docker.service.d
# no mirror: leave daemon.json untouched; else merge only registry-mirrors (original kept once)
if [ -n "$DOCKER_REGISTRY_MIRROR" ]; then
  [ -f /etc/docker/daemon.json ] || echo "{}" > /etc/docker/daemon.json
  [ -e /etc/docker/daemon.json.bak ] || cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
  rc=0
  python3 - "$DOCKER_REGISTRY_MIRROR" <<PY || rc=$?
import json, sys
p = "/etc/docker/daemon.json"
d = json.load(open(p))
if d.get("registry-mirrors") == [sys.argv[1]]:
    sys.exit(3)
d["registry-mirrors"] = [sys.argv[1]]
json.dump(d, open(p, "w"), indent=2)
PY
  case $rc in 0) changed=1 ;; 3) ;; *) echo "Cannot merge /etc/docker/daemon.json (invalid JSON?), aborting." >&2; exit 1 ;; esac
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
id aps >/dev/null 2>&1 || useradd -m -s /bin/bash aps
usermod -aG docker aps
if id ops >/dev/null 2>&1; then
  # an existing ops must not keep privileged groups
  for g in docker sudo adm lxd; do
    if id -nG ops | tr ' ' '\n' | grep -qx "$g"; then gpasswd -d ops "$g" >/dev/null; echo "Removed ops from group $g."; fi
  done
else
  useradd -m -s /bin/bash ops
fi

# 5b. ops firewall: no ops traffic to container networks or the registry (see infra/ops-firewall.nft)
install -D -m 644 "$SRC/infra/ops-firewall.nft" /etc/challsmith/ops-firewall.nft
install -m 644 "$SRC/infra/challsmith-ops-firewall.service" /etc/systemd/system/challsmith-ops-firewall.service
systemctl daemon-reload
systemctl enable challsmith-ops-firewall.service
systemctl restart challsmith-ops-firewall.service

# 6. copy repo
install -d -o aps -g aps -m 750 "$DEST"
OLD_ENV=/dev/null; [ ! -f "$ENVF" ] || { OLD_ENV="$(mktemp)"; cp "$ENVF" "$OLD_ENV"; }
rsync -a --chmod=o-rwx --exclude=.git --exclude=.env --exclude=.superpowers --exclude=scenarios/bin "$SRC/" "$DEST/"
chown -R aps:aps "$DEST"
chmod 750 "$DEST"
chmod 600 "$ENVF"

# 7. secrets: fill only when empty (rsync replaced the env file, so prefer the previous install's value)
fill() { # $1 = key; an installed non-empty value always wins
  old="$(sed -n "s/^$1=//p" "$OLD_ENV" | head -n1)"
  cur="$(sed -n "s/^$1=//p" "$ENVF" | head -n1)"
  if [ -n "$old" ]; then
    [ -z "$cur" ] || [ "$cur" = "$old" ] || echo "WARNING: $1 in challsmith.env differs from the installed value; ignored, keeping the installed one." >&2
    val="$old"
  elif [ -z "$cur" ]; then
    val="$(openssl rand -hex 32)"
  else
    return 0
  fi
  if grep -qE "^$1=" "$ENVF"; then sed -i "s|^$1=.*|$1=$val|" "$ENVF"; else echo "$1=$val" >> "$ENVF"; fi
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
dc() { sudo -u aps -H docker compose --env-file "$ENVF" -f "$DEST/infra/compose.yaml" "$@"; }
dc up -d --build
# a failed ctfd-setup would leave CTFd's open /setup page for the first visitor to claim admin
rc=0; dc wait ctfd-setup >/dev/null || rc=$?
[ "$rc" -eq 0 ] || { echo "ctfd-setup failed (exit $rc), see: docker compose -p challsmith logs ctfd-setup" >&2; exit 1; }
code="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/setup)"
[ "$code" = 302 ] || { echo "CTFd /setup returned $code, expected a redirect (CTFd not set up), aborting." >&2; exit 1; }
for _ in $(seq 60); do
  curl -fsS --noproxy '*' -o /dev/null http://127.0.0.1:5000/v2/ && break
  sleep 2
done
curl -fsS --noproxy '*' -o /dev/null http://127.0.0.1:5000/v2/ || { echo "Registry did not come up" >&2; exit 1; }

# 9b. GitHub release artifacts (checksum-verified; oras: sha256, pulumi-docker: SHA-1): Pulumi docker plugin and oras.
# pulumi-docker version comes from scenarios/go.mod; the oras version is defined here only.
ORAS_VERSION=1.4.0
PULUMI_DOCKER_VERSION="$(sed -n 's|.*pulumi-docker/sdk/v5 v||p' "$DEST/scenarios/go.mod" | head -n1)"
[ -n "$PULUMI_DOCKER_VERSION" ] || { echo "Cannot read pulumi-docker version from scenarios/go.mod" >&2; exit 1; }
: "${PULUMI_DOCKER_PLUGIN:=}" "${PULUMI_DOCKER_CHECKSUMS:=}" "${ORAS_TARBALL:=}" "${ORAS_CHECKSUMS:=}"

# fetch_verified <source url|path> <asset name> <checksums name> <local checksums file|""> <out file>
fetch_verified() {
  local src=$1 asset=$2 sums=$3 localsums=$4 out=$5 sf="$5.sums" want got
  case "$src" in
    http://*|https://*)
      curl -fL --retry 3 -o "$out" "$src" || { echo "Download failed: $src" >&2; exit 1; }
      curl -fL --retry 3 -o "$sf" "${src%/*}/$sums" || { echo "Checksum download failed: ${src%/*}/$sums" >&2; exit 1; } ;;
    *)
      [ -f "$src" ] || { echo "Local file not found: $src" >&2; exit 1; }
      cp "$src" "$out"
      if [ -n "$localsums" ]; then cp "$localsums" "$sf"; else sf=; echo "WARNING: no checksum file for local $asset, skipping checksum verification." >&2; fi ;;
  esac
  if [ -n "$sf" ]; then
    want="$(awk -v f="$asset" '{n=$2; sub(/^[.][/]/,"",n)} n==f {print $1}' "$sf")"
    case ${#want} in 40) got="$(sha1sum "$out" | cut -d' ' -f1)" ;; *) got="$(sha256sum "$out" | cut -d' ' -f1)" ;; esac  # pulumi-docker publishes SHA-1 only
    [ -n "$want" ] && [ "$want" = "$got" ] || { echo "Checksum mismatch for $asset (expected '${want:-none}', got $got), aborting." >&2; exit 1; }
  fi
  chmod 644 "$out"
}

tmp="$(mktemp -d)"; chmod 755 "$tmp"; trap 'rm -rf "$tmp"' EXIT

# pulumi docker plugin, installed into chall-manager's Pulumi home (volume cm-pulumi)
if dc exec -T chall-manager pulumi plugin ls 2>/dev/null | awk -v v="$PULUMI_DOCKER_VERSION" '$1=="docker" && $2=="resource" && $3==v {f=1} END {exit !f}'; then
  echo "Pulumi docker plugin $PULUMI_DOCKER_VERSION already installed, skipping."
else
  asset="pulumi-resource-docker-v$PULUMI_DOCKER_VERSION-linux-amd64.tar.gz"
  fetch_verified "${PULUMI_DOCKER_PLUGIN:-https://github.com/pulumi/pulumi-docker/releases/download/v$PULUMI_DOCKER_VERSION/$asset}" \
    "$asset" "pulumi-docker_${PULUMI_DOCKER_VERSION}_checksums.txt" "$PULUMI_DOCKER_CHECKSUMS" "$tmp/$asset"
  dc cp "$tmp/$asset" chall-manager:/tmp/plugin.tar.gz
  dc exec -T chall-manager pulumi plugin install resource docker "v$PULUMI_DOCKER_VERSION" --file /tmp/plugin.tar.gz \
    || { echo "Pulumi docker plugin install failed" >&2; exit 1; }
  dc exec -T chall-manager rm -f /tmp/plugin.tar.gz
  echo "Pulumi docker plugin $PULUMI_DOCKER_VERSION installed."
fi

# oras binary
ORAS_BIN="$DEST/bin/oras"
if [ -x "$ORAS_BIN" ] && "$ORAS_BIN" version 2>/dev/null | grep -qE "^Version: +$ORAS_VERSION$"; then
  echo "oras $ORAS_VERSION already installed, skipping."
else
  asset="oras_${ORAS_VERSION}_linux_amd64.tar.gz"
  fetch_verified "${ORAS_TARBALL:-https://github.com/oras-project/oras/releases/download/v$ORAS_VERSION/$asset}" \
    "$asset" "oras_${ORAS_VERSION}_checksums.txt" "$ORAS_CHECKSUMS" "$tmp/$asset"
  mkdir "$tmp/oras"; tar -xzf "$tmp/$asset" -C "$tmp/oras" oras || { echo "Cannot extract oras from $asset" >&2; exit 1; }
  install -d -o aps -g aps -m 755 "$DEST/bin"
  install -o aps -g aps -m 755 "$tmp/oras/oras" "$ORAS_BIN"
  echo "oras $ORAS_VERSION installed."
fi

# The proxy goes only to the golang build container (module download), never to a challenge.
sudo -u aps -H env GOPROXY="${GOPROXY:-}" GOSUMDB="${GOSUMDB:-}" HTTP_PROXY="$HTTP_PROXY" HTTPS_PROXY="$HTTPS_PROXY" NO_PROXY="$NO_PROXY_ALL" ORAS_BIN="$ORAS_BIN" \
  "$DEST/scripts/push-scenarios.sh" v1

# 10. Burp Suite Community
BURP=/opt/BurpSuiteCommunity
if [ ! -e "$BURP" ]; then
  url="${BURP_DOWNLOAD_URL:-https://portswigger.net/burp/releases/download?product=community&type=Linux}"
  curl -fsSL -o "$tmp/burp.sh" "$url"
  chmod +x "$tmp/burp.sh"
  "$tmp/burp.sh" -q -dir "$BURP"
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

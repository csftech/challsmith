[繁體中文](README_ZH-TW.md)

# challsmith

challsmith is a CTFd training environment that runs on one Ubuntu 26.04 VM. It is installed once, exported as a vmdk and handed to new hires, who solve web challenges in their own copy. CTFd runs with the ctfd-chall-manager plugin, and every challenge instance is started on demand by chall-manager as Docker containers. Each instance gets its own dynamic flag.

Authors build challenges in a web app on `http://127.0.0.1:3000`: pick a template, edit the files and publish, and the app builds the images and creates the CTFd challenge (see "Authoring challenges"). Challenges can still be created by hand in the CTFd admin UI (see "Create a challenge manually").

## Architecture

```
Ubuntu 26.04 VM
├─ ops (trainee) ── browser ──> CTFd 127.0.0.1:8000 ──> challenge instance 127.0.0.1:<random port>
│                          └──> Burp Suite
└─ aps (docker group)
   │  (authors) browser ──> web app 127.0.0.1:3000 ──> api ──> CTFd, registry, docker
   └─ docker compose project "challsmith" (restart: unless-stopped)
      ├─ ctfd                  CTFd 3.8.9 + ctfd-chall-manager plugin v0.10.1, 127.0.0.1:8000
      ├─ ctfd-db / ctfd-redis  mariadb 11.8 / redis 8.10-alpine
      ├─ ctfd-setup            one-shot, creates the CTFd admin and plugin settings
      ├─ chall-manager         v0.6.7, mounts /var/run/docker.sock, no published port
      ├─ chall-manager-janitor removes expired instances every minute
      ├─ web                   authoring web app (Next.js 16), 127.0.0.1:3000, the only way to api
      ├─ api                   FastAPI backend, mounts /var/run/docker.sock, no published port
      ├─ app-db                postgres 19-alpine, challenges, sessions and settings of the web app
      └─ registry              registry 3.1, 127.0.0.1:5000, challenge images and scenarios
```

All published ports bind to 127.0.0.1, and a firewall keeps `ops` away from the containers and the registry (see "Security notes"). Challenge images and scenarios are pushed to `localhost:5000`; chall-manager pulls them as `registry:5000/...`.

The two scenarios are written in Go (Go 1.27, pulumi-docker v5.3.0) and are built and pushed to the registry as OCI artifacts by `install.sh`:

- `registry:5000/challsmith/scenarios/single:v1` starts one container.
- `registry:5000/challsmith/scenarios/multi:v1` starts several containers on a per-instance Docker network, with one entry service.

## Install

You need an Ubuntu 26.04 Desktop VM with internet access, directly or through the company proxies.

1. Copy the repository to the VM, then `cp challsmith.env.example challsmith.env` and edit it. The CTFd admin name, email and password are required, and so is `WEB_ADMIN_PASSWORD`, the password of the web app (`WEB_ADMIN_USER` is its user name, default `admin`). `CTFD_SECRET_KEY`, `CTFD_DB_PASSWORD` and `APP_DB_PASSWORD` (the web app's PostgreSQL) are generated when left empty. The web app signs in to CTFd with the CTFd admin account. `CM_MANA_TOTAL` is the per-user mana limit (default 0, unlimited; see below).
2. Run `sudo ./install.sh`. It is safe to re-run. It installs Docker, writes the Docker daemon proxy settings, creates the users `aps` (docker group) and `ops` (an existing `ops` is removed from the docker, sudo, adm and lxd groups), installs the `ops` firewall, copies the repository to `/opt/challsmith`, starts the compose project, builds and pushes the scenarios, and installs Burp Suite (PortSwigger's merged installer, pinned by `BURP_VERSION` and verified by SHA-256). Without a licence it runs as Community; that is PortSwigger's behaviour, so the maintainer should confirm it on the desktop. Installs from before this lived in `/opt/BurpSuiteCommunity`, which the installer leaves alone and you can delete.
3. Set the passwords: `sudo passwd aps` and `sudo passwd ops`.
4. Open `http://127.0.0.1:8000` and log in to CTFd with the admin account from `challsmith.env`. The web app is at `http://127.0.0.1:3000`, with `WEB_ADMIN_USER` and `WEB_ADMIN_PASSWORD`.

Mana is unlimited by default: with `CM_MANA_TOTAL=0` the CTFd plugin ignores mana, and a trainee can run instances of any number of challenges at once. The per-challenge `mana` field in the web app (default 0) only matters when you set `CM_MANA_TOTAL` to a positive number, which then caps the sum of the mana of one user's running instances. Existing installs copied `CM_MANA_TOTAL=5` from the old example: change it to `0` in `challsmith.env` and rerun `sudo ./install.sh` to lift the limit.

If your `challsmith.env` still has the old `BURP_DOWNLOAD_URL` for Burp Suite Community (the `product=community` URL from the previous example), the installer ignores it and uses the pinned default, printing a notice when it can detect the old line (an unquoted line is cut at the `&` when the file is read, so it is already effectively unset and no notice appears); remove that line to be sure.

If you change the CTFd admin password in CTFd, change `CTFD_ADMIN_PASSWORD` in `challsmith.env` too and rerun `sudo ./install.sh`, otherwise the web app can no longer reach CTFd. Installs from before the web app left a stale `/opt/challsmith/api` directory; the installer does not delete it, so you can remove it by hand.

### Company network

Ubuntu apt, Docker Hub, pip, npm, apk, Go modules and the GitHub release downloads all go through company proxies. Set these in `challsmith.env`:

| Key | Purpose |
|---|---|
| `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` | apt, the Docker daemon, the GitHub release downloads of the Pulumi plugin and oras, and the golang build container of the scenarios. `localhost`, `127.0.0.1` and `registry` are always added to `NO_PROXY`. |
| `DOCKER_REGISTRY_MIRROR` | Docker Hub proxy address, written to `registry-mirrors` in `/etc/docker/daemon.json`. |
| `GOPROXY` | The company Go module mirror (Artifactory or Nexus style), for example `https://artifactory.example/api/go/go-remote`. Used when building the scenarios. If the mirror host is internal, add it to `NO_PROXY`. |
| `GOSUMDB` | Optional checksum database, for example `sum.golang.org https://<mirror>/sumdb/sum.golang.org` when the mirror proxies it, or `off` only if the company requires it. Empty keeps Go's default. |

With a mirror in `GOPROXY`, nothing in the scenario build needs `storage.googleapis.com` (the public proxy redirects some modules there, a mirror does not). The build container also runs with `GOTOOLCHAIN=local`, so Go never downloads a toolchain: a `go.mod` newer than the `golang:1.27-alpine` image fails the build instead. On the dev VM only (not part of the install), a native `go` older than `go.mod` downloads a toolchain for `go test`, which also goes to `storage.googleapis.com`; use the golang container shown below instead.

The proxy is never passed to the stack's service containers or to challenge containers (compose sets every proxy variable to empty, and the scenarios do the same for challenge containers), so a challenge instance cannot reach or be steered through the company proxy.

The installer downloads two files from GitHub releases and verifies them against the checksum file published next to them: the Pulumi docker provider plugin (installed into the Pulumi home of chall-manager, volume `cm-pulumi`; pulumi-docker publishes SHA-1) and the oras binary 1.4.0 (SHA-256). With the proxy variables set, these downloads need no further configuration.

To override the download, set `PULUMI_DOCKER_PLUGIN` or `ORAS_TARBALL` to a different URL or to an absolute local file path. A URL is verified against the checksum file in the same directory. For a local file, set `PULUMI_DOCKER_CHECKSUMS` or `ORAS_CHECKSUMS` to a local checksum file, otherwise verification is skipped with a warning. The checksum file comes from the same host as the download, so this check detects corruption but not a compromised host.

The plugin version is read from `infra/scenarios/go.mod` (pulumi-docker v5.3.0), and a plugin you supply yourself must be that version.

The php-fpm base images that need PECL extensions are not built here, because the company has no PECL proxy. Build them outside and pull them through the Docker Hub proxy.

## Authoring challenges

Open `http://127.0.0.1:3000` in the VM's browser and log in with `WEB_ADMIN_USER` and `WEB_ADMIN_PASSWORD`.

1. Create: choose a slug (lowercase letters, digits and `-`, at most 48 characters), a name and a template. The app creates the challenge with the template's files.
2. Edit: change the settings (category, tags, description, points, flag, protocol, resource limits, services) and the files. Files live under `services/<service>/`, and a service without an `image` is built from its `Dockerfile`. You can edit a file in the browser, or upload a file or a `.zip` into a service folder. A file with mixed or lone-CR line endings, or one that is not UTF-8, is read-only in the editor; edit it by uploading a replacement.
3. Publish: the app builds the service images, pushes them to `localhost:5000` and creates the CTFd challenge, or updates the same one if it was published before. A service that uses an official image (for example `mariadb:11.8`) is copied to `localhost:5000/challsmith/mirror/<name>:<tag>`.
   Publishing writes the build-context files as `0644` and directories as `0755`, so run scripts with `sh script` or `chmod +x` them in the `Dockerfile`.
4. Read the publish log, which shows the docker output. If a build or push fails, publishing stops there, CTFd is not touched and the published version stays as it was.

A challenge is `draft` (never published), `modified` (changed since the last publish) or `published`. Deleting a challenge also deletes its CTFd challenge and instances. Publishing a challenge whose CTFd challenge was deleted by hand creates a new one. Every instance gets its flag in the `FLAG` environment variable, see "How the image reads the flag".

### Templates

| Template | Scenario | Contents |
|---|---|---|
| `php` | single | PHP 8.6 built-in web server, one container |
| `nginx-php-db` | multi | nginx, PHP-FPM and MariaDB, three containers |
| `python-flask` | single | Python 3.15 and Flask web app, one container |
| `node-nextjs` | single | Next.js 16 App Router app on Node.js 26, one container |
| `tcp` | single | TCP service served by socat, one container, category Pwn |

### PHP challenges with PECL extensions

A PHP challenge that needs PECL extensions (redis, mongodb, apcu, imagick) or many bundled ones, or that simply wants to skip install steps, can use `FROM csftech/php-ext:8.3-fpm-alpine`. Use a fixed tag such as `csftech/php-ext:8.3.37-fpm-alpine3.24` to pin a patch version. The images are built in [challsmith-base-images](https://github.com/csftech/challsmith-base-images) and pulled through the Docker Hub proxy.

- php-fpm is not configured for you. If PHP reads `FLAG`, add `clear_env = no` yourself, as the `nginx-php-db` template does.
- The 8.6 image currently has no redis, apcu or imagick, because they do not compile on PHP 8.6 yet.

## Git and backup

Both are on the Sync page of the web app.

- Settings: the remote URL (`https://`, `http://`, `file://` or a local path), user name, access token, branch (default `main`) and the directory in the repository (default `challenges`). The token is stored in the web app's database and the api never returns it. git runs through the company proxy from `challsmith.env`.
- Export to git: commits every challenge as `<directory>/<slug>/` and pushes. The comparison base of each challenge (the state at the last sync) moves only when the push succeeded, or when there was nothing to commit. If the push fails, or you export without pushing, the base stays, so a later import cannot let the old copy in git silently overwrite your changes.
- Import: run a preview first, from the git repository or from an uploaded backup archive. Each challenge gets one of five states, from the database, the source and the base:

| State | Meaning | Apply does |
|---|---|---|
| `new` | Only in the source | Creates it |
| `unchanged` | Same in both | Moves the base (git only) |
| `source_changed` | Only the source changed | Overwrites the database |
| `db_changed` | Only the database changed | Nothing |
| `conflict` | Both changed | You choose `source` or `db` for each one, and apply is refused until you do |

  A challenge that fails validation is shown as `invalid` and skipped. Apply refuses if a challenge changed after the preview.
- Download backup: a `.tar.gz` of all challenges. It does not move the comparison base, because the file may never be imported anywhere. Importing a backup does not move it either: the base follows git only (git export and git import), so a backup can carry content older than the base, and moving the base to it would let a later git import overwrite newer content without asking. Applying a backup writes the content you chose and leaves the base as it was.

## Cleanup before release

Before exporting the VM for trainees, open the Cleanup page of the web app and type `CLEANUP`, or run `sudo ./cleanup.sh` as `aps` (or root), which asks for the same confirmation. It deletes:

- every chall-manager instance, and leftover `challenge-*` containers and networks;
- every CTFd user that is not an admin;
- every web app session, so you are logged out.

It keeps the challenges, the images in the registry, the git settings and the CTFd admin account.

## Create a challenge manually

1. Build the challenge image and push it to the local registry, for example `docker build -t localhost:5000/challsmith/my-chall:v1 .` and `docker push localhost:5000/challsmith/my-chall:v1`. Run these as `aps` (or another docker group user). The `tests/e2e/fixtures/` directory has working challenges.
2. In CTFd, go to Admin, then Challenges, then create a challenge of type `dynamic_iac`. Fill in name, category, description and points as usual.
3. Set the scenario to `registry:5000/challsmith/scenarios/single:v1` or `registry:5000/challsmith/scenarios/multi:v1`.
4. Add the `additional` keys from the tables below. The image in `image` or `services` is the one pushed in step 1, referenced as `localhost:5000/...`.
5. Do not add a static flag. The plugin accepts both the static flag and the instance flag, so a static flag would let everyone pass with the same string.

### How the image reads the flag

Every container gets the environment variable `FLAG`, for example `APS{php_strcmp_array_3f9a1c07e2b84d65}`: the template body, an underscore and the instance identity (chall-manager's 64-bit random value). Two instances practically never get the same flag, however short the template is, the flag stays the same while the instance lives, and an admin can tell from a submitted flag which instance it belongs to. The image must not contain the flag. Its entrypoint or code reads `FLAG` at start, for example writing it to `/flag.txt` or into a database. In a multi challenge every service receives `FLAG`, and a `FLAG` set in the `env` of a service is overridden. The flag differs per instance, including after the same trainee deletes and reopens an instance.

### Keys for single

| Key | Meaning | Default |
|---|---|---|
| `image` | Full image reference, for example `localhost:5000/challsmith/my-chall:v1` | required |
| `flag` | Flag template body, for example `php_strcmp_array` | required |
| `port` | Service port inside the container (1-65535) | `80` |
| `protocol` | `http` gives `http://localhost:<port>`, `tcp` gives `nc localhost <port>` | `http` |
| `flag_prefix` | Outer flag format, giving `APS{...}` | `APS` |
| `memory` | Memory limit, an integer with suffix `m` or `g`, for example `256m`, `1g` | `256m` |
| `cpus` | CPU limit, a number greater than 0 | `0.5` |

### Keys for multi

`flag`, `flag_prefix`, `protocol`, `memory` and `cpus` work as in single, and the limits apply to each container. `services` is required and is a JSON string holding a list:

```json
[
  {"name": "web", "image": "localhost:5000/challsmith/sqli-1-web:ab12", "port": 80, "entry": true},
  {"name": "php", "image": "localhost:5000/challsmith/sqli-1-php:ab12"},
  {"name": "db",  "image": "mariadb:11", "env": {"MARIADB_ROOT_PASSWORD": "x"}}
]
```

| Service field | Meaning |
|---|---|
| `name` | Required. Lowercase letters, digits and `-`, unique. Also the network alias the other services connect to. |
| `image` | Required. |
| `entry` | Exactly one service must be `true`. Only it is published, on a random port bound to 127.0.0.1. |
| `port` | Required for the entry service (1-65535). |
| `env` | Optional extra environment variables. |

## Tests

Unit tests for the scenarios, run in the same container image the build uses:

```
docker run --rm -v "$PWD/infra/scenarios:/src" -w /src golang:1.27-alpine go test ./...
```

End-to-end tests run on the installed VM as `aps`. They build and push the images in `tests/e2e/fixtures/`, create instances through the CTFd API, and drive the web app on port 3000 (create, edit, publish, republish, a failing build, login and Origin checks, backup and import preview). The runner reads `WEB_ADMIN_USER` and `WEB_ADMIN_PASSWORD` from `challsmith.env`. The cleanup test deletes every trainee and web session, so it runs last in its own pytest, and the runner then checks that no `challenge-*` container is left:

```
tests/e2e/run.sh
```

The runner's pip gets its proxy from the `proxies` section of the Docker client config (`~/.docker/config.json`) of `aps`. If you set one there, its `noProxy` must include `localhost` and `127.0.0.1`, otherwise the tests send CTFd traffic to the proxy.

The `ops` isolation check runs as root. It fails if `ops` can connect to any service or instance container, to chall-manager, to the registry or to the web app on 127.0.0.1:3000, if `aps` cannot reach the web app, if a container on a temporary `challenge-isocheck` network can reach any platform service, or if `ops` cannot reach CTFd and the published instance ports:

```
sudo tests/ops-isolation.sh
```

## Known limitations

1. Instances do not survive a VM reboot or a Docker restart, on purpose. Docker may give a restarted container a new host port, which would leave CTFd showing a dead connection URL. So instance containers are created with restart policy `no`, and at boot and whenever Docker (re)starts, `challsmith-boot-reset.service` (installed and enabled by `install.sh`, script `infra/boot/reset-instances.sh`) waits up to five minutes for the api and chall-manager, then runs `cleanup.sh --instances-only --yes`: every chall-manager instance and leftover `challenge-*` container and network is deleted, while CTFd users and web sessions are kept. A trainee opens a new instance afterwards, and its flag changes. Right after boot, wait until the reset has finished (`systemctl status challsmith-boot-reset`) before opening instances, because one started during the reset may be deleted. A failure of the unit is logged in the journal (`journalctl -u challsmith-boot-reset`) and does not stop other services.
2. php single-container challenges use `php -S`, which is single-threaded. That is fine for one trainee per VM.
3. Anyone with the vmdk can get root. Dynamic flags only stop trainees from copying each other's flags. The writeup and the oral check are the real control.
4. An import preview is kept in the api's memory for 30 minutes, so after the api restarts you must run the preview again.
5. The web app answers only to the Host names in `WEB_ALLOWED_HOSTS` (default `localhost:3000,127.0.0.1:3000`), which stops DNS rebinding. If you reach the VM by another name, add it in `challsmith.env` (comma separated); any other Host gets 421.
6. The web app has one account, and it signs in to CTFd with the CTFd admin account, so the two passwords must be kept in step.

## Troubleshooting

When instance creation fails, CTFd shows only "Scenario does not match specification.". The real error is in chall-manager:

```
cd /opt/challsmith
docker compose -p challsmith logs chall-manager
docker compose -p challsmith exec chall-manager ls /var/lib/pulumi/logs
```

The Pulumi logs are in the `cm-pulumi` volume, mounted at `/var/lib/pulumi` in chall-manager. Typical causes are a wrong `additional` key (the scenario reports which one), an image that was not pushed to `localhost:5000`, and a missing Pulumi docker plugin.

## Security notes

- `ops` is not in the docker group. `/opt/challsmith` is mode 750 and `challsmith.env` is 600.
- chall-manager mounts `docker.sock`, which is root-equivalent on the VM. The VM is meant for throwaway training use only.
- Every published port binds to 127.0.0.1, so the services and instances are not reachable from the network.
- The VM itself can reach the container networks, so `ops` is blocked by an nftables table `inet challsmith_ops` (`/etc/challsmith/ops-firewall.nft`, loaded at boot by `challsmith-ops-firewall.service`). It rejects all `ops` traffic into the Docker bridges (`docker0`, `br-*`, including the per-instance networks) and to the registry port 5000 and the web app port 3000 on loopback. `ops` still reaches CTFd on 127.0.0.1:8000 and the instance ports, which go through Docker's root-owned port proxy. Without this, `ops` could call the unauthenticated chall-manager API and read every instance flag, read the CTFd sessions in redis, or push a scenario to the registry that chall-manager would run with `docker.sock`.
- The firewall fails closed: `challsmith-ops-firewall.service` expires the `ops` account before loading the rules and unlocks it only after they loaded, so `ops` cannot log in if the load fails (`aps` is not affected). Docker keeps the per-instance `challenge-*` networks apart from the compose network; `tests/ops-isolation.sh` verifies it.
- Before exporting the VM, run the cleanup (see "Cleanup before release"). `sudo ./cleanup.sh` runs the cleanup CLI in the `api` container and asks for confirmation.
- Web app login: one account from `challsmith.env`, checked in constant time. A session is a random token in an `HttpOnly`, `SameSite=Strict` cookie that lasts 12 hours, and only its BLAKE3 hash is stored, so the database cannot be used to log in. The browser talks only to `web`, which calls `api` for it, and `api` checks the session on every endpoint except login, so `web` is not the only guard. Writes need an `Origin` whose host equals the request's `Host`, and that `Host` must be in `WEB_ALLOWED_HOSTS` (a request with any other `Host` is refused), and the `/api/auth/*` routes cannot be reached from the browser.
- `api` mounts `docker.sock`, so a login to the web app is root-equivalent on the VM. The firewall therefore blocks `ops` from port 3000 as well, and if the firewall fails to load, the `ops` account stays expired.
- The firewall relies on Docker's userland proxy (the default). With `"userland-proxy": false` in `daemon.json`, loopback traffic to published ports is routed into the bridges and `ops` loses CTFd too, so keep the default.

[繁體中文](README_ZH-TW.md)

# challsmith

challsmith is a CTFd training environment that runs on one Ubuntu 26.04 VM. It is installed once, exported as a vmdk and handed to new hires, who solve web challenges in their own copy. CTFd runs with the ctfd-chall-manager plugin, and every challenge instance is started on demand by chall-manager as Docker containers. Each instance gets its own dynamic flag.

Only the infrastructure and the two generic scenarios exist so far. The web app for authors is planned, so challenges are created by hand in the CTFd admin UI (see "Create a challenge manually").

## Architecture

```
Ubuntu 26.04 VM
├─ ops (trainee) ── browser ──> CTFd 127.0.0.1:8000 ──> challenge instance 127.0.0.1:<random port>
│                          └──> Burp Suite Community
└─ aps (docker group)
   └─ docker compose project "challsmith" (restart: unless-stopped)
      ├─ ctfd                  CTFd 3.8.9 + ctfd-chall-manager plugin v0.10.1, 127.0.0.1:8000
      ├─ ctfd-db / ctfd-redis  mariadb 11.8 / redis 8.10-alpine
      ├─ ctfd-setup            one-shot, creates the CTFd admin and plugin settings
      ├─ chall-manager         v0.6.7, mounts /var/run/docker.sock, no published port
      ├─ chall-manager-janitor removes expired instances every minute
      └─ registry              registry 3.1, 127.0.0.1:5000, challenge images and scenarios
```

All published ports bind to 127.0.0.1, and a firewall keeps `ops` away from the containers and the registry (see "Security notes"). Challenge images and scenarios are pushed to `localhost:5000`; chall-manager pulls them as `registry:5000/...`.

The two scenarios are written in Go (Go 1.27, pulumi-docker v5.3.0) and are built and pushed to the registry as OCI artifacts by `install.sh`:

- `registry:5000/challsmith/scenarios/single:v1` starts one container.
- `registry:5000/challsmith/scenarios/multi:v1` starts several containers on a per-instance Docker network, with one entry service.

## Install

You need an Ubuntu 26.04 Desktop VM with internet access, directly or through the company proxies.

1. Copy the repository to the VM, then `cp challsmith.env.example challsmith.env` and edit it. The admin name, email and password are required. `CTFD_SECRET_KEY` and `CTFD_DB_PASSWORD` are generated when left empty. `CM_MANA_TOTAL` is the per-user mana limit (default 5).
2. Run `sudo ./install.sh`. It is safe to re-run. It installs Docker, writes the Docker daemon proxy settings, creates the users `aps` (docker group) and `ops` (an existing `ops` is removed from the docker, sudo, adm and lxd groups), installs the `ops` firewall, copies the repository to `/opt/challsmith`, starts the compose project, builds and pushes the scenarios, and installs Burp Suite Community.
3. Set the passwords: `sudo passwd aps` and `sudo passwd ops`.
4. Open `http://127.0.0.1:8000` and log in with the admin account from `challsmith.env`.

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

The plugin version is read from `scenarios/go.mod` (pulumi-docker v5.3.0), and a plugin you supply yourself must be that version.

The php-fpm base images that need PECL extensions are not built here, because the company has no PECL proxy. Build them outside and pull them through the Docker Hub proxy.

## Create a challenge manually

1. Build the challenge image and push it to the local registry, for example `docker build -t localhost:5000/challsmith/my-chall:v1 .` and `docker push localhost:5000/challsmith/my-chall:v1`. Run these as `aps` (or another docker group user). The `examples/` directory has working challenges.
2. In CTFd, go to Admin, then Challenges, then create a challenge of type `dynamic_iac`. Fill in name, category, description and points as usual.
3. Set the scenario to `registry:5000/challsmith/scenarios/single:v1` or `registry:5000/challsmith/scenarios/multi:v1`.
4. Add the `additional` keys from the tables below. The image in `image` or `services` is the one pushed in step 1, referenced as `localhost:5000/...`.
5. Do not add a static flag. The plugin accepts both the static flag and the instance flag, so a static flag would let everyone pass with the same string.

### How the image reads the flag

Every container gets the environment variable `FLAG`, for example `CTF{php_strcmp_array_...}`. The image must not contain the flag. Its entrypoint or code reads `FLAG` at start, for example writing it to `/flag.txt` or into a database. In a multi challenge every service receives `FLAG`, and a `FLAG` set in the `env` of a service is overridden. The flag differs per instance, including after the same trainee deletes and reopens an instance.

### Keys for single

| Key | Meaning | Default |
|---|---|---|
| `image` | Full image reference, for example `localhost:5000/challsmith/my-chall:v1` | required |
| `flag` | Flag template body, for example `php_strcmp_array` | required |
| `port` | Service port inside the container (1-65535) | `80` |
| `protocol` | `http` gives `http://localhost:<port>`, `tcp` gives `nc localhost <port>` | `http` |
| `flag_prefix` | Outer flag format, giving `CTF{...}` | `CTF` |
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
docker run --rm -v "$PWD/scenarios:/src" -w /src golang:1.27-alpine go test ./...
```

End-to-end tests run on the installed VM as `aps`. They build and push the images in `examples/`, then create instances through the CTFd API:

```
tests/e2e/run.sh
```

The runner's pip gets its proxy from the `proxies` section of the Docker client config (`~/.docker/config.json`) of `aps`. If you set one there, its `noProxy` must include `localhost` and `127.0.0.1`, otherwise the tests send CTFd traffic to the proxy.

The `ops` isolation check runs as root. It fails if `ops` can connect to any service or instance container, to chall-manager or to the registry, or cannot reach CTFd and the published instance ports:

```
sudo tests/ops-isolation.sh
```

## Known limitations

1. After a VM reboot the instance containers come back, but Docker may assign a new host port (observed 32776 to 32768). CTFd still shows the old connection URL, so the trainee must delete the instance and open a new one.
2. php single-container challenges use `php -S`, which is single-threaded. That is fine for one trainee per VM.
3. Anyone with the vmdk can get root. Dynamic flags only stop trainees from copying each other's flags. The writeup and the oral check are the real control.

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
- The VM itself can reach the container networks, so `ops` is blocked by an nftables table `inet challsmith_ops` (`/etc/challsmith/ops-firewall.nft`, loaded at boot by `challsmith-ops-firewall.service`). It rejects all `ops` traffic into the Docker bridges (`docker0`, `br-*`, including the per-instance networks) and to the registry port 5000 on loopback. `ops` still reaches CTFd on 127.0.0.1:8000 and the instance ports, which go through Docker's root-owned port proxy. Without this, `ops` could call the unauthenticated chall-manager API and read every instance flag, read the CTFd sessions in redis, or push a scenario to the registry that chall-manager would run with `docker.sock`.
- The firewall relies on Docker's userland proxy (the default). With `"userland-proxy": false` in `daemon.json`, loopback traffic to published ports is routed into the bridges and `ops` loses CTFd too, so keep the default.

[English](README.md)

# challsmith

challsmith 是跑在一台 Ubuntu 26.04 VM 上的 CTFd 訓練環境，安裝一次後匯出成 vmdk 發給新人，新人在自己的副本上解 web 題。CTFd 搭配 ctfd-chall-manager plugin，每個題目 instance 都由 chall-manager 在需要時以 Docker container 啟動，並且各自擁有動態 flag。

目前只完成基礎架構與兩個通用 scenario。給出題者使用的 web app 還在規劃中，所以題目要在 CTFd 管理介面手動建立（見「手動建立題目」）。

## 系統架構

```
Ubuntu 26.04 VM
├─ ops（新人）── 瀏覽器 ──> CTFd 127.0.0.1:8000 ──> 題目 instance 127.0.0.1:<隨機 port>
│                      └──> Burp Suite Community
└─ aps（docker 群組）
   └─ docker compose 專案 challsmith（restart: unless-stopped）
      ├─ ctfd                  CTFd 3.8.9 + ctfd-chall-manager plugin v0.10.1，127.0.0.1:8000
      ├─ ctfd-db / ctfd-redis  mariadb 11.8 / redis 8.10-alpine
      ├─ ctfd-setup            一次性，建立 CTFd 管理者與 plugin 設定
      ├─ chall-manager         v0.6.7，掛載 /var/run/docker.sock，不對外發布 port
      ├─ chall-manager-janitor 每分鐘回收逾時的 instance
      └─ registry              registry 3.1，127.0.0.1:5000，存題目 image 與 scenario
```

所有對外的 port 都只綁在 127.0.0.1，另有防火牆擋住 `ops` 連往 container 與 registry（見「安全注意事項」）。題目 image 與 scenario 推到 `localhost:5000`，chall-manager 則以 `registry:5000/...` 拉取。

兩個 scenario 以 Go 撰寫（Go 1.27、pulumi-docker v5.3.0），由 `install.sh` build 並以 OCI artifact 推到 registry：

- `registry:5000/challsmith/scenarios/single:v1` 啟動單一 container。
- `registry:5000/challsmith/scenarios/multi:v1` 在每個 instance 專屬的 Docker network 上啟動多個 container，其中一個是入口服務。

## 安裝

需要一台 Ubuntu 26.04 Desktop VM，能直接或經由公司 proxy 連上網路。

1. 把 repo 複製到 VM，執行 `cp challsmith.env.example challsmith.env` 後編輯。管理者的名稱、email 與密碼必填。`CTFD_SECRET_KEY` 與 `CTFD_DB_PASSWORD` 留空時會自動產生。`CM_MANA_TOTAL` 是每位使用者的 mana 上限，預設為 5。
2. 執行 `sudo ./install.sh`，可以重複執行。它會安裝 Docker、寫入 Docker daemon 的 proxy 設定、建立使用者 `aps`（docker 群組）與 `ops`（已存在的 `ops` 會被移出 docker、sudo、adm 與 lxd 群組）、安裝 `ops` 的防火牆、把 repo 複製到 `/opt/challsmith`、啟動 compose 專案、build 並推送 scenario，最後安裝 Burp Suite Community。
3. 設定密碼：`sudo passwd aps` 與 `sudo passwd ops`。
4. 開啟 `http://127.0.0.1:8000`，用 `challsmith.env` 裡的管理者帳號登入。

### 公司網路

Ubuntu apt、Docker Hub、pip、npm、apk、Go module 與 GitHub release 的下載，在公司內都要經過 proxy。請在 `challsmith.env` 設定：

| 設定 | 用途 |
|---|---|
| `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` | apt、Docker daemon、從 GitHub release 下載 Pulumi plugin 與 oras，以及 build scenario 的 golang 容器。`localhost`、`127.0.0.1` 與 `registry` 一律會加進 `NO_PROXY`。 |
| `DOCKER_REGISTRY_MIRROR` | Docker Hub proxy 位址，寫入 `/etc/docker/daemon.json` 的 `registry-mirrors`。 |
| `GOPROXY` | 公司的 Go module mirror（Artifactory 或 Nexus 類型），例如 `https://artifactory.example/api/go/go-remote`，build scenario 時使用。如果 mirror 的主機在內網，請把它加進 `NO_PROXY`。 |
| `GOSUMDB` | 選填的 checksum 資料庫，例如 mirror 有代理時可設為 `sum.golang.org https://<mirror>/sumdb/sum.golang.org`，只有公司要求時才設為 `off`。留空則使用 Go 的預設值。 |

`GOPROXY` 指向 mirror 時，build scenario 的過程不需要連到 `storage.googleapis.com`（公開的 proxy 會把部分 module 轉址到那裡，mirror 不會）。build 容器也以 `GOTOOLCHAIN=local` 執行，Go 不會下載 toolchain，所以 `go.mod` 比 `golang:1.27-alpine` image 新時，build 會直接失敗。只有在開發用 VM 上（不屬於安裝流程），本機的 `go` 若比 `go.mod` 舊，執行 `go test` 會下載 toolchain，這個下載同樣會連到 `storage.googleapis.com`，請改用下方的 golang 容器。

proxy 絕不會傳給本專案的服務容器或題目容器（compose 把所有 proxy 變數設為空值，scenario 也對題目容器做同樣的事），因此題目 instance 無法連到公司 proxy，也不會被導向 proxy。

安裝程式會從 GitHub release 下載兩個檔案，並用旁邊的 checksum 檔驗證：Pulumi docker provider plugin（裝進 chall-manager 的 Pulumi home，也就是 volume `cm-pulumi`，pulumi-docker 只提供 SHA-1）與 oras 1.4.0（SHA-256）。設好 proxy 變數後，這兩個下載不需要其他設定。

如果要改用別的來源，把 `PULUMI_DOCKER_PLUGIN` 或 `ORAS_TARBALL` 設成另一個 URL 或本機檔案的絕對路徑。URL 會用同目錄的 checksum 檔驗證。本機檔案則要把 `PULUMI_DOCKER_CHECKSUMS` 或 `ORAS_CHECKSUMS` 設成本機的 checksum 檔，否則會略過驗證並顯示警告。checksum 檔與下載檔來自同一個主機，所以這項檢查只能發現檔案損毀，無法防範主機本身被入侵。

plugin 版本從 `scenarios/go.mod` 讀取（pulumi-docker v5.3.0），自行提供的 plugin 也必須是這個版本。

需要 PECL extension 的 php-fpm base image 不在這裡 build，因為公司內沒有 PECL proxy。請在公司外先包好，再透過 Docker Hub proxy 拉取。

## 手動建立題目

1. 先 build 題目 image 並推到本機 registry，例如 `docker build -t localhost:5000/challsmith/my-chall:v1 .` 與 `docker push localhost:5000/challsmith/my-chall:v1`，用 `aps`（或其他 docker 群組的使用者）執行。`examples/` 目錄裡有可以直接使用的題目。
2. 在 CTFd 進入 Admin、Challenges，建立類型為 `dynamic_iac` 的題目，名稱、分類、說明與分數照一般題目填寫。
3. scenario 填 `registry:5000/challsmith/scenarios/single:v1` 或 `registry:5000/challsmith/scenarios/multi:v1`。
4. 依下面的表格填入 `additional` 的鍵。`image` 或 `services` 裡的 image 就是步驟 1 推送的那個，以 `localhost:5000/...` 表示。
5. 不要建立靜態 flag。plugin 會同時接受靜態 flag 與 instance 的 flag，建立靜態 flag 之後，所有人都能用同一個字串過關。

### 題目 image 怎麼讀 flag

每個 container 都會拿到環境變數 `FLAG`，例如 `CTF{php_strcmp_array_...}`。image 裡不能包含 flag，由 entrypoint 或程式在啟動時讀取 `FLAG`，例如寫成 `/flag.txt` 或寫進資料庫。multi 題目的每個服務都會拿到 `FLAG`，服務的 `env` 裡若也設了 `FLAG` 會被覆蓋。每個 instance 的 flag 都不同，同一位新人刪掉 instance 再重開，也會拿到新的 flag。

### single 的鍵

| 鍵 | 說明 | 預設 |
|---|---|---|
| `image` | 完整的 image 位置，例如 `localhost:5000/challsmith/my-chall:v1` | 必填 |
| `flag` | flag 範本的內文，例如 `php_strcmp_array` | 必填 |
| `port` | container 內部的服務 port（1-65535） | `80` |
| `protocol` | `http` 產生 `http://localhost:<port>`，`tcp` 產生 `nc localhost <port>` | `http` |
| `flag_prefix` | flag 外層的格式，結果為 `CTF{...}` | `CTF` |
| `memory` | 記憶體上限，整數加上 `m` 或 `g`，例如 `256m`、`1g` | `256m` |
| `cpus` | CPU 上限，大於 0 的數字 | `0.5` |

### multi 的鍵

`flag`、`flag_prefix`、`protocol`、`memory` 與 `cpus` 的意義同 single，資源上限套用在每個 container。`services` 必填，內容是一個放著清單的 JSON 字串：

```json
[
  {"name": "web", "image": "localhost:5000/challsmith/sqli-1-web:ab12", "port": 80, "entry": true},
  {"name": "php", "image": "localhost:5000/challsmith/sqli-1-php:ab12"},
  {"name": "db",  "image": "mariadb:11", "env": {"MARIADB_ROOT_PASSWORD": "x"}}
]
```

| 服務欄位 | 說明 |
|---|---|
| `name` | 必填，只能用小寫字母、數字與 `-`，不可重複，同時也是其他服務連線用的 network alias。 |
| `image` | 必填。 |
| `entry` | 必須剛好有一個服務設為 `true`，只有它會對外發布，port 隨機分配並綁在 127.0.0.1。 |
| `port` | 入口服務必填（1-65535）。 |
| `env` | 選填，額外的環境變數。 |

## 測試

scenario 的單元測試，在 build 用的同一個 container image 裡執行：

```
docker run --rm -v "$PWD/scenarios:/src" -w /src golang:1.27-alpine go test ./...
```

端對端測試在已安裝的 VM 上以 `aps` 執行，會先 build 並推送 `examples/` 的 image，再透過 CTFd API 建立 instance：

```
tests/e2e/run.sh
```

測試程式裡的 pip 會從 `aps` 的 Docker client 設定（`~/.docker/config.json` 的 `proxies` 區段）取得 proxy。如果在那裡設了 proxy，`noProxy` 必須包含 `localhost` 與 `127.0.0.1`，否則測試連 CTFd 的流量會被送到 proxy。

`ops` 隔離檢查以 root 執行。只要 `ops` 連得到任何服務或 instance 的 container、chall-manager 或 registry，或是連不到 CTFd 與 instance 的對外 port，檢查就會失敗：

```
sudo tests/ops-isolation.sh
```

## 已知限制

1. VM 重開機後，instance 的 container 會自動回來，但 Docker 可能分配新的對外 port（實測從 32776 變成 32768）。CTFd 仍顯示舊的連線網址，所以新人必須刪除 instance 再重新開一個。
2. php 單一 container 的題目使用 `php -S`，它是單執行緒，一台 VM 只有一位新人使用時沒有問題。
3. 拿到 vmdk 的人都能取得 root，動態 flag 只能防止新人互相抄 flag，真正的管控方式是 writeup 與口頭確認。

## 疑難排解

建立 instance 失敗時，CTFd 只會顯示「Scenario does not match specification.」，真正的錯誤訊息在 chall-manager：

```
cd /opt/challsmith
docker compose -p challsmith logs chall-manager
docker compose -p challsmith exec chall-manager ls /var/lib/pulumi/logs
```

Pulumi 的 log 放在 `cm-pulumi` volume，也就是 chall-manager 內的 `/var/lib/pulumi`。常見原因有 `additional` 的鍵填錯（scenario 會指出是哪一個）、image 沒有推到 `localhost:5000`，以及沒有安裝 Pulumi docker plugin。

## 安全注意事項

- `ops` 不在 docker 群組，`/opt/challsmith` 的權限是 750，`challsmith.env` 是 600。
- chall-manager 掛載了 `docker.sock`，等同於這台 VM 的 root 權限，所以這台 VM 只適合拿來做用完即丟的訓練。
- 所有對外的 port 都只綁在 127.0.0.1，從網路連不到服務與 instance。
- VM 本身連得到 container 的網路，所以用 nftables 的 `inet challsmith_ops` 表擋住 `ops`（`/etc/challsmith/ops-firewall.nft`，開機時由 `challsmith-ops-firewall.service` 載入）。它拒絕 `ops` 送進 Docker bridge（`docker0`、`br-*`，包含每個 instance 專屬的 network）的所有流量，以及送往 loopback 上 registry port 5000 的流量。`ops` 仍然連得到 127.0.0.1:8000 的 CTFd 與 instance 的 port，因為這些連線經過 Docker 以 root 執行的 port proxy。少了這道防火牆，`ops` 就能呼叫不需登入的 chall-manager API 讀到每個 instance 的 flag、讀取 redis 裡的 CTFd session，或是推一個 scenario 到 registry，讓 chall-manager 帶著 `docker.sock` 執行。
- 這道防火牆要靠 Docker 預設的 userland proxy 才能運作。如果在 `daemon.json` 設了 `"userland-proxy": false`，loopback 上連往對外 port 的流量會被轉進 bridge，`ops` 連 CTFd 也會被擋，所以請維持預設值。

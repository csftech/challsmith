[English](README.md)

# challsmith

challsmith 是跑在一台 Ubuntu 26.04 VM 上的 CTFd 訓練環境，安裝一次後匯出成 vmdk 發給新人，新人在自己的副本上解 web 題。CTFd 搭配 ctfd-chall-manager plugin，每個題目 instance 都由 chall-manager 在需要時以 Docker container 啟動，並且各自擁有動態 flag。

出題者在 `http://127.0.0.1:3000` 的 web app 裡製作題目：選範本、編輯檔案、發佈，由 app 建置 image 並建立 CTFd 題目（見「出題流程」）。題目仍然可以在 CTFd 管理介面手動建立（見「手動建立題目」）。

## 系統架構

```
Ubuntu 26.04 VM
├─ ops（新人）── 瀏覽器 ──> CTFd 127.0.0.1:8000 ──> 題目 instance 127.0.0.1:<隨機 port>
│                      └──> Burp Suite
└─ aps（docker 群組）
   │  （出題者）瀏覽器 ──> web app 127.0.0.1:3000 ──> api ──> CTFd、registry、docker
   └─ docker compose 專案 challsmith（restart: unless-stopped）
      ├─ ctfd                  CTFd 3.8.9 + ctfd-chall-manager plugin v0.10.1，127.0.0.1:8000
      ├─ ctfd-db / ctfd-redis  mariadb 11.8 / redis 8.10-alpine
      ├─ ctfd-setup            一次性，建立 CTFd 管理者與 plugin 設定
      ├─ chall-manager         v0.6.7，掛載 /var/run/docker.sock，不對外發布 port
      ├─ chall-manager-janitor 每分鐘回收逾時的 instance
      ├─ web                   出題用的 web app（Next.js 16），127.0.0.1:3000，是通往 api 的唯一入口
      ├─ api                   FastAPI 後端，掛載 /var/run/docker.sock，不對外發布 port
      ├─ app-db                postgres 19-alpine，存放 web app 的題目、session 與設定
      └─ registry              registry 3.1，127.0.0.1:5000，存題目 image 與 scenario
```

所有對外的 port 都只綁在 127.0.0.1，另有防火牆擋住 `ops` 連往 container 與 registry（見「安全注意事項」）。題目 image 與 scenario 推到 `localhost:5000`，chall-manager 則以 `registry:5000/...` 拉取。

兩個 scenario 以 Go 撰寫（Go 1.27、pulumi-docker v5.3.0），由 `install.sh` build 並以 OCI artifact 推到 registry：

- `registry:5000/challsmith/scenarios/single:v1` 啟動單一 container。
- `registry:5000/challsmith/scenarios/multi:v1` 在每個 instance 專屬的 Docker network 上啟動多個 container，其中一個是入口服務。

## 安裝

需要一台 Ubuntu 26.04 Desktop VM，能直接或經由公司 proxy 連上網路。

1. 把 repo 複製到 VM，執行 `cp challsmith.env.example challsmith.env` 後編輯。CTFd 管理者的名稱、email 與密碼必填，web app 的密碼 `WEB_ADMIN_PASSWORD` 也必填（`WEB_ADMIN_USER` 是它的帳號，預設為 `admin`）。`CTFD_SECRET_KEY`、`CTFD_DB_PASSWORD` 與 `APP_DB_PASSWORD`（web app 的 PostgreSQL）留空時會自動產生。web app 以 CTFd 的管理者帳號登入 CTFd。`CM_MANA_TOTAL` 是每位使用者的 mana 上限，預設為 0，代表不限制（見下方說明）。
2. 執行 `sudo ./install.sh`，可以重複執行。它會安裝 Docker、寫入 Docker daemon 的 proxy 設定、建立使用者 `aps`（docker 群組）與 `ops`（已存在的 `ops` 會被移出 docker、sudo、adm 與 lxd 群組）、安裝 `ops` 的防火牆、把 repo 複製到 `/opt/challsmith`、啟動 compose 專案、build 並推送 scenario，最後安裝 Burp Suite（PortSwigger 的合併版安裝程式，版本由 `BURP_VERSION` 固定，並以 SHA-256 驗證）。沒有授權時它會以 Community 模式執行，這是 PortSwigger 的行為，維護者應在桌面上確認。舊版安裝在 `/opt/BurpSuiteCommunity`，安裝程式不會動它，可以自行刪除。
3. 設定密碼：`sudo passwd aps` 與 `sudo passwd ops`。
4. 開啟 `http://127.0.0.1:8000`，用 `challsmith.env` 裡的管理者帳號登入 CTFd。web app 在 `http://127.0.0.1:3000`，帳密是 `WEB_ADMIN_USER` 與 `WEB_ADMIN_PASSWORD`。

預設不限制 mana：`CM_MANA_TOTAL=0` 時 CTFd plugin 會忽略 mana，新人可以同時開任意數量題目的 instance。web app 裡每個題目的 `mana` 欄位（預設 0）只有在 `CM_MANA_TOTAL` 設為正整數時才有作用，此時同一位使用者所有執行中 instance 的 mana 總和不能超過它。既有的安裝是從舊範例複製了 `CM_MANA_TOTAL=5`，請在 `challsmith.env` 改成 `0` 並重新執行 `sudo ./install.sh` 來解除限制。

如果 `challsmith.env` 裡還留著舊範例的 Burp Suite Community 下載網址 `BURP_DOWNLOAD_URL`（`product=community` 那一行），安裝程式會忽略它並改用固定的預設網址，偵測得到舊那一行時會顯示提示（沒有加引號的那一行，讀檔時會在 `&` 被截斷，本來就等於沒設定，所以不會有提示）；把那一行刪掉最保險。

如果在 CTFd 裡改了管理者密碼，要把 `challsmith.env` 的 `CTFD_ADMIN_PASSWORD` 一併改掉，再重新執行 `sudo ./install.sh`，否則 web app 會連不上 CTFd。在 web app 推出之前安裝的環境，會留下過時的 `/opt/challsmith/api` 目錄，安裝程式不會刪除它，可以自行手動移除。

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

plugin 版本從 `infra/scenarios/go.mod` 讀取（pulumi-docker v5.3.0），自行提供的 plugin 也必須是這個版本。

需要 PECL extension 的 php-fpm base image 不在這裡 build，因為公司內沒有 PECL proxy。請在公司外先包好，再透過 Docker Hub proxy 拉取。

## 出題流程

在 VM 的瀏覽器開啟 `http://127.0.0.1:3000`，以 `WEB_ADMIN_USER` 與 `WEB_ADMIN_PASSWORD` 登入。

1. 建立：填入 slug（小寫字母、數字與 `-`，最長 48 個字元）、名稱並選一個範本，app 會用範本的檔案建立題目。
2. 編輯：修改題目的設定（分類、標籤、說明、分數、flag、protocol、資源上限、服務）與檔案。檔案放在 `services/<service>/` 底下，沒有設定 `image` 的服務會用它的 `Dockerfile` build。可以直接在瀏覽器編輯檔案，也可以把檔案或 `.zip` 上傳到服務的資料夾。換行符號混用或只有 CR 的檔案，以及不是 UTF-8 的檔案，在編輯器裡是唯讀的，請上傳新檔案來取代。
3. 發佈：app 會 build 各服務的 image 並推到 `localhost:5000`，然後建立 CTFd 題目，如果之前發佈過，就更新同一個題目。使用官方 image 的服務（例如 `mariadb:11.8`）會複製到 `localhost:5000/challsmith/mirror/<名稱>:<tag>`。
   發佈時 build context 裡的檔案權限是 `0644`、資料夾是 `0755`，所以腳本要用 `sh script` 執行，或在 `Dockerfile` 裡 `chmod +x`。
4. 查看發佈 log，裡面有 docker 的輸出。build 或 push 失敗時，發佈會停在那一步，不會動到 CTFd，已發佈的版本維持原樣。

題目的狀態有 `draft`（從未發佈）、`modified`（上次發佈後有修改）與 `published`。刪除題目時，它在 CTFd 的題目與 instance 也會一併刪除，而如果 CTFd 上的題目被手動刪掉，再發佈時會建立新的題目。每個 instance 的 flag 都放在環境變數 `FLAG`，見「題目 image 怎麼讀 flag」。

### 範本

| 範本 | scenario | 內容 |
|---|---|---|
| `php` | single | PHP 8.6 內建 web server，單一 container |
| `nginx-php-db` | multi | nginx、PHP-FPM 與 MariaDB，三個 container |
| `python-flask` | single | Python 3.15 與 Flask web app，單一 container |
| `node-nextjs` | single | Node.js 26 上的 Next.js 16 App Router app，單一 container |
| `tcp` | single | 以 socat 提供的 TCP 服務，單一 container，分類為 Pwn |

## git 與備份

兩者都在 web app 的同步頁面。

- 設定：要填遠端網址（`https://`、`http://`、`file://` 或本機路徑）、使用者名稱、access token、分支（預設 `main`）與 repo 內的目錄（預設 `challenges`）。token 存在 web app 的資料庫裡，api 不會把它回傳，而 git 的連線會經過 `challsmith.env` 設定的公司 proxy。
- 匯出到 git：把每個題目提交成 `<目錄>/<slug>/` 並推送。每個題目的比對基準（上次同步時的狀態）只有在推送成功，或是沒有東西需要提交時，才會移動。推送失敗，或是只匯出而不推送時，基準維持不變，所以之後匯入時，git 上的舊版不會默默蓋掉你的修改。
- 匯入：先預覽，來源可以是 git repo，也可以是上傳的備份壓縮檔。系統會依資料庫、來源與基準，把每個題目歸入五種狀態之一：

| 狀態 | 意思 | 套用時 |
|---|---|---|
| `new` | 只存在於來源 | 建立題目 |
| `unchanged` | 兩邊相同 | 移動基準（僅限 git） |
| `source_changed` | 只有來源改過 | 以來源覆蓋資料庫 |
| `db_changed` | 只有資料庫改過 | 不做任何事 |
| `conflict` | 兩邊都改過 | 每個題目都要選 `source` 或 `db`，沒選就不能套用 |

  驗證不通過的題目會顯示為 `invalid` 並被略過。預覽之後如果有題目被改動，套用會被拒絕。
- 下載備份：把所有題目打包成 `.tar.gz`。它不會移動比對基準，因為這個檔案可能根本不會被匯入到任何地方。匯入備份也不會移動基準，因為基準只跟著 git（git 匯出與 git 匯入）走。備份裡可能是比基準更舊的內容，如果基準跟著移過去，之後從 git 匯入時，就會不經詢問地用舊版覆蓋掉較新的內容。套用備份只會寫入你選擇的內容，基準維持原樣。

## 發佈前清理

要把 VM 匯出給新人之前，請開啟 web app 的清理頁面並輸入 `CLEANUP`，或以 `aps`（或 root）執行 `sudo ./cleanup.sh`，它會要求相同的確認。清理會刪除：

- 所有 chall-manager 的 instance，以及殘留的 `challenge-*` container 與網路。
- 所有不是管理者的 CTFd 使用者。
- 所有 web app 的 session，所以你也會被登出。

題目、registry 裡的 image、git 設定與 CTFd 管理者帳號都會保留。

## 手動建立題目

1. 先 build 題目 image 並推到本機 registry，例如 `docker build -t localhost:5000/challsmith/my-chall:v1 .` 與 `docker push localhost:5000/challsmith/my-chall:v1`，用 `aps`（或其他 docker 群組的使用者）執行。`tests/e2e/fixtures/` 目錄裡有可以直接使用的題目。
2. 在 CTFd 進入 Admin、Challenges，建立類型為 `dynamic_iac` 的題目，名稱、分類、說明與分數照一般題目填寫。
3. scenario 填 `registry:5000/challsmith/scenarios/single:v1` 或 `registry:5000/challsmith/scenarios/multi:v1`。
4. 依下面的表格填入 `additional` 的鍵。`image` 或 `services` 裡的 image 就是步驟 1 推送的那個，以 `localhost:5000/...` 表示。
5. 不要建立靜態 flag。plugin 會同時接受靜態 flag 與 instance 的 flag，建立靜態 flag 之後，所有人都能用同一個字串過關。

### 題目 image 怎麼讀 flag

每個 container 都會拿到環境變數 `FLAG`，例如 `APS{php_strcmp_array_3f9a1c07e2b84d65}`，格式是 flag 範本、底線，再接上 instance 的 identity（chall-manager 產生的 64 位元亂數）。不論 flag 範本多短，不同 instance 拿到相同 flag 的機率都極低，instance 存在期間 flag 也不會變，管理者還能從提交的 flag 看出它屬於哪個 instance。image 裡不能包含 flag，由 entrypoint 或程式在啟動時讀取 `FLAG`，例如寫成 `/flag.txt` 或寫進資料庫。multi 題目的每個服務都會拿到 `FLAG`，服務的 `env` 裡若也設了 `FLAG` 會被覆蓋。每個 instance 的 flag 都不同，同一位新人刪掉 instance 再重開，也會拿到新的 flag。

### single 的鍵

| 鍵 | 說明 | 預設 |
|---|---|---|
| `image` | 完整的 image 位置，例如 `localhost:5000/challsmith/my-chall:v1` | 必填 |
| `flag` | flag 範本的內文，例如 `php_strcmp_array` | 必填 |
| `port` | container 內部的服務 port（1-65535） | `80` |
| `protocol` | `http` 產生 `http://localhost:<port>`，`tcp` 產生 `nc localhost <port>` | `http` |
| `flag_prefix` | flag 外層的格式，結果為 `APS{...}` | `APS` |
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
docker run --rm -v "$PWD/infra/scenarios:/src" -w /src golang:1.27-alpine go test ./...
```

端對端測試在已安裝的 VM 上以 `aps` 執行，會先 build 並推送 `tests/e2e/fixtures/` 的 image，透過 CTFd API 建立 instance，並操作 3000 port 的 web app（建立、編輯、發佈、重新發佈、build 失敗、登入與 Origin 檢查、備份與匯入預覽）。執行程式會從 `challsmith.env` 讀取 `WEB_ADMIN_USER` 與 `WEB_ADMIN_PASSWORD`。清理測試會刪除所有新人與 web session，所以最後才以獨立的 pytest 執行，之後執行程式會檢查是否還有 `challenge-*` container 殘留：

```
tests/e2e/run.sh
```

測試程式裡的 pip 會從 `aps` 的 Docker client 設定（`~/.docker/config.json` 的 `proxies` 區段）取得 proxy。如果在那裡設了 proxy，`noProxy` 必須包含 `localhost` 與 `127.0.0.1`，否則測試連 CTFd 的流量會被送到 proxy。

`ops` 隔離檢查以 root 執行。只要 `ops` 連得到任何服務或 instance 的 container、chall-manager 或 registry，或是連得到 127.0.0.1:3000 的 web app，或是 `aps` 連不到 web app，或是暫時的 `challenge-isocheck` 網路上的 container 連得到任何平台服務，或是 `ops` 連不到 CTFd 與 instance 的對外 port，檢查就會失敗：

```
sudo tests/ops-isolation.sh
```

## 已知限制

1. instance 不會在 VM 重開機或 Docker 重新啟動後保留，這是刻意的設計。Docker 可能替重新啟動的 container 分配新的對外 port，CTFd 就會顯示失效的連線網址。因此 instance 的 container 以重啟策略 `no` 建立，開機以及每次 Docker 啟動時，由 `challsmith-boot-reset.service`（`install.sh` 會安裝並啟用，腳本是 `infra/boot/reset-instances.sh`）最多等五分鐘，等 api 與 chall-manager 就緒後執行 `cleanup.sh --instances-only --yes`，刪除所有 chall-manager instance 與殘留的 `challenge-*` container 和 network，CTFd 使用者與 web 登入狀態則保留。新人事後重新開一個 instance 即可，flag 也會跟著改變。剛開機時請先等重設完成（用 `systemctl status challsmith-boot-reset` 確認）再開 instance，因為重設期間開的 instance 可能被刪掉。這個 unit 失敗時會記錄在 journal（`journalctl -u challsmith-boot-reset`），不會影響其他服務。
2. php 單一 container 的題目使用 `php -S`，它是單執行緒，一台 VM 只有一位新人使用時沒有問題。
3. 拿到 vmdk 的人都能取得 root，動態 flag 只能防止新人互相抄 flag，真正的管控方式是 writeup 與口頭確認。
4. 匯入預覽存在 api 的記憶體中，保留 30 分鐘，所以 api 重新啟動後，必須重新預覽。
5. web app 只回應 `WEB_ALLOWED_HOSTS` 列出的 Host 名稱（預設為 `localhost:3000,127.0.0.1:3000`），目的是防止 DNS rebinding。如果要用別的名稱連到這台 VM，請在 `challsmith.env` 加上該名稱（以逗號分隔），其他 Host 會收到 421。
6. web app 只有一個帳號，而且它以 CTFd 的管理者帳號登入 CTFd，所以兩邊的密碼必須同步。

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
- VM 本身連得到 container 的網路，所以用 nftables 的 `inet challsmith_ops` 表擋住 `ops`（`/etc/challsmith/ops-firewall.nft`，開機時由 `challsmith-ops-firewall.service` 載入）。它拒絕 `ops` 送進 Docker bridge（`docker0`、`br-*`，包含每個 instance 專屬的 network）的所有流量，以及送往 loopback 上 registry port 5000 與 web app port 3000 的流量。`ops` 仍然連得到 127.0.0.1:8000 的 CTFd 與 instance 的 port，因為這些連線經過 Docker 以 root 執行的 port proxy。少了這道防火牆，`ops` 就能呼叫不需登入的 chall-manager API 讀到每個 instance 的 flag、讀取 redis 裡的 CTFd session，或是推一個 scenario 到 registry，讓 chall-manager 帶著 `docker.sock` 執行。
- 防火牆採失敗即關閉：`challsmith-ops-firewall.service` 先讓 `ops` 帳號過期，規則載入成功後才解鎖，所以載入失敗時 `ops` 無法登入（`aps` 不受影響）。Docker 會把每個 instance 專屬的 `challenge-*` 網路與 compose 網路隔開，`tests/ops-isolation.sh` 會驗證這點。
- 匯出 VM 之前，請先執行清理（見「發佈前清理」）。`sudo ./cleanup.sh` 會在 `api` container 內執行清理指令並要求確認。
- web app 的登入：只有 `challsmith.env` 裡的一個帳號，以固定時間比對。session 是放在 `HttpOnly`、`SameSite=Strict` cookie 裡的隨機 token，效期 12 小時，資料庫只存它的 BLAKE3 雜湊值，所以拿到資料庫也無法登入。瀏覽器只會連到 `web`，由 `web` 代為呼叫 `api`，而 `api` 除了登入以外的每個端點都會自己驗證 session，所以擋住請求的並不是只有 `web`。寫入請求的 `Origin` 其 host 必須與請求的 `Host` 相同，而且這個 `Host` 必須在 `WEB_ALLOWED_HOSTS` 內，`Host` 不在其中的請求會被拒絕，瀏覽器也無法連到 `/api/auth/*` 這些路由。
- `api` 掛載了 `docker.sock`，所以登入 web app 就等於取得這台 VM 的 root 權限。因此防火牆同樣擋住 `ops` 連往 3000 port，而且防火牆載入失敗時，`ops` 帳號會維持過期狀態。
- 這道防火牆要靠 Docker 預設的 userland proxy 才能運作。如果在 `daemon.json` 設了 `"userland-proxy": false`，loopback 上連往對外 port 的流量會被轉進 bridge，`ops` 連 CTFd 也會被擋，所以請維持預設值。

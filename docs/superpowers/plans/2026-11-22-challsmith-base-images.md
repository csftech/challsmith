# challsmith 第 3 部分：php base images 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 建立 GitHub repo `csftech/challsmith-base-images`，以 GitHub Actions build「所有 extension 都裝好」的 php-fpm alpine image（全部可編譯的內建 extension，加上 PECL 的 redis、mongodb、apcu、imagick），推到 Docker Hub 的 `csftech/php-ext`，讓公司內的出題作者透過 Docker Hub proxy 拉取，在題目 Dockerfile 裡當 base 使用。

**Architecture：** 一份設定檔 `images.yml` 列出每個 php 版本的 base tag、別名、要編譯的內建 extension，以及各 PECL extension 的固定版本。`scripts/matrix.py` 驗證設定並產生 GitHub Actions 的 build matrix，同一個 `php/Dockerfile` 以 build args 產生每個版本的 image。CI 先 build 並跑冒煙測試，只有在 `main` 上的 push 或手動觸發時才推送。

**Tech Stack：** Docker（BuildKit）、GitHub Actions（`docker/setup-buildx-action`、`docker/login-action`、`docker/build-push-action`）、Python（`matrix.py` 與 pytest）、PyYAML、shell。

**Spec：** `docs/superpowers/specs/2026-11-21-challsmith-design.md` 第 10 節。使用者在 2026-11-22 補充的決定：repo 名稱 `challsmith-base-images`；Docker Hub 帳號 `csftech`；php 版本 7.4、8.1、8.3、8.6；PECL extension 為 redis、mongodb、apcu、imagick；內建 extension 全部預裝；只做一種「全部都裝」的 image，不分標準版與完整版；image 名稱 `csftech/php-ext`。

**本計畫不包含：** 其他語言的 base image（repo 名稱保留了空間，但第一版只有 php）、多架構 image（VM 只有 amd64）。

## Global Constraints

- 新 repo 放在本機 `D:/projects/challsmith-base-images`，GitHub 上是 `csftech/challsmith-base-images`，公開 repo。不可出現 VM 的 IP、帳密、任何 `.env` 內容或 Docker Hub token。
- image 名稱：`csftech/php-ext`。每個版本推兩個 tag：
  - 固定的 `<php 版本>-fpm-<alpine 版本>`，例如 `8.3.37-fpm-alpine3.24`
  - 會移動的別名 `<別名>-fpm-alpine`，例如 `8.3-fpm-alpine`
- base image 一律用官方 `php:<php 版本>-fpm-<alpine 版本>`。
- php 版本：7.4、8.1、8.3、8.6，每個都固定到確切的修補版與 alpine 版本，用官方 image 目前提供的最新組合。2026-11-22 查到的是 `8.6.0-fpm-alpine3.24`、`8.3.37-fpm-alpine3.24`、`8.1.34-fpm-alpine3.22`、`7.4.33-fpm-alpine3.16`。8.1 與 7.4 已經停止支援，官方 image 不再出新的 alpine 版本，就用它們最後一個 tag，不自己編譯 php。開工時重新查一次，有更新的組合就用更新的。
- PECL extension：redis、mongodb、apcu、imagick。每個 php 版本各自固定 extension 的版本，選 PECL 上支援該 php 版本的最新穩定版。開工時查證並記在 report。
- 內建 extension：每個 php 版本都裝上 base image 中 `docker-php-ext-install` 能編譯的全部 extension，只排除 `oci8`、`pdo_oci`（需要 Oracle 專有的 Instant Client）與 `zend_test`、`dl_test`（php 自己的測試用 extension）。已經編譯在官方 image 裡的（例如 `PDO`、`pdo_sqlite`、`sqlite3`、`mysqlnd`）不需要再裝。可編譯的清單依 php 版本不同（例如 `imap`、`pspell` 在 8.4 之後已經從 php 移除），所以 `images.yml` 每個版本各列一份，並由 Task 2 的檢查確保清單和 base image 實際提供的一致。
- 版本原則：有 LTS 的用最新 LTS，沒有的用最新穩定版，`.0` 也可以；全部固定確切版本。GitHub Actions 的 action 一律用 commit SHA 固定，後面註解版本號。
- 只產生 `linux/amd64`。
- Docker Hub token 只放在 GitHub repo secret `DOCKERHUB_TOKEN`，由使用者自己設定。帳號名稱取自 `images.yml` 的 `namespace`。workflow 只用 `pull_request` 觸發 PR 的 build，不用 `pull_request_target`。PR 的 build 拿不到 secret，也不推送。
- 換行一律 LF（`.gitattributes` 寫 `* text=auto eol=lf`），shell script 在 git 裡的 mode 要是 100755。
- `README.md`（英文）與 `README_ZH-TW.md`（繁體中文）內容一致，開頭互相連結。中文版寫完用 `py "C:/Users/csf/.claude/skills/zh-tw-writing/scripts/check_zh.py" README_ZH-TW.md` 檢查。
- 本機 build 與測試在使用者的開發 VM 上進行（有 Docker、可以直接連外網）。不讀取 challsmith repo 根目錄的 `.env`，一律用控制者提供的 SSH 包裝腳本。
- commit 訊息結尾加上 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Review Focus

- 設定檔替某個 php 版本固定了不支援它的 extension 版本，例如 mongodb 2.x 搭配 php 7.4。這時 build 必須失敗並看得出原因，不能默默跳過這個 extension，或改裝別的版本（Task 2 的冒煙測試會比對實際載入的 extension 版本）。
- 移除 build 相依套件時，順便刪掉了 extension 執行時需要的函式庫，例如 imagick 依賴的 ImageMagick、pgsql 依賴的 libpq、gd 依賴的 libpng 與 libjpeg。php 這時不會停止，只會在啟動時印出 `Unable to load dynamic library` 的警告，然後繼續跑。冒煙測試必須把任何 PHP Warning 或 startup 錯誤都當成失敗（Task 2）。
- 從 fork 送來的 PR 不能拿到 secret，也不能推送到 Docker Hub（Task 3 的 workflow 結構檢查）。
- 兩筆設定使用同一個別名，或別名不是 php 版本的前綴時，會用比較舊的修補版覆蓋會移動的 tag。設定檔驗證必須拒絕這種情況（Task 1 的測試）。
- 更新 php 版本之後，新版多了或少了可編譯的內建 extension，但設定檔沒跟著改，「全部都裝」就不再成立；或者設定檔列了新版已經移除的 extension，build 就會失敗。這兩種情況都要由檢查明確指出差異（Task 2 的 `tests/check-bundled.sh`）。
- 公司內只能透過 Docker Hub proxy 拉取，所以 image 必須是公開的 `docker.io` image，在 challsmith VM 上用一般的 `docker pull` 就能拿到（Task 5 的驗證）。

---

## 檔案結構

```
challsmith-base-images/
├─ .gitattributes / .gitignore              Task 1
├─ images.yml                                Task 1（namespace、image、各版本的 base tag、別名、內建 extension 清單、PECL 版本）
├─ scripts/matrix.py                         Task 1（驗證設定、產生 build matrix）
├─ tests/test_matrix.py                      Task 1
├─ tests/run-unit.sh                         Task 1（在 python alpine container 跑 pytest）
├─ php/Dockerfile                            Task 2
├─ tests/smoke.sh                            Task 2（檢查一個 image：extension 載入、版本、無警告、php-fpm 設定）
├─ tests/check-bundled.sh                    Task 2（比對設定檔的內建清單和 base image 實際可編譯的清單）
├─ scripts/build-local.sh                    Task 2（依 images.yml 在本機 build 並跑 smoke）
├─ .github/workflows/build.yml               Task 3
├─ README.md / README_ZH-TW.md               Task 4
└─（challsmith repo）README.md / README_ZH-TW.md  Task 4（加一段如何使用 csftech/php-ext）
```

---

### Task 1：repo 骨架、設定檔與 matrix 產生器

**Files:**
- Create：`.gitattributes`、`.gitignore`、`images.yml`、`scripts/matrix.py`、`tests/test_matrix.py`、`tests/run-unit.sh`

**Interfaces:**
- Produces：
  - `images.yml` 的格式：

    ```yaml
    namespace: csftech
    image: php-ext
    images:
      - php: "8.3.37"          # 官方 base tag 的 php 版本部分
        alpine: "alpine3.24"   # 官方 base tag 的 alpine 部分
        alias: "8.3"           # 產生 <alias>-fpm-alpine 的移動 tag
        bundled:               # 用 docker-php-ext-install 編譯的內建 extension（全部可編譯的，扣除排除清單）
          [bcmath, bz2, calendar, exif, gd, gettext, gmp, intl, ldap, mysqli, opcache, pdo_dblib,
           pdo_mysql, pdo_pgsql, pgsql, soap, sockets, xsl, zip]   # 只示範格式，實際清單在開工時由 check-bundled 產生
        extensions:            # PECL 套件名稱: 固定版本
          redis: "6.3.0"
          mongodb: "2.1.4"
          apcu: "5.1.27"
          imagick: "3.8.1"
    ```

    上面的數字只示範格式。實際版本在開工時查證，條件見 Global Constraints。
  - `scripts/matrix.py`：
    - `load(path: str) -> dict`
    - `validate(cfg: dict) -> None`：違反規則時 raise `ValueError`，訊息要指出是哪一筆、哪個欄位。
    - `matrix(cfg: dict) -> dict`：回傳 `{"include": [{"php", "alpine", "base", "tags", "extensions", "expect"}]}`。
      - `base` 是 `php:<php>-fpm-<alpine>`。
      - `tags` 是逗號分隔的兩個完整 tag。
      - `bundled` 是空白分隔的內建 extension 名稱，交給 `docker-php-ext-install`。
      - `extensions` 是空白分隔的 `name-version`，可以直接交給 `pecl install`。
      - `expect` 是空白分隔的 `name=version`，給冒煙測試比對 PECL 版本用。
    - 命令列用法：`python scripts/matrix.py images.yml` 印出一行 JSON。
  - 驗證規則：
    - `namespace`、`image` 必須符合 Docker 名稱規則 `^[a-z0-9]+(?:[._-][a-z0-9]+)*$`。
    - `images` 不能是空的。
    - `php` 必須符合 `^\d+\.\d+\.\d+$`，`alpine` 必須符合 `^alpine\d+\.\d+$`。
    - `alias` 必須是 `php` 的「主版本.次版本」，例如 `8.3.37` 只能用 `8.3`。
    - `php` 不能重複，`alias` 也不能重複。
    - `extensions` 至少要有一個。名稱只能是 `^[a-z0-9_]+$`，版本只能是 `^\d+\.\d+\.\d+$`。
    - `bundled` 至少要有一個，名稱只能是 `^[a-z0-9_]+$`，不能重複，不能包含 `oci8`、`pdo_oci`、`zend_test`、`dl_test`，也不能和 `extensions` 的名稱重疊。
  - `tests/run-unit.sh`：在 VM 上以 `python:3.15-alpine` container 安裝固定版本的 PyYAML 與 pytest，再執行 `pytest tests/test_matrix.py`。

- [ ] **Step 1：寫失敗的測試** `tests/test_matrix.py`：
  - `test_matrix_for_one_image`：給一筆 `php: "8.3.37"`、`alpine: "alpine3.24"`、`alias: "8.3"`、`bundled: [pdo_mysql, gd]`、`extensions: {redis: "6.3.0", apcu: "5.1.27"}`，`namespace: csftech`、`image: php-ext`。結果完全等於：

    ```python
    {"include": [{
        "php": "8.3.37",
        "alpine": "alpine3.24",
        "base": "php:8.3.37-fpm-alpine3.24",
        "tags": "csftech/php-ext:8.3.37-fpm-alpine3.24,csftech/php-ext:8.3-fpm-alpine",
        "bundled": "pdo_mysql gd",
        "extensions": "redis-6.3.0 apcu-5.1.27",
        "expect": "redis=6.3.0 apcu=5.1.27",
    }]}
    ```

  - `test_validate_rejects`：參數化，以下每一種都 raise `ValueError`：
    - 重複的 `php`
    - 重複的 `alias`
    - `alias` 填 `8.2`，但 `php` 是 `8.3.37`
    - `php` 填 `8.3`
    - `alpine` 填 `3.24`
    - extension 版本填 `latest`
    - extension 名稱填 `Redis`
    - `extensions` 是空的
    - `bundled` 是空的
    - `bundled` 包含 `oci8`
    - `bundled` 有重複
    - `bundled` 和 `extensions` 都有 `redis`
    - `images` 是空的
    - `namespace` 填 `CSF`
  - `test_repo_config_is_valid`：`validate(load("images.yml"))` 不 raise，四個 php 版本的「主版本.次版本」分別是 7.4、8.1、8.3、8.6，每個版本都有 redis、mongodb、apcu、imagick 四個 PECL extension，而且 `bundled` 都包含 `pdo_mysql`、`mysqli`、`pdo_pgsql`、`pgsql`、`pdo_dblib`、`gd`、`zip`、`intl`、`bcmath`、`exif`、`sockets`、`soap`、`xsl`、`opcache`。
  - `test_cli_prints_json`：用 subprocess 執行 `python scripts/matrix.py images.yml`，輸出可以被 `json.loads` 解析，而且有 4 筆 `include`。
- [ ] **Step 2：執行 `tests/run-unit.sh`**，預期因為 `scripts/matrix.py` 不存在而失敗。
- [ ] **Step 3：查證並填好 `images.yml` 的實際版本，實作 `scripts/matrix.py`。**
- [ ] **Step 4：重跑 `tests/run-unit.sh`**，預期全部通過。
- [ ] **Step 5：`git init`，用 `git update-index --chmod=+x` 設定 shell script 的執行權限，commit** `feat: image config and build matrix generator`

### Task 2：Dockerfile、內建清單檢查與冒煙測試

**Files:**
- Create：`php/Dockerfile`、`tests/smoke.sh`、`tests/check-bundled.sh`、`scripts/build-local.sh`

**Interfaces:**
- Consumes：`scripts/matrix.py` 的 `matrix` 輸出（Task 1）。
- Produces：
  - `php/Dockerfile` 的 build args：`BASE`（例如 `php:8.3.37-fpm-alpine3.24`）、`BUNDLED`（例如 `pdo_mysql gd ...`）與 `PECL_EXTENSIONS`（例如 `redis-6.3.0 mongodb-2.1.4 apcu-5.1.27 imagick-3.8.1`）。做法：
    - `FROM ${BASE}`。
    - 先用 `docker-php-ext-configure` 設定需要參數的 extension，例如 gd 開啟 freetype、jpeg、webp，imap 開啟 kerberos 與 ssl（只在清單裡有 imap 的版本執行）；再用 `docker-php-ext-install -j$(nproc) ${BUNDLED}` 編譯全部內建 extension。各 extension 需要的 `-dev` 套件一律放進 `.build-deps`。
    - 用 `apk add --virtual .build-deps` 安裝 `$PHPIZE_DEPS` 與各 extension 需要的 `-dev` 套件，然後 `pecl install ${PECL_EXTENSIONS}`，再對每個 extension 執行 `docker-php-ext-enable`。
    - 用 `scanelf` 找出 `.so` 實際需要的執行期函式庫，以 `apk add --virtual .run-deps` 保留下來，再 `apk del .build-deps`，並清掉 pecl 的暫存檔。
    - 不改 `php-fpm` 的設定，例如不加 `clear_env`，那屬於題目自己的 Dockerfile。
    - 加上 OCI label：`org.opencontainers.image.source=https://github.com/csftech/challsmith-base-images`，以及 `org.opencontainers.image.description`。
  - `tests/check-bundled.sh <base> <bundled>`：在 base image 裡列出 `/usr/src/php/ext` 中可以用 `docker-php-ext-install` 編譯的 extension（先執行 `docker-php-source extract`），扣掉已經編譯在 base image 裡的（`php -m` 已經列出的）與排除清單，和 `<bundled>` 比對。兩邊不一致時，印出「base 有但設定沒列」和「設定有但 base 沒有」兩份清單，並以非 0 結束。
  - `tests/smoke.sh <image> <expect> <bundled>`，`<expect>` 與 `<bundled>` 是 matrix 的同名欄位。以下任何一項失敗就以非 0 結束：
    1. `docker run --rm <image> php -m` 的結果包含每個 PECL extension 與每個內建 extension（`opcache` 列在 `[Zend Modules]` 底下，名稱是 `Zend OPcache`，也算數），而且 stdout 與 stderr 都沒有 `Warning`、`Unable to load`、`startup` 這些字。
    2. 對每個 `name=version`，`php -r 'echo phpversion("<name>");'` 的輸出完全等於 version。
    3. 實際用一次每個 extension，不需要連到服務：
       - `new Redis();`
       - `new MongoDB\Driver\Manager("mongodb://127.0.0.1:1");`
       - `php -d apc.enable_cli=1 -r 'var_dump(apcu_enabled());'` 輸出 `bool(true)`
       - `count((new Imagick())->queryFormats("PNG")) > 0`
    4. `php-fpm -t` 成功。
  - `scripts/build-local.sh [php 版本]`：讀 `images.yml`，對每一筆（或指定的那一筆）先跑 `tests/check-bundled.sh`，再執行 `docker build --build-arg BASE=... --build-arg BUNDLED=... --build-arg PECL_EXTENSIONS=... -t <第一個 tag> php/`，然後跑 `tests/smoke.sh`，最後印出每個 image 的大小。

- [ ] **Step 0：寫 `tests/check-bundled.sh`，對四個 base image 各執行一次，把輸出的「base 有但設定沒列」清單填進 `images.yml` 的 `bundled`，直到四個版本都通過。** report 裡記下每個版本最後的清單與數量。
- [ ] **Step 1：先寫 `tests/smoke.sh`**，用官方 `php:8.3-fpm-alpine` 執行，預期失敗，因為 extension 不存在。另外用 `php -d extension=nonexistent.so` 製造一個 `Unable to load` 的警告，確認 smoke 會把它判成失敗，證明警告檢查有效。
- [ ] **Step 2：寫 `php/Dockerfile` 與 `scripts/build-local.sh`。**
- [ ] **Step 3：在 VM 上執行 `scripts/build-local.sh`**，預期四個版本都 build 成功、smoke 全部通過，並記下每個 image 的大小。
- [ ] **Step 4：反向驗證 Review Focus 第一點**：暫時把 7.4 的 mongodb 改成 2.x 版，執行 `scripts/build-local.sh 7.4`，預期 build 失敗，而且錯誤訊息看得出是 mongodb 不支援這個 php 版本。驗證完改回原本的設定，report 裡記下錯誤訊息。
- [ ] **Step 4b：反向驗證「全部都裝」的檢查**：暫時從 8.3 的 `bundled` 刪掉 `zip`，執行 `tests/check-bundled.sh`，預期失敗並列出 `zip`；再暫時加上 `imap` 到 8.6，預期失敗並列出 `imap`。驗證完改回。
- [ ] **Step 5：commit** `feat: php-fpm image with all extensions and smoke test`

### Task 3：GitHub Actions workflow

**Files:**
- Create：`.github/workflows/build.yml`

**Interfaces:**
- Consumes：`scripts/matrix.py`、`php/Dockerfile`、`tests/smoke.sh`。
- Produces：workflow `build`
  - 觸發：`push` 到 `main`、`pull_request`、`workflow_dispatch`。
  - `permissions: contents: read`。`concurrency` 以 `${{ github.workflow }}-${{ github.ref }}` 分組，新的一次執行會取消舊的。
  - job `matrix`：checkout，安裝固定版本的 PyYAML，執行 `python scripts/matrix.py images.yml`，把結果寫進 `$GITHUB_OUTPUT`。
  - job `build`：`needs: matrix`，`strategy.matrix` 取自上一步的輸出，`fail-fast: false`。步驟如下：
    1. checkout
    2. setup-buildx
    3. 用 build-push-action 以 `load: true` build，tag 用 matrix 的 `tags`，`platforms: linux/amd64`，cache 用 GitHub Actions cache（`type=gha`，scope 用 php 版本區分）
    4. 執行 `tests/check-bundled.sh` 與 `tests/smoke.sh`
    5. 只有在 `github.event_name != 'pull_request'` 而且 `github.ref == 'refs/heads/main'` 時，才 login，再以相同的 tag 推送。登入帳號是 `images.yml` 的 `namespace`（由 matrix job 一併輸出），密碼是 `secrets.DOCKERHUB_TOKEN`。
  - 所有 action 都用 commit SHA 固定版本，後面註解版本號，例如 `actions/checkout@<sha> # v5.x.x`。

- [ ] **Step 1：寫 `build.yml`。**
- [ ] **Step 2：在 VM 上用固定版本的 `rhysd/actionlint` image 檢查**，預期沒有錯誤。
- [ ] **Step 3：結構檢查**：寫 `tests/test_workflow.py`，用 PyYAML 讀 workflow，加進 `tests/run-unit.sh` 一起跑。斷言以下幾點：
  - 觸發條件不含 `pull_request_target`。
  - 每個 `uses:` 都是 `owner/repo@<40 位 hex>`。
  - 用到 `secrets.` 的步驟，以及推送步驟，都帶有上面那個只在 `main` 上執行的 `if` 條件。
  - `permissions` 只有 `contents: read`。

  預期全部通過。
- [ ] **Step 4：commit** `ci: build, smoke-test and push the images`

### Task 4：README

**Files:**
- Create：`README.md`、`README_ZH-TW.md`（challsmith-base-images）
- Modify：challsmith repo 的 `README.md`、`README_ZH-TW.md`

**Interfaces:**
- Consumes：前面所有 task 的檔名、指令與 tag 規則。

- [ ] **Step 1：寫 challsmith-base-images 的兩份 README**，內容包括：
  - 這個 repo 的用途，以及為什麼要在公司外 build：公司內沒有 PECL proxy，而且預先裝好全部 extension，題目 Dockerfile 不必再各自安裝。
  - image 與 tag 列表，從 `images.yml` 整理成表格：php 版本、固定 tag、移動 tag、PECL extension 版本；另外列出每個版本的內建 extension 清單，以及排除了哪些、為什麼排除。
  - 在題目 Dockerfile 裡的用法，例如 `FROM csftech/php-ext:8.3-fpm-alpine`。另外說明要鎖定特定修補版時，改用固定 tag。
  - 新增版本或 extension 的步驟：只改 `images.yml`，必要時在 Dockerfile 補上 `-dev` 套件，送 PR，合併後 CI 自動推送。
  - 本機 build 的方式：`scripts/build-local.sh`。
  - 需要的 GitHub secret：`DOCKERHUB_TOKEN`。這是 Docker Hub 的 access token，權限要有 Read & Write，由維護者用 `gh secret set` 設定。
  - image 的大小：全部 extension 與 imagick 會讓 image 明顯變大，寫出 Task 2 實測的大小。
- [ ] **Step 2：在 challsmith 的兩份 README 加一小段**：需要 PECL extension 或想省掉安裝步驟的 php 題目，可以改用 `csftech/php-ext` 當 base，並附上 repo 連結。php-fpm 題目要記得自己加 `clear_env = no`，做法同 nginx-php-db 範本。
- [ ] **Step 3：執行 zh-TW 檢查腳本**，修正真正的問題，並在 report 中說明保留的提醒各是基於什麼理由。
- [ ] **Step 4：兩個 repo 各自 commit**，訊息為 `docs: README`，challsmith 那邊是 `docs: point php challenges at csftech/php-ext`。

### Task 5：建立 GitHub repo、設定 secret、第一次發佈

這個 task 有三個對外的動作，每一個都要先徵得使用者同意：建立公開 repo、推送程式碼、第一次推送到 Docker Hub。

**Files:** 無新增，只有 git remote 與 GitHub 上的設定。

- [ ] **Step 1：控制者確認使用者同意後，用 gh 建立公開 repo**：`gh repo create csftech/challsmith-base-images --public --source D:/projects/challsmith-base-images --remote origin`。預設分支為 `main`。
- [ ] **Step 2：請使用者自己設定 secret**，讓 token 不經過 Claude：使用者在 Docker Hub 建立 Read & Write 的 access token，然後執行 `! gh secret set DOCKERHUB_TOKEN --repo csftech/challsmith-base-images`，在提示中貼上 token。
- [ ] **Step 3：push 前掃描歷史**，不能有 VM 的 IP、帳密、token 格式或私鑰格式，然後 `git push -u origin main`。
- [ ] **Step 4：用 `gh run watch` 追蹤 workflow**，預期 4 個 build job 都成功，而且推送步驟有執行。如果失敗，修正後重新 push，最多三輪，超過就停下來回報。
- [ ] **Step 5：在 challsmith 的開發 VM 上驗證**：對每個移動 tag 執行 `docker pull csftech/php-ext:<alias>-fpm-alpine`，再用 `tests/smoke.sh` 檢查拉下來的 image。另外用 `FROM csftech/php-ext:8.3-fpm-alpine` 寫一個暫時的 Dockerfile，build 並啟動之後，確認 `/flag.txt` 的寫入流程照常運作（沿用 challsmith php 範本的 entrypoint 寫法）。驗證完移除暫時的 image。
- [ ] **Step 6：在 report 記錄** workflow run 的網址、Docker Hub 上的 tag 清單，以及每個 image 的大小。

# challsmith 第 2 部分：出題 web app 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 在第 1 部分架好的 VM 上加入出題 web app，讓作者從範本建題、在網頁上編輯檔案與題目資訊，按一次發佈就完成 build、推送 registry 與建立或更新 CTFd 的 `dynamic_iac` 題目，並提供 git 與備份壓縮檔的匯入匯出，以及發佈前清理。

**Architecture：** 三個新的 compose 服務：`web`（Next.js，BFF，唯一對外，`127.0.0.1:3000`）、`api`（FastAPI，只在內部網路，掛 docker.sock，用 docker CLI build 與 push）、`app-db`（PostgreSQL）。瀏覽器只跟 `web` 溝通，`web` 把 session token 放在 httpOnly cookie，轉送給 `api` 驗證，session 存在 PostgreSQL。題目以資料庫為正本，git 與 `.tar.gz` 都使用 spec 第 7 節的資料夾格式，以三方 hash 判斷誰改過。

**Tech Stack：** Node.js 26 LTS、Next.js 16 LTS（App Router，TypeScript）、PostgreSQL 19、Python 3.15（FastAPI、SQLAlchemy 2、Alembic、psycopg 3、httpx、PyYAML、pytest）、CodeMirror 6（`@uiw/react-codemirror`）、alpine 的 `docker-cli`、`docker-cli-buildx` 與 `git` 套件。

**Spec：** `docs/superpowers/specs/2026-11-21-challsmith-design.md`（第 2、5、7、8、9 節）。第 1 部分完成後的實際狀態以 `README.md`、`infra/compose.yaml` 與 `install.sh` 為準，spec 第 3 節的版本號已經過時。

**本計畫不包含：** base images repo（第 3 份計畫）。

## Global Constraints

- 開發與測試在使用者的 Ubuntu 26.04 開發 VM 上透過 SSH 進行：`ssh -i ~/.ssh/challsmith_vm -o BatchMode=yes <user>@<dev-vm>`，連線資訊在本機 `.env`。不讀取、不印出 `.env` 的內容。Windows 端用 `tar --exclude=./.env --exclude=./.git --exclude=./.superpowers --exclude=./web/node_modules --exclude=./web/.next -cf - . | ssh ... 'mkdir -p ~/challsmith && tar -xf - -C ~/challsmith'` 同步。VM 已裝第 1 部分（`/opt/challsmith`），以 `sudo ./install.sh` 重裝即可套用變更。
- 公開 repo 不可出現 VM 的 IP、帳密或任何 `.env` 內容。
- 版本：盡可能使用彼此相容的最新 LTS 版本。有 LTS 的元件用最新的 LTS 版本；沒有 LTS 的元件，用最新的穩定版，剛發布的 `.0` 大版本也可以；其他套件用與上述版本相容的最新穩定版。所有版本都要固定確切版本號：compose 寫明 tag，`requirements.txt` 與 `package-lock.json` 鎖版。image 有 alpine 版就用 alpine 版。開工時查證並記在 ledger。以 2026-11-22 查到的狀態，預期如下：
  - Node.js：`node:26-alpine`，26 是目前的 Active LTS，最新為 26.13.1。
  - Next.js：16.x，16 是目前的 LTS 版本線，最新為 16.4.6。React 沒有 LTS，使用 Next.js 16 支援的最新 19.x。
  - PostgreSQL：沒有 LTS，每個大版本都支援 5 年，用 `postgres:19-alpine`，最新為 19.0。
  - Python：沒有 LTS，用 `python:3.15-alpine`，支援到 2028-10，第 1 部分的 e2e 已在使用。如果有必要的套件缺少 3.15 的 musl wheel，退回 3.14，並記一筆 ruling。
  - alpine：沒有 LTS，用最新的穩定版。
  - 第 1 部分已使用的 MariaDB 11.8 本身就是 LTS，維持不變。
- 第 1 部分沿用的版本不改：`mariadb:11.8`、`php:8.6-*-alpine`、`nginx:1.30-alpine`、scenario `registry:5000/challsmith/scenarios/single:v1` 與 `multi:v1`。
- 所有服務 container 的 environment 都要套用 compose 的 `*no-proxy` anchor，不使用 `env_file`。公司 proxy 只以 `UPSTREAM_HTTP_PROXY`、`UPSTREAM_HTTPS_PROXY`、`UPSTREAM_NO_PROXY` 傳進 `api`，只在兩個地方使用：題目 `docker build` 的 `--build-arg`（`HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 與小寫三個），以及 `git` 子程序的環境變數。題目 container 與 image 的 ENV 不能帶到 proxy。
- `web` 與 `api` 的 image build 跟 `ctfd` 一樣，以 compose 的 predefined proxy build args 取得 npm、pip、apk 的 proxy。
- 只有 `web` 發布 port，綁 `127.0.0.1:3000`。`api` 與 `app-db` 不發布 port。
- 題目 image tag：`localhost:5000/challsmith/<slug>-<service>:<內容 hash 前 12 碼>`。直接使用官方 image 的 service 複製到 `localhost:5000/challsmith/mirror/<原 image 名稱與 tag>`，例如 `mariadb:11.8` → `localhost:5000/challsmith/mirror/mariadb:11.8`，已經在 `localhost:5000/` 的 image 原樣使用。
- CTFd 上不建立靜態 flag。題目的 `additional` 鍵與預設值以 `README.md` 的「Keys for single」「Keys for multi」為準，所有值都是字串。
- `slug` 必須符合 `^[a-z0-9][a-z0-9-]{0,47}$`，service 名稱必須符合 `^[a-z0-9-]+$`（與 `scenarios/internal/scenario/config.go` 的 `nameRe` 一致）。
- web app 只有一個管理者帳號，帳密來自 `challsmith.env` 的 `WEB_ADMIN_USER`、`WEB_ADMIN_PASSWORD`。
- `README.md`（英文）與 `README_ZH-TW.md`（繁體中文）內容一致，兩份都要更新。
- api 採 FastAPI 慣用的分層架構（router、service、repository、model），模組依「檔案結構」的資料夾分層：`core/`、`models/`、`repositories/`、`formats/`、`clients/`、`services/`、`routers/`、`cli/`。router 只處理 HTTP（解析請求、呼叫 service、轉換錯誤成狀態碼），業務邏輯放在 `services/`，資料庫的查詢與寫入放在 `repositories/`，外部系統的呼叫放在 `clients/`。只有 repository 可以寫 SQLAlchemy 查詢（`select`、`delete`、`db.get`、`db.add` 等）。transaction 由 service 負責：repository 只做查詢、`add`、`delete` 與必要的 `flush`，不呼叫 `commit` 或 `rollback`。依賴方向只能往下：router → service → repository → model，service 也可以用 `clients/` 與 `formats/`，`core/` 不依賴任何上層。以下各 task 寫到的 `docker_ops.X`、`ctfd.X`、`gitrepo.X`、`chall_manager.X`、`publish.X`、`sync.X`、`cleanup.X`、`templates.X`、`challenge_format.X`，分別位於 `clients/docker.py`、`clients/ctfd.py`、`clients/git.py`、`clients/chall_manager.py`、`services/publish.py`、`services/sync.py`、`services/cleanup.py`、`services/templates.py`、`formats/challenge.py`，路由一律放在 `routers/` 的同名檔案。
- 跨層呼叫時引用模組，不引用函式，讓呼叫端一眼看出呼叫的是哪一層。為此 `services/`、`clients/`、`formats/` 的檔名帶上層別後綴：`services/<名稱>_service.py`、`repositories/<名稱>_repository.py`、`clients/<名稱>_client.py`、`formats/<名稱>_format.py`，引用時不用 `as`，例如 `from challsmith_api.services import challenge_service`，呼叫時寫 `challenge_service.put_files(...)`，不寫 `from ...challenge_service import put_files`。`routers/` 只由 `main.py` 引用，維持 `routers/challenges.py` 這類名稱。models 的類別、`core.deps` 的 dependency、`get_settings`、`get_session` 與 `services/errors.py` 的例外類別可以直接引用名稱。同一個模組內的呼叫不受此限。下方「檔案結構」與各 task 寫的舊檔名，依此規則對應，例如 `clients/docker.py` 即 `clients/docker_client.py`、`services/publish.py` 即 `services/publish_service.py`、`formats/challenge.py` 即 `formats/challenge_format.py`。
- 本專案自己計算的 hash 一律使用 BLAKE3（Python 用 `blake3` 套件），包括題目內容 hash、service hash（image tag）與 session token hash。上游提供的 checksum（安裝指令驗證 pulumi-docker 的 SHA-1 與 oras 的 SHA-256）照上游格式，不在此列。
- commit 訊息結尾加上 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Review Focus

- 上傳的 zip 或 `.tar.gz` 含 `../`、絕對路徑、symlink 或解壓後過大的內容時，要整份拒絕且不寫入任何檔案，不能寫到題目資料夾以外（Task 2 的測試）。
- docker build 或 push 失敗時，publish 必須停在那一步，CTFd 不被呼叫，`published_hash` 不變，log 裡看得到 docker 的錯誤輸出（Task 6 的測試）。
- 題目在 CTFd 被手動刪掉後再發佈，web app 要建立新題並更新記錄的 CTFd ID，而不是一直失敗（Task 6 的測試）。
- 作者在公司內只匯出備份壓縮檔、沒有匯出到 git，之後從 git 匯入時，不能因為基準 hash 被備份動作改掉，就用 git 的舊版默默蓋掉資料庫的修改（Task 7 的測試）。
- 未登入、session 過期，或從其他 origin 送出的寫入請求，都必須被拒絕，`api` 的每個端點（登入除外）都要自己驗證 session，不能只靠 `web` 擋（Task 3 與 Task 9 的測試）。

---

## 檔案結構

```
challsmith/
├─ api/
│  ├─ Dockerfile                    Task 1（target runtime 與 test）
│  ├─ requirements.txt / requirements-dev.txt
│  ├─ alembic.ini / alembic/        Task 1（schema 版本）
│  ├─ challsmith_api/
│  │  ├─ main.py                    Task 1（FastAPI app，掛上各 router）
│  │  ├─ core/                      設定、資料庫連線、FastAPI dependency
│  │  │  ├─ config.py / db.py       Task 1
│  │  │  └─ deps.py                 Task 3（require_session）
│  │  ├─ models/                    SQLAlchemy 資料表，一個實體一個檔案，`__init__.py` 匯出全部
│  │  ├─ repositories/              資料庫的查詢與寫入，一個實體一個檔案（Task 6b）
│  │  │  └─ challenge_repository.py、web_session_repository.py、setting_repository.py、publish_run_repository.py
│  │  ├─ formats/                   純函式，不碰資料庫與網路
│  │  │  ├─ challenge.py            Task 2（ChallengeMeta、驗證、YAML、資料夾讀寫）
│  │  │  ├─ archive.py              Task 2（安全解壓 zip 與 tar.gz、產生 tar.gz）
│  │  │  └─ hashing.py              Task 2
│  │  ├─ clients/                   對外部系統的包裝
│  │  │  ├─ docker.py               Task 6（docker CLI，`DockerOps`）
│  │  │  ├─ ctfd.py                 Task 6（CTFd API client）
│  │  │  ├─ git.py                  Task 7（`GitRepo`）
│  │  │  └─ chall_manager.py        Task 8
│  │  ├─ services/                  業務邏輯，給 router 與命令列共用
│  │  │  ├─ auth.py                 Task 3
│  │  │  ├─ templates.py            Task 4
│  │  │  ├─ challenges.py           Task 5（load、save、hash、狀態、刪除）
│  │  │  ├─ publish.py              Task 6
│  │  │  ├─ sync.py                 Task 7
│  │  │  └─ cleanup.py              Task 8
│  │  ├─ routers/                   只放 HTTP 路由，呼叫 services
│  │  │  └─ auth.py、templates.py、challenges.py、publish.py、sync.py、cleanup.py
│  │  └─ cli/
│  │     └─ cleanup.py              Task 8（`python -m challsmith_api.cli.cleanup`）
│  └─ tests/
│     ├─ run.sh                     Task 1（起一個暫時的 postgres，在 test image 跑 pytest）
│     └─ test_*.py
├─ templates/                       Task 4（php、python-flask、node-nextjs、nginx-php-db、tcp）
├─ web/                             Task 9、10（Next.js）
├─ infra/compose.yaml               Task 1（api、app-db）、Task 9（web）
├─ infra/ops-firewall.nft           Task 11（擋 ops 連 3000）
├─ infra/challsmith-ops-firewall.service  Task 11（載入失敗時鎖住 ops）
├─ install.sh / challsmith.env.example    Task 1、Task 9
├─ scripts/cleanup.sh               Task 11（發佈前清理的命令列入口）
├─ tests/ops-isolation.sh           Task 11（加 3000 與 instance 網路的檢查）
├─ tests/templates-smoke.sh         Task 4
├─ tests/e2e/test_webapp.py / test_cleanup.py  Task 12
└─ README.md / README_ZH-TW.md      Task 12
```

---

### Task 1：api 骨架、資料庫與測試流程

**Files:**
- Create: `api/Dockerfile`、`api/requirements.txt`、`api/requirements-dev.txt`、`api/alembic.ini`、`api/alembic/env.py`、`api/alembic/versions/0001_initial.py`、`api/challsmith_api/{__init__,config,db,models,main}.py`、`api/tests/run.sh`、`api/tests/conftest.py`、`api/tests/test_health.py`
- Modify: `infra/compose.yaml`、`challsmith.env.example`、`install.sh`

**Interfaces:**
- Produces:
  - `config.Settings`（pydantic-settings 或手寫讀取皆可），欄位：`database_url`、`web_admin_user`、`web_admin_password`、`ctfd_url`（預設 `http://ctfd:8000`）、`ctfd_admin_name`、`ctfd_admin_password`、`chall_manager_url`（預設 `http://chall-manager:8080`）、`registry_prefix`（預設 `localhost:5000/challsmith`）、`scenario_single`（預設 `registry:5000/challsmith/scenarios/single:v1`）、`scenario_multi`（預設 `registry:5000/challsmith/scenarios/multi:v1`）、`templates_dir`（預設 `/app/templates`）、`data_dir`（預設 `/var/lib/challsmith`）、`upstream_http_proxy`、`upstream_https_proxy`、`upstream_no_proxy`。`get_settings()` 回傳快取的實例。
  - `db.get_session()`：FastAPI dependency，yield SQLAlchemy `Session`。
  - `models`：
    - `Challenge(id, slug unique, meta JSONB, ctfd_id int|None, published_hash str|None, sync_hash str|None, created_at, updated_at)`
    - `ChallengeFile(challenge_id FK cascade, path str, content bytea)`，`(challenge_id, path)` 唯一
    - `WebSession(token_hash str pk, expires_at)`
    - `Setting(key str pk, value JSONB)`
    - `PublishRun(id, challenge_id FK cascade, status str, log text, created_at, finished_at)`，status 為 `running`、`succeeded`、`failed`
  - `main.app`：`GET /health` 回 `{"ok": true}`，不需要登入。
  - `api/tests/run.sh [pytest args]`：在 VM 上以 `aps` 執行，建立暫時的 docker network 與 postgres container，build `api/Dockerfile` 的 `test` target，以 `DATABASE_URL` 指向該 postgres 跑 pytest，結束時一定移除 postgres 與 network。
  - compose 新增兩個服務，都是 `restart: unless-stopped`，environment 都套 `*no-proxy`：
    - `app-db`：選定的 postgres alpine image，`POSTGRES_USER: challsmith`、`POSTGRES_DB: challsmith`、`POSTGRES_PASSWORD: ${APP_DB_PASSWORD}`，volume `app-db`，healthcheck 用 `pg_isready`。
    - `api`：build `context: ..`、`dockerfile: api/Dockerfile`、`target: runtime`，proxy build args 與 `ctfd` 相同。environment 為 `Settings` 的各欄位，`DATABASE_URL` 指向 `app-db`，`CTFD_ADMIN_NAME`、`CTFD_ADMIN_PASSWORD`、`WEB_ADMIN_USER`、`WEB_ADMIN_PASSWORD` 來自 env 檔，`UPSTREAM_HTTP_PROXY: ${HTTP_PROXY:-}` 等三個。掛 `/var/run/docker.sock` 與 volume `app-data:/var/lib/challsmith`。`depends_on` `app-db`（healthy）。不發布 port。
    - 新增 volumes `app-db`、`app-data`。
  - `challsmith.env.example` 新增 `WEB_ADMIN_USER=admin`、`WEB_ADMIN_PASSWORD=`（必填）、`APP_DB_PASSWORD=`（留空時自動產生），並說明 `CTFD_ADMIN_NAME` 與 `CTFD_ADMIN_PASSWORD` 也會給 web app 登入 CTFd 用，在 CTFd 改了管理者密碼要同步改這裡。
  - `install.sh`：step 1 檢查 `WEB_ADMIN_PASSWORD` 不為空，否則中止並說明；`fill APP_DB_PASSWORD`；沿用既有的 `dc up -d --build`。
  - `tests/conftest.py` 提供 `db` fixture（每個測試在乾淨的 schema 上跑，例如先 `alembic upgrade head` 再在測試後 truncate）與 `client` fixture（`TestClient(app)`）。

- [ ] **Step 1：寫 `test_health.py`**：`client.get("/health")` 回 200 與 `{"ok": True}`；另一個測試確認 `alembic upgrade head` 後五張表都存在（用 `sqlalchemy.inspect`）。
- [ ] **Step 2：寫 Dockerfile**。base 用 Global Constraints 選定的 python alpine image，`apk add git docker-cli docker-cli-buildx`，`runtime` target 以 `uvicorn challsmith_api.main:app --host 0.0.0.0 --port 8000 --workers 1` 啟動，啟動前執行 `alembic upgrade head`。`test` target 多裝 `requirements-dev.txt`（pytest、httpx）。build context 是 repo 根目錄，image 內 `COPY templates/ /app/templates/`。`--workers 1` 是因為 Task 7 的匯入預覽存在行程記憶體中。
- [ ] **Step 3：寫 `run.sh`、models 與第一個 migration**，執行 `api/tests/run.sh`，預期 2 passed。
- [ ] **Step 4：整合進 compose 與安裝指令**，在 VM 上執行 `sudo ./install.sh`，預期正常結束，`docker compose -p challsmith exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"` 印出 `{"ok":true}`。再執行一次 `sudo ./install.sh`，`APP_DB_PASSWORD` 不變。
- [ ] **Step 5：commit** `feat(api): skeleton, schema, test runner and compose service`

### Task 2：題目格式、hash 與安全解壓

**Files:**
- Create: `api/challsmith_api/challenge_format.py`、`api/challsmith_api/hashing.py`、`api/challsmith_api/archive.py`
- Test: `api/tests/test_challenge_format.py`、`api/tests/test_hashing.py`、`api/tests/test_archive.py`

**Interfaces:**
- Produces:
  - `ServiceSpec`（pydantic）：`name`、`port: int | None`、`entry: bool = False`、`image: str | None`（有值代表直接用現成 image，沒有資料夾）、`env: dict[str, str] = {}`。
  - `ChallengeMeta`（pydantic）：欄位順序即 `challenge.yml` 的輸出順序，`slug`、`name`、`category`、`tags: list[str]`、`description`、`value: int`、`template: str | None`、`scenario: Literal["single","multi"]`、`flag`、`flag_prefix: str = "CTF"`、`protocol: Literal["http","tcp"] = "http"`、`instance: InstanceSpec`（`timeout: int = 3600`、`mana: int = 1`、`memory: str = "256m"`、`cpus: str = "0.5"`）、`services: list[ServiceSpec]`、`visible: bool = True`。`flag_prefix`、`protocol`、`memory`、`cpus` 是 spec 範例沒有、但 scenario 支援的鍵，等於預設值時輸出 YAML 也照樣寫出。
  - 驗證規則（違反時 raise `ValueError`，訊息指出欄位）：slug 與 service 名稱符合 Global Constraints 的 regex；service 名稱不重複；恰好一個 `entry: true` 且它有 `port`；`single` 只能有一個 service 且它沒有 `image`（必須是資料夾）；`memory` 符合 `^\d+[mg]$`；`value`、`timeout`、`mana` 為正整數。
  - `dump_challenge_yml(meta: ChallengeMeta) -> bytes`：確定性輸出（固定欄位順序、`sort_keys=False`、UTF-8、LF）。
  - `parse_challenge_yml(data: bytes) -> ChallengeMeta`
  - `safe_relpath(path: str) -> str`：回傳正規化後的 POSIX 相對路徑。空字串、絕對路徑、含 `..` 片段、含反斜線或 NUL 時 raise `ValueError`。
  - `to_folder(meta, files: dict[str, bytes]) -> dict[str, bytes]`：`files` 的 key 是相對於題目資料夾的路徑（例如 `services/app/index.php`），回傳加上 `challenge.yml` 的完整資料夾。`from_folder(folder: dict[str, bytes]) -> tuple[ChallengeMeta, dict[str, bytes]]` 是反向操作，資料夾的 `slug` 以 `challenge.yml` 為準。
  - `hashing.content_hash(meta: ChallengeMeta, files: dict[str, bytes]) -> str`：BLAKE3 hex（`blake3` 套件，預設 32 bytes 輸出）。輸入是 `meta.model_dump(mode="json")` 的 canonical JSON（`sort_keys=True`、`separators=(",",":")`），加上依路徑排序的每個檔案。不含 NUL byte 的檔案先把 CRLF 換成 LF。檔案權限本來就不在輸入裡。
  - `hashing.service_hash(files: dict[str, bytes], service: str) -> str`：同樣的正規化，只算 `services/<service>/` 底下的檔案，用於 image tag。
  - `archive.extract_zip(data: bytes) -> dict[str, bytes]`、`archive.extract_tar_gz(data: bytes) -> dict[str, bytes]`：每個成員的路徑都經過 `safe_relpath`，只接受一般檔案與目錄，遇到 symlink、hardlink、裝置檔時整份 raise `ValueError`。上限：成員數 2000、解壓後總大小 100 MiB，超過就 raise。
  - `archive.make_tar_gz(folders: dict[str, dict[str, bytes]]) -> bytes`：key 是 slug，輸出 `challenges/<slug>/...`，mtime 固定為 0，成員依路徑排序。

- [ ] **Step 1：寫失敗的測試**
  - `test_yaml_roundtrip`：spec 第 7 節的 `php-strcmp` 範例 parse 之後再 dump、再 parse 結果相等，而且 dump 兩次的 bytes 完全相同。
  - `test_validation_errors`：參數化，分別給 slug `Bad_Slug`、兩個 entry、entry 沒有 port、single 卻有兩個 service、`memory: 256` 時都 raise `ValueError`。
  - `test_safe_relpath`：`"../x"`、`"/etc/passwd"`、`"a/../../b"`、`"a\\b"`、`""` 都 raise，`"services/app/./index.php"` 回傳 `"services/app/index.php"`。
  - `test_hash_ignores_crlf`：`b"a\r\nb"` 與 `b"a\nb"` 的 `content_hash` 相同。含 NUL 的 binary 檔案不做轉換，內容不同時 hash 不同。
  - `test_hash_changes_with_meta`：只改 `meta.value`，hash 就要不同。
  - `test_hash_ignores_yaml_formatting`：同一份 meta 以不同縮排與欄位順序寫成的兩份 `challenge.yml`，經 `from_folder` 後 hash 相同。
  - `test_extract_rejects`：參數化，含 `../evil` 成員的 zip、含絕對路徑的 tar、含 symlink 的 tar、解壓後超過 100 MiB 的 zip（用高壓縮率的零位元組檔案製造）都 raise `ValueError`。
  - `test_make_tar_gz_roundtrip`：`extract_tar_gz(make_tar_gz(x))` 等於加上 `challenges/<slug>/` 前綴的 `x`。
- [ ] **Step 2：執行 `api/tests/run.sh tests/test_challenge_format.py tests/test_hashing.py tests/test_archive.py`**，預期因為模組不存在而失敗。
- [ ] **Step 3：實作三個模組**。解壓時先檢查完所有成員，再一次回傳結果，避免只解出一半。
- [ ] **Step 4：重跑**，預期全部通過。
- [ ] **Step 5：commit** `feat(api): challenge folder format, content hash and safe archive extraction`

### Task 3：登入與 session

**Files:**
- Create: `api/challsmith_api/auth.py`
- Modify: `api/challsmith_api/main.py`
- Test: `api/tests/test_auth.py`

**Interfaces:**
- Produces:
  - `POST /auth/login` body `{"username","password"}`：帳密以 `hmac.compare_digest` 比對 `Settings`，成功時產生 `secrets.token_urlsafe(32)`，資料庫只存它的 BLAKE3 hash，有效期 12 小時，回 `{"token": ..., "expires_at": ...}`。失敗回 401，不區分帳號錯還是密碼錯。
  - `POST /auth/logout`：刪掉目前的 session，回 204。
  - `GET /auth/me`：回 `{"username": ...}`。
  - `require_session`：FastAPI dependency，讀 `Authorization: Bearer <token>`，token 不存在或過期時回 401。除了 `/health` 與 `/auth/login`，所有 router 都以 `dependencies=[Depends(require_session)]` 掛上，包括之後各 task 新增的 router。
  - `clear_sessions(db) -> int`：刪掉全部 session，回傳刪除筆數，給 Task 8 使用。

- [ ] **Step 1：寫失敗的測試**：正確帳密拿到 token，`/auth/me` 帶 token 回 200；錯誤密碼回 401；不帶 token、帶亂數 token、帶過期 token（直接把資料庫的 `expires_at` 改成過去）都回 401；logout 後同一個 token 回 401；資料庫裡找不到 token 的明文。另外寫 `test_all_routes_require_session`：走訪 `app.routes`，除了 `/health`、`/auth/login` 與 FastAPI 內建的文件路由，每個路由不帶 token 呼叫都要回 401。之後的 task 新增路由時，這個測試會自動涵蓋。
- [ ] **Step 2：執行測試，預期失敗。**
- [ ] **Step 3：實作 `auth.py`**，在 `main.py` 關掉 `/docs`、`/redoc`、`/openapi.json`（`docs_url=None` 等），`api` 不需要對外的文件頁面。
- [ ] **Step 4：重跑測試，預期通過。**
- [ ] **Step 5：commit** `feat(api): single-admin login with server-side sessions`

### Task 4：範本

**Files:**
- Create: `templates/{php,python-flask,node-nextjs,nginx-php-db,tcp}/template.yml` 與各自的檔案、`api/challsmith_api/templates.py`、`tests/templates-smoke.sh`
- Modify: `api/challsmith_api/main.py`
- Test: `api/tests/test_templates.py`

**Interfaces:**
- Consumes: `ChallengeMeta`、`ServiceSpec`、`safe_relpath`（Task 2）。
- Produces:
  - `template.yml` 格式：`description`（一行，顯示在建題頁面）、`scenario`、`protocol`、`flag_prefix`（可省略）、`instance`（可省略）、`services`（`ServiceSpec` 清單）。範本資料夾裡除了 `template.yml` 之外的檔案，就是新題目的 `services/<name>/...` 初始檔案。
  - `templates.list_templates() -> list[TemplateInfo]`（`name`、`description`、`scenario`），`templates.instantiate(name: str, slug: str, title: str) -> tuple[ChallengeMeta, dict[str, bytes]]`：回傳的 meta 的 `category` 為 `Web`（`tcp` 範本為 `Pwn`）、`value` 為 100、`flag` 為 slug 把 `-` 換成 `_`、`template` 為範本名稱、`tags` 為空清單、`description` 為空字串。範本不存在時 raise `KeyError`。
  - `GET /templates` 回傳 `list_templates()`。

範本內容（每個 image 都在 Dockerfile 寫明 tag；每個題目 container 都有 `entrypoint.sh`，在服務啟動前執行 `printf '%s\n' "$FLAG" > /flag.txt`，`FLAG` 為空時直接失敗退出）：

| 範本 | services | 內容 |
|---|---|---|
| `php` | `app`（port 80，entry） | `php:8.6-cli-alpine`，`php -S 0.0.0.0:80 -t /var/www/html`，範例 `index.php` 只顯示一段提示文字，不讀 flag |
| `python-flask` | `app`（port 5000，entry） | `python:3.15-alpine`（或 Task 1 選定的版本），`requirements.txt` 固定 Flask 的最新穩定版，`app.py` 監聽 `0.0.0.0:5000` |
| `node-nextjs` | `app`（port 3000，entry） | `node:26-alpine`（或 Task 1 選定的版本），最小的 Next.js 16 App Router 專案，build 時 `npm ci && npm run build`，以 `next start -H 0.0.0.0 -p 3000` 啟動，附上 `package-lock.json` |
| `nginx-php-db` | `web`（port 80，entry）、`php`、`db`（`image: mariadb:11.8`，env `MARIADB_ROOT_PASSWORD`、`MARIADB_DATABASE: app`） | 以 `examples/hello-multi` 為基礎：nginx 轉給 `php:9000`；php-fpm 用 `docker-php-ext-install pdo_mysql mysqli`，`clear_env = no`；`instance.memory` 為 `512m` |
| `tcp` | `app`（port 9000，entry） | `alpine` 最新的固定版本，`apk add socat`，`socat TCP-LISTEN:9000,reuseaddr,fork EXEC:/app/run.sh`，`protocol: tcp`，`category` 為 `Pwn` |

- [ ] **Step 1：寫失敗的測試** `test_templates.py`：五個範本都列得出來；`instantiate` 每個範本後產生的 meta 都能通過 Task 2 的驗證，`to_folder` 的結果能被 `from_folder` 讀回同一份 meta；`instantiate("nope", ...)` raise `KeyError`；`GET /templates` 帶 session 回 5 筆。
- [ ] **Step 2：執行測試，預期失敗。**
- [ ] **Step 3：建立五個範本與 `templates.py`。**
- [ ] **Step 4：重跑測試，預期通過。**
- [ ] **Step 5：寫並執行 `tests/templates-smoke.sh`**（在 VM 上以 `aps` 執行）：逐一 build 每個範本中有資料夾的 service，再以 `-e FLAG='CTF{smoke}'` 執行。單一 container 的範本用 `curl` 確認入口 port 有回應，`tcp` 用 `nc` 確認有輸出；`nginx-php-db` 用一個暫時的 docker network 起三個 container，確認 `curl` 得到 200。另外確認沒有帶 `FLAG` 時，container 會以非 0 退出。腳本結束時移除自己建立的 container、network 與 image。預期全部 PASS。
- [ ] **Step 6：commit** `feat: challenge templates (php, python-flask, node-nextjs, nginx-php-db, tcp)`

### Task 5：題目 CRUD、檔案與上傳

**Files:**
- Create: `api/challsmith_api/challenges.py`
- Modify: `api/challsmith_api/main.py`
- Test: `api/tests/test_challenges.py`

**Interfaces:**
- Consumes: Task 2 的格式與 hash、Task 3 的 `require_session`、Task 4 的 `instantiate`。
- Produces：
  - `load_challenge(db, slug) -> tuple[Challenge, ChallengeMeta, dict[str, bytes]]`（找不到時 404）、`save_challenge(db, slug, meta, files) -> Challenge`（新增或覆寫，整題在同一個 transaction 寫入）、`current_hash(db, challenge) -> str`。這三個函式給 Task 6、7 共用。
  - `status_of(challenge, current_hash) -> dict`：`publish` 為 `draft`（`ctfd_id` 為 null）、`published`（`published_hash == current_hash`）或 `modified`；`sync` 為 `never`（`sync_hash` 為 null）、`synced` 或 `modified`。
  - 路由：
    - `GET /challenges`：`[{slug, name, category, scenario, publish, sync, updated_at}]`
    - `POST /challenges` body `{slug, template, name}`：slug 已存在回 409，範本不存在回 400
    - `GET /challenges/{slug}`：`{meta, files: [{path, size}], status}`
    - `PUT /challenges/{slug}` body `ChallengeMeta`：body 的 slug 必須等於路徑的 slug（不支援改 slug），驗證失敗回 422 並帶上錯誤訊息
    - `DELETE /challenges/{slug}`：有 `ctfd_id` 時先呼叫 Task 6 的 `CtfdClient.delete_challenge`（CTFd 回 404 視為已刪除），再刪資料庫。Task 6 完成之前先只刪資料庫，Task 6 補上 CTFd 這一步。
    - `GET /challenges/{slug}/files/{path:path}`：回傳原始 bytes
    - `PUT /challenges/{slug}/files/{path:path}`：request body 就是檔案內容，路徑經過 `safe_relpath`，而且必須在 `services/<某個 service>/` 底下，`challenge.yml` 不能用這個路由改
    - `DELETE /challenges/{slug}/files/{path:path}`
    - `POST /challenges/{slug}/upload?dir=services/app`：multipart 單一欄位 `file`。副檔名是 `.zip` 時以 `extract_zip` 解開，放到 `dir` 底下，否則當成單一檔案放到 `dir/<檔名>`。單一檔案上限 20 MiB。任何一個成員不合法時整份拒絕，回 400。

- [ ] **Step 1：寫失敗的測試**：從 `php` 範本建題後，清單的狀態是 `draft`、`never`；改檔案後再讀回內容一致，`updated_at` 變新；PUT 路徑 `../x`、`challenge.yml`、`services/nope/x`（service 不存在）都回 400；上傳含 `../evil` 的 zip 回 400，而且題目的檔案清單完全不變；上傳正常的 zip 後，檔案出現在指定的 dir 底下；建立重複的 slug 回 409；PUT meta 換 slug 回 400；手動把 `ctfd_id` 設成 1、`published_hash` 設成目前的 hash 時狀態為 `published`，改一個檔案後變成 `modified`。
- [ ] **Step 2：執行測試，預期失敗。**
- [ ] **Step 3：實作 `challenges.py`。**
- [ ] **Step 4：重跑測試，預期通過。**
- [ ] **Step 5：commit** `feat(api): challenge CRUD, file editing and uploads`

### Task 5b：api 模組分層

使用者在 Task 5 完成後要求：不要把 model、route、config、db 全部放在同一層，改成依元件分資料夾。這個 task 只搬移與改 import，不改行為。

**Files:**
- Move：`config.py`、`db.py` → `core/`；`models.py` → `models/`（`base.py` 放 `Base` 與共用欄位 helper，`challenge.py` 放 `Challenge` 與 `ChallengeFile`，`web_session.py`、`setting.py`、`publish_run.py` 各放一個，`__init__.py` 匯出全部）；`challenge_format.py`、`archive.py`、`hashing.py` → `formats/`（`challenge_format.py` 改名為 `formats/challenge.py`）；`templates.py` → `services/templates.py`；`routes_templates.py` → `routers/templates.py`；`auth.py` 拆成 `services/auth.py`（token hash、建立與驗證 session、`clear_sessions`）、`core/deps.py`（`require_session`）與 `routers/auth.py`（`/auth/*` 路由）；`challenges.py` 拆成 `services/challenges.py`（`load_challenge`、`save_challenge`、`current_hash`、`status_of`、`delete_challenge` 與其他不碰 HTTP 的邏輯）與 `routers/challenges.py`。
- Modify：`main.py`、`alembic/env.py`、`api/tests/*.py` 的 import。

**Interfaces:**
- Produces：上面的新位置。舊的平面模組全部刪除，不留相容用的轉接模組。services 層的函式在找不到資料時 raise 自己的例外（例如 `NotFound`、`Conflict`），由 router 轉成 HTTP 狀態碼。既有測試會呼叫這些函式，如果它們目前直接 raise `HTTPException`，就維持現在的行為，只在 report 裡註明。
- 不改 HTTP 行為、不改資料表、不改測試的斷言，只改 import 與搬移時必要的呼叫位置。

- [ ] **Step 1：搬移並修正 import。**
- [ ] **Step 2：執行完整測試**，預期與搬移前同樣的測試數量全部通過（Task 5 結束時為 79 passed），`test_all_routes_require_session` 仍然涵蓋所有路由。
- [ ] **Step 3：在 VM 上執行 `sudo ./install.sh`**，確認 api container 正常啟動，`alembic upgrade head` 與 `/health` 正常。
- [ ] **Step 4：commit** `refactor(api): split modules into core, models, formats, services, routers`

### Task 6：發佈

**Files:**
- Create: `api/challsmith_api/clients/docker.py`、`api/challsmith_api/clients/ctfd.py`、`api/challsmith_api/services/publish.py`、`api/challsmith_api/routers/publish.py`
- Modify: `api/challsmith_api/services/challenges.py`（`delete_challenge` 補上刪除 CTFd 題目）、`api/challsmith_api/main.py`
- Test: `api/tests/test_publish.py`、`api/tests/test_ctfd.py`

**Interfaces:**
- Consumes: `load_challenge`、`current_hash`、`service_hash`。
- Produces：
  - `docker_ops.DockerOps`，每個方法把子程序的 stdout 與 stderr 一行一行交給 `log: Callable[[str], None]`，結束碼不是 0 時 raise `DockerError`：
    - `build(context_dir: Path, tag: str, log) -> None`：`docker build --progress=plain -t <tag> <dir>`，加上 Global Constraints 規定的六個 `--build-arg`（只在對應的 `UPSTREAM_*` 有值時加）。
    - `push(tag, log)`、`pull(image, log)`、`tag(src, dst, log)`
    - `remove_containers(name_prefix: str, log) -> int`、`remove_networks(name_prefix: str, log) -> int`：給 Task 8 使用，用 `docker ps -a` 與 `docker network ls` 的 `--filter name=^<prefix>` 找出目標再刪除。
  - `ctfd.CtfdClient(base_url, name, password, transport=None)`：以 CTFd 網頁登入（GET `/login` 取 `csrfNonce`，POST 表單，回 302 才算成功），之後的 API 呼叫都帶 session cookie 與 `CSRF-Token` header（登入後到 `/challenges` 重新取 nonce），做法與 `tests/e2e/conftest.py` 相同，不建立 API token。登入失敗時 raise `CtfdError`，訊息說明 `CTFD_ADMIN_NAME` 與 `CTFD_ADMIN_PASSWORD` 要與 CTFd 管理者一致。方法：
    - `create_challenge(payload: dict) -> int`、`update_challenge(cid: int, payload: dict) -> None`（CTFd 回 404 時 raise `CtfdNotFound`）、`delete_challenge(cid) -> None`
    - `set_tags(cid, tags: list[str]) -> None`：刪掉不在清單裡的 tag，補上缺少的 tag
    - `list_users() -> list[dict]`（跟著 `meta.pagination.next` 讀完所有頁）、`delete_user(uid) -> None`：給 Task 8 使用
    - 建立與更新題目時，chall-manager 會在 CTFd 的 request 中同步處理 scenario，timeout 設 300 秒
  - `publish.build_additional(meta: ChallengeMeta, images: dict[str, str]) -> tuple[str, dict[str, str]]`：回傳 `(scenario_ref, additional)`。`images` 是 service 名稱對應到本機 registry 的 image。
    - `single`：`{"image", "port", "protocol", "flag", "flag_prefix", "memory", "cpus"}`
    - `multi`：`{"services": <JSON 字串>, "flag", "flag_prefix", "protocol", "memory", "cpus"}`，JSON 的每個元素只放 `name`、`image`，以及有值時的 `port`、`entry`、`env`
  - `publish.ctfd_payload(meta, scenario_ref, additional) -> dict`：`name`、`category`、`description`、`type: "dynamic_iac"`、`function: "linear"`、`initial` 與 `minimum` 都是 `meta.value`、`decay: 0`、`state`（`visible` 或 `hidden`）、`scenario`、`additional`、`mana_cost`、`timeout`，與 `tests/e2e/conftest.py` 的欄位一致。更新時拿掉 `type`。
  - `publish.run_publish(db_factory, run_id, slug, docker: DockerOps, ctfd: CtfdClient) -> None`：流程如下，每一步都寫進 `PublishRun.log`，每寫一行就 commit，讓前端輪詢時看得到進度：
    1. 在一個 transaction 裡讀出 meta、檔案與目前的 hash，作為這次發佈的快照，之後作者再修改不會影響這次發佈。
    2. 對每個有資料夾的 service，把快照的 `services/<name>/` 寫到暫存目錄，build 並 push `<registry_prefix>/<slug>-<name>:<service_hash 前 12 碼>`。
    3. 對每個有 `image` 的 service，pull、tag 成 mirror 的位置再 push（規則見 Global Constraints）。
    4. 組出 additional 與 payload。有 `ctfd_id` 時更新，遇到 `CtfdNotFound` 就改成建立新題；沒有 `ctfd_id` 時建立。然後 `set_tags`。
    5. 全部成功後，才把 `ctfd_id` 與 `published_hash`（快照的 hash）寫回 `Challenge`，run 標為 `succeeded`。任何例外都把例外訊息寫進 log，run 標為 `failed`，`Challenge` 不動。
  - 路由：`POST /challenges/{slug}/publish` 回 `{"run_id"}`，同一題已有 `running` 的 run 時回 409，以 FastAPI `BackgroundTasks` 執行 `run_publish`。`GET /publish-runs/{id}` 回 `{status, log, created_at, finished_at}`。api 啟動時把殘留的 `running` run 標成 `failed`，log 補一行說明是重啟中斷。

- [ ] **Step 1：寫失敗的測試**
  - `test_build_additional_single`：`php` 範本、slug `php-strcmp`、flag `php_strcmp_array`，images 為 `{"app": "localhost:5000/challsmith/php-strcmp-app:abc"}` 時，結果完全等於 `("registry:5000/challsmith/scenarios/single:v1", {"image": "localhost:5000/challsmith/php-strcmp-app:abc", "port": "80", "protocol": "http", "flag": "php_strcmp_array", "flag_prefix": "CTF", "memory": "256m", "cpus": "0.5"})`。
  - `test_build_additional_multi`：`nginx-php-db` 範本，`json.loads(additional["services"])` 裡 `db` 的 image 是 `localhost:5000/challsmith/mirror/mariadb:11.8`，`web` 有 `"entry": true` 與 `"port": 80`，`additional["memory"] == "512m"`，所有值都是 `str`。
  - `test_mirror_ref`：`mariadb:11.8` → `localhost:5000/challsmith/mirror/mariadb:11.8`，`library/redis:8` → `localhost:5000/challsmith/mirror/library/redis:8`，沒有 tag 的 `nginx` → `localhost:5000/challsmith/mirror/nginx:latest`，`localhost:5000/x:1` 原樣回傳。
  - `test_publish_success`：用 fake `DockerOps`（記錄呼叫）與 fake `CtfdClient`，publish 後 run 為 `succeeded`，`ctfd_id` 已寫入，`published_hash` 等於發佈前的 `current_hash`，fake CTFd 收到的 payload 不含 `flags` 鍵（不建立靜態 flag）。
  - `test_publish_build_failure_stops`：fake build raise `DockerError("boom")`，run 為 `failed`，log 含 `boom`，fake CTFd 沒有被呼叫，`ctfd_id` 與 `published_hash` 不變。
  - `test_publish_recreates_when_ctfd_missing`：`ctfd_id` 為 7，fake `update_challenge` raise `CtfdNotFound`，`create_challenge` 回 12，結束後 `ctfd_id == 12`。
  - `test_publish_conflict`：已經有一個 `running` 的 run 時，再 POST 回 409。
  - `test_ctfd.py` 用 `httpx.MockTransport` 模擬 CTFd：登入頁沒有 nonce 或登入回 200（帳密錯誤時 CTFd 不會 redirect）都 raise `CtfdError`；`set_tags` 在現有 `["a","b"]`、目標 `["b","c"]` 時刪 a、加 c；`list_users` 在兩頁的回應下回傳兩頁的使用者。
- [ ] **Step 2：執行測試，預期失敗。**
- [ ] **Step 3：實作三個模組與路由**，並讓 `DELETE /challenges/{slug}` 先刪 CTFd 題目。`DockerOps` 與 `CtfdClient` 以 FastAPI dependency 提供，測試用 `app.dependency_overrides` 換成 fake。
- [ ] **Step 4：重跑測試，預期通過。**
- [ ] **Step 5：commit** `feat(api): publish challenges to the registry and CTFd`

真正的 docker 與 CTFd 在 Task 12 的端對端測試驗證。

### Task 6b：repository 層

使用者在 Task 6 進行中要求加上 repository 層（router、service、repository、model）。這個 task 只搬移資料庫存取的程式碼，不改行為。

**Files:**
- Create：`api/challsmith_api/repositories/__init__.py`、`challenge_repository.py`（`Challenge` 與 `ChallengeFile`）、`web_session_repository.py`、`setting_repository.py`（Task 7 會用到，這裡先放 `get(db, key)` 與 `put(db, key, value)`）、`publish_run_repository.py`
- Modify：`services/` 底下所有直接寫 SQLAlchemy 查詢的地方、`main.py` 的 lifespan（如果它直接查 `PublishRun`）、`core/deps.py`（`require_session` 改用 `web_session_repository`，`core` 依賴 `repositories` 是往下，可以）

**Interfaces:**
- Produces：每個 repository 是一組模組層級函式，第一個參數是 `Session`，例如 `challenge_repository.get_by_slug(db, slug) -> Challenge | None`、`challenge_repository.list_all(db) -> list[Challenge]`、`challenge_repository.files_of(db, challenge) -> dict[str, bytes]`、`challenge_repository.replace_files(db, challenge, files)`、`challenge_repository.put_files(db, challenge, put, remove)`、`publish_run_repository.running_for_update(db, challenge) -> PublishRun | None`。函式名稱由實作者依實際用途決定，在 report 中列出。
- repository 不 commit、不 rollback、不 raise `services/errors.py` 的例外，查不到時回傳 `None`，由 service 決定要不要 raise `NotFound`。
- 不改 HTTP 行為、不改資料表、不改測試的斷言。

- [ ] **Step 1：建立 repositories，把 services 與 core 裡的查詢搬過去。**
- [ ] **Step 2：grep 確認 `services/`、`routers/`、`core/deps.py` 裡沒有 `select(`、`delete(`、`db.get(`、`db.add(`、`db.query(`、`db.execute(`，`repositories/` 裡沒有 `commit(` 與 `rollback(`。**
- [ ] **Step 3：執行完整測試**，數量與 Task 6 結束時相同，全部通過。在 VM 上 `sudo ./install.sh` 後 api 正常啟動。
- [ ] **Step 4：commit** `refactor(api): add a repository layer for database access`

### Task 7：git 與備份壓縮檔

**Files:**
- Create: `api/challsmith_api/clients/git.py`、`api/challsmith_api/services/sync.py`、`api/challsmith_api/routers/sync.py`；資料庫存取放在 `repositories/`（例如 git 設定用 `setting_repository`）
- Modify: `api/challsmith_api/main.py`
- Test: `api/tests/test_sync.py`、`api/tests/test_gitrepo.py`

**Interfaces:**
- Consumes: `load_challenge`、`save_challenge`、`current_hash`、`content_hash`、`to_folder`、`from_folder`、`make_tar_gz`、`extract_tar_gz`。
- Produces：
  - git 設定存在 `Setting` 的 `git` 鍵：`{"remote_url", "username", "token", "branch": "main", "dir": "challenges", "author_name": "challsmith", "author_email": "challsmith@localhost"}`。`GET /settings/git` 回傳時 `token` 只回傳是否已設定（`"token_set": true`），`PUT /settings/git` 的 `token` 為 null 時保留原值。
  - `gitrepo.GitRepo(workdir: Path, settings: dict, proxy_env: dict)`：所有 git 指令都是子程序，環境變數只含 `PATH`、`HOME`、`GIT_TERMINAL_PROMPT=0`，以及 `proxy_env`（由 `UPSTREAM_*` 產生的 `http_proxy`、`https_proxy`、`no_proxy`）。帳密透過 `GIT_ASKPASS` 指向一個從環境變數讀帳密的小腳本，不寫進 remote URL，也不寫進 `.git/config`。工作目錄放在 `<data_dir>/git`。
    - `fetch() -> bool`：初次時 `git init` 並設定 remote，然後 `git fetch origin <branch>`，遠端沒有這個 branch 時回 False。
    - `read_tree() -> dict[str, dict[str, bytes]]`：用 `git archive origin/<branch> <dir>` 讀出每題的資料夾，key 是 slug，不切換工作目錄，也不 merge。遠端沒有 branch 時回空 dict。
    - `commit_and_push(folders: dict[str, dict[str, bytes]], message: str, push: bool) -> dict`：先把本機 branch 重設到 `origin/<branch>`（遠端沒有這個 branch 時建立 orphan branch），寫入每題的資料夾（同一個 slug 的資料夾整個替換，資料庫裡沒有的題目資料夾不刪），沒有變動就不 commit。回傳 `{"commit": sha|None, "pushed": bool, "error": str|None}`，push 失敗不 raise，`error` 放 git 的輸出並附上建議改用備份壓縮檔的說明。本機未 push 的 commit 會在下一次匯出時被重設掉，資料庫才是正本。
  - `sync.classify(base: str|None, db: str|None, src: str) -> str`：
    - `db is None` → `new`
    - `db == src` → `unchanged`
    - `db == base` → `source_changed`
    - `src == base` → `db_changed`
    - 其他 → `conflict`（包括 `base` 為 null、兩邊都有而且不同）
  - `sync.preview(db, source: dict[str, dict[str, bytes]]) -> dict`：每題用 `from_folder` 解析並算 hash，解析失敗的題目列為 `invalid` 並附錯誤訊息，不影響其他題。把來源內容與分類結果存在行程記憶體的預覽表，key 是隨機的 `preview_id`，30 分鐘後失效。回傳 `{"preview_id", "items": [{"slug", "status", "error"?}]}`。只存在資料庫、來源沒有的題目不列出。
  - `sync.apply(db, preview_id, decisions: dict[str, Literal["source","db"]], kind: Literal["git","archive"]) -> dict`：每個 `conflict` 都必須有決定，缺少時回 400 且不寫入任何東西。套用前重新計算每題資料庫目前的 hash，與預覽時不同就整批回 409，請作者重新預覽。規則：
    - `new`、`source_changed`、選 `source` 的 `conflict`：寫入來源版本，`sync_hash` 設為來源的 hash
    - `unchanged`：`sync_hash` 設為該 hash
    - 選 `db` 的 `conflict`：`sync_hash` 設為來源的 hash，下次比對時就會判定為 `db_changed`
    - `db_changed`：不動
    - `invalid`：跳過
  - 匯入只寫資料庫，不發佈到 CTFd。
  - 基準 hash 的更新規則：git 匯出、git 匯入、備份匯入都會更新 `sync_hash`，**下載備份不更新**。下載的備份可能不會再匯入任何地方，如果它也更新基準，之後 git 上的舊版會被判定成「只有 git 改過」而蓋掉資料庫的修改。
  - 路由：`GET`、`PUT /settings/git`；`POST /sync/git/export` body `{"push": bool}`，匯出所有題目，成功 commit 後把每題的 `sync_hash` 設為目前的 hash；`POST /sync/git/preview`；`POST /sync/archive/preview`（multipart `file`，上限 100 MiB）；`POST /sync/apply` body `{"preview_id", "decisions"}`（`kind` 由預覽記錄）；`GET /backup` 回 `application/gzip`，檔名 `challsmith-backup-<UTC 時間>.tar.gz`。

- [ ] **Step 1：寫失敗的測試**
  - `test_classify`：參數化五種情況，外加 `base=None`、db 與 src 不同 → `conflict`，`base=None`、兩者相同 → `unchanged`。
  - `test_apply_requires_conflict_decisions`：預覽中有一題 `conflict`，`decisions` 為空時回 400，資料庫不變。
  - `test_apply_rejects_stale_preview`：預覽後修改資料庫中的某題，再 apply 回 409。
  - `test_backup_download_keeps_base`：題目 `sync_hash` 為 B，修改資料庫成 D，下載備份後 `sync_hash` 仍為 B；接著拿 git 的 B 版本預覽，狀態是 `db_changed` 而不是 `source_changed`。
  - `test_conflict_keep_db_then_db_changed`：衝突時選 `db`，資料庫內容不變，再對同一份來源預覽，狀態變成 `db_changed`。
  - `test_archive_roundtrip`：下載的備份再上傳預覽，全部 `unchanged`。
  - `test_gitrepo.py`：在 `tmp_path` 建一個 bare repo 當 remote，`commit_and_push` 後 clone 出來看得到 `challenges/<slug>/challenge.yml`；第二次匯出內容不變時 `commit` 為 None；在另一個 clone 修改後 push，`fetch` 加 `read_tree` 讀得到新內容；remote 是不存在的路徑時 `commit_and_push(push=True)` 回傳的 `error` 不為空且不 raise；`token` 不會出現在工作目錄的 `.git/config` 裡。
- [ ] **Step 2：執行測試，預期失敗。**
- [ ] **Step 3：實作 `gitrepo.py`、`sync.py` 與路由。**
- [ ] **Step 4：重跑測試，預期通過。**
- [ ] **Step 5：commit** `feat(api): git and backup import/export with three-way change detection`

### Task 8：發佈前清理

**Files:**
- Create: `api/challsmith_api/clients/chall_manager.py`、`api/challsmith_api/services/cleanup.py`、`api/challsmith_api/routers/cleanup.py`、`api/challsmith_api/cli/cleanup.py`
- Modify: `api/challsmith_api/main.py`
- Test: `api/tests/test_cleanup.py`

**Interfaces:**
- Consumes: `CtfdClient.list_users`、`delete_user`（Task 6）、`DockerOps.remove_containers`、`remove_networks`（Task 6）、`clear_sessions`（Task 3）。
- Produces：
  - `chall_manager.ChallManager(base_url, transport=None)`：
    - `list_instances() -> list[tuple[str, str]]`：`GET /api/v1/instance`，回傳 `(challenge_id, source_id)`。這是 grpc-gateway 的 server stream，回應是一行一個 `{"result": {...}}` 的 JSON。開工前在 VM 上用 `docker compose -p challsmith exec api` 對 chall-manager v0.6.7 實際呼叫一次，確認不帶 `source_id` 時會回傳所有 instance、以及欄位名稱是 `challengeId` 與 `sourceId`，把確認結果記在 report。如果不帶 `source_id` 拿不到全部，改成對 CTFd 每位使用者的 ID 逐一查詢。
    - `delete_instance(challenge_id, source_id) -> None`：`DELETE /api/v1/instance/{challenge_id}/{source_id}`，404 視為已刪除。
  - `cleanup.run_cleanup(db, cm: ChallManager, ctfd: CtfdClient, docker: DockerOps, log) -> dict`：依 spec 8.6 的順序：
    1. 刪除所有 instance，再刪除名稱以 `challenge-` 開頭的 container 與 network（第 1 部分的 scenario 以 `challenge-<identity>` 命名）
    2. 刪除 CTFd 中 `type` 不是 `admin` 的所有使用者
    3. `clear_sessions`
    回傳 `{"instances": n, "containers": n, "networks": n, "users": n, "sessions": n}`。某一步失敗時停止並 raise，已完成的步驟照實回報在 log。不刪除題目、image 或 web app 的其他資料。
  - `POST /cleanup` body `{"confirm": "CLEANUP"}`，`confirm` 不是這個字串時回 400。成功後因為 session 已清空，前端要導回登入頁。
  - 命令列：`python -m challsmith_api.cli.cleanup [--yes]`。沒有 `--yes` 時，先印出會做的事，要求輸入 `CLEANUP` 才執行，結果印在 stdout，失敗時以非 0 結束。

- [ ] **Step 1：寫失敗的測試**：用 fake 的 `ChallManager`、`CtfdClient` 與 `DockerOps`，三個 instance 都被刪除；使用者清單裡的 admin 沒被刪、兩位一般使用者被刪；session 表被清空，但 `Challenge` 與 `ChallengeFile` 的筆數不變；`confirm` 錯誤時回 400 且所有 fake 都沒被呼叫；`list_instances` 用 `MockTransport` 回兩行 stream JSON 時解析出兩筆；`delete_instance` 收到 404 不 raise。
- [ ] **Step 2：執行測試，預期失敗。**
- [ ] **Step 3：實作 `chall_manager.py`、`cleanup.py` 與路由。**
- [ ] **Step 4：重跑測試，預期通過。**
- [ ] **Step 5：commit** `feat(api): pre-release cleanup (instances, trainee users, sessions)`

### Task 9：web 的 BFF、登入與題目編輯

**Files:**
- Modify: `infra/compose.yaml`、`install.sh`（完成訊息加上 `Web app: http://127.0.0.1:3000`）
- Create: `web/`（`package.json`、`package-lock.json`、`next.config.ts`、`tsconfig.json`、`Dockerfile`、`middleware.ts`、`app/api/[...path]/route.ts`、`app/api/login/route.ts`、`app/api/logout/route.ts`、`app/login/page.tsx`、`app/page.tsx`（題目清單）、`app/new/page.tsx`、`app/c/[slug]/page.tsx`（編輯）、`lib/api.ts`）

**Interfaces:**
- Consumes: Task 3、4、5 的 API。
- Produces：
  - 環境變數：`API_URL`（預設 `http://api:8000`）。
  - cookie：`challsmith_session`，`HttpOnly`、`SameSite=Strict`、`Path=/`，有效期與 api 回傳的 `expires_at` 一致。VM 上只走 http，不設 `Secure`。
  - `POST /api/login`：轉給 api 的 `/auth/login`，成功時設 cookie，body 不回傳 token。`POST /api/logout`：轉給 api 並清掉 cookie。
  - `/api/[...path]`：把方法、query、body（以 stream 轉送，`duplex: "half"`）與 `Content-Type` 轉給 `API_URL/<path>`，加上 `Authorization: Bearer <cookie>`，回應原樣傳回（包括 `Content-Disposition` 與狀態碼）。非 GET、HEAD 的請求，`Origin` header 的 host 必須等於請求的 `Host`，否則回 403。`login` 也做同樣的 Origin 檢查。
  - `middleware.ts`：除了 `/login`、`/api/login` 與 Next.js 靜態資源，沒有 cookie 時導向 `/login`。api 回 401 時，前端導回 `/login`。
  - 頁面都是 client component，透過 `lib/api.ts` 的 `api(path, init)` 呼叫 `/api/...`。
    - 清單頁：每題顯示名稱、slug、分類、發佈狀態與 git 同步狀態，有「新增題目」的按鈕。
    - 新增頁：選範本（顯示 `description`）、填 slug 與標題，建立後進入編輯頁。
    - 編輯頁：左邊是題目資訊表單（`ChallengeMeta` 的所有欄位，描述是 Markdown 文字框，tags 用逗號分隔，services 可新增、刪除，image 型的 service 只填 image 與 env），右邊是檔案樹與 CodeMirror 編輯器（依副檔名套用語法，至少涵蓋 php、python、javascript、html、css、yaml、Dockerfile 與 nginx 設定的純文字），可新增檔案、刪除檔案、上傳單一檔案或 zip 到選定的 service 資料夾。儲存失敗時顯示 api 的錯誤訊息。
  - CodeMirror 與所有前端套件都打包在 image 裡，不從 CDN 載入，因為公司內的 vmdk 是離線的。
  - Dockerfile：多階段，`npm ci` 與 `next build` 使用 `output: "standalone"`，runtime 以非 root 使用者執行 `node server.js`，監聽 `0.0.0.0:3000`，build context 是 `web/`。
  - compose 新增 `web`：build `context: ../web`，proxy build args 與 `ctfd` 相同，`restart: unless-stopped`，environment 套 `*no-proxy` 並加 `API_URL: http://api:8000`，`ports: 127.0.0.1:3000:3000`，`depends_on: api`。

- [ ] **Step 1：在 VM 上以 `docker build web/` 確認可以 build**，並在 build 中執行 `npm run lint`（若 Next.js 版本不內建 lint，就執行 `tsc --noEmit`）。預期 build 成功、沒有型別錯誤。
- [ ] **Step 2：手動冒煙**：在 VM 上執行 `sudo ./install.sh`，確認不帶 cookie 的 `curl http://127.0.0.1:3000/` 回 307 或 308，再用 `curl` 走一遍：不帶 cookie 的 `GET /` 被導到 `/login`；`POST /api/login` 拿到 `Set-Cookie`；帶 cookie 的 `GET /api/challenges` 回 200；`Origin: http://evil.example` 的 `POST /api/challenges` 回 403。把結果記在 report。完整的自動化檢查在 Task 12。
- [ ] **Step 3：commit** `feat(web): BFF proxy, login and challenge editor`

### Task 10：web 的發佈、同步與清理頁面

**Files:**
- Create: `web/app/c/[slug]/publish/page.tsx`（或編輯頁內的區塊）、`web/app/sync/page.tsx`、`web/app/cleanup/page.tsx`
- Modify: `web/app/page.tsx`（導覽列）

**Interfaces:**
- Consumes: Task 6、7、8 的 API。
- Produces：
  - 發佈：按下「發佈」後 POST `/api/challenges/{slug}/publish`，每秒輪詢 `/api/publish-runs/{id}`，以等寬字型顯示 log 並自動捲到底，結束後顯示成功或失敗。409 時顯示「這題正在發佈中」。
  - 同步頁：
    - git 設定表單，token 欄位只顯示「已設定」，留空代表不變。
    - 「匯出到 git」，可勾選是否 push，顯示 commit 與 push 結果，push 失敗時顯示錯誤與改用備份的建議。
    - 「從 git 匯入」與「上傳備份」都先顯示預覽表（slug、狀態），`conflict` 的每一題要選「保留資料庫版」或「採用來源版」，全部選完才能按「套用」。409 時提示重新預覽。
    - 「下載備份」連到 `/api/backup`。
  - 清理頁：列出 spec 8.6 的三個動作，要求在輸入框輸入 `CLEANUP` 才能按下執行，完成後顯示各項數字，然後導回登入頁。

- [ ] **Step 1：在 VM 上 build web image**，預期成功、沒有型別錯誤。
- [ ] **Step 2：手動冒煙**：用瀏覽器或 `curl` 經由 web 完成一次發佈的輪詢與一次備份下載，記在 report。
- [ ] **Step 3：commit** `feat(web): publish log, git/backup sync and cleanup pages`

### Task 11：防火牆、隔離檢查與清理指令

**Files:**
- Modify: `infra/ops-firewall.nft`、`infra/challsmith-ops-firewall.service`、`tests/ops-isolation.sh`
- Create: `scripts/cleanup.sh`

**Interfaces:**
- Produces：
  - `scripts/cleanup.sh`：以 `aps` 執行 `docker compose -p challsmith exec api python -m challsmith_api.cli.cleanup "$@"`，供匯出 vmdk 前使用，需要互動確認時要配置 tty（不帶 `-T`）。
  - `infra/ops-firewall.nft` 新增一條：`meta skuid "ops" ip daddr 127.0.0.0/8 tcp dport 3000 reject with tcp reset`，註解說明新人用不到 web app，擋掉可以避免對登入頁暴力猜測。
  - `infra/challsmith-ops-firewall.service`（處理第 1 部分暫緩的「防火牆載入失敗時放行」）：`ExecStartPre=/usr/bin/chage -E 0 ops` 先鎖住 `ops`，`ExecStart` 載入 nft，`ExecStartPost=/usr/bin/chage -E -1 ops` 只在載入成功後解鎖。載入失敗時 `ops` 無法登入，`aps` 不受影響。
  - `tests/ops-isolation.sh` 新增：
    - `ops` 連 `127.0.0.1:3000` 必須失敗
    - `aps` 連 `127.0.0.1:3000` 必須成功
    - 「instance 網路不能連到服務」的檢查（處理第 1 部分暫緩的「bridge 之間的對外隔離未驗證」）：建立一個暫時的 `challenge-isocheck` docker network，在上面跑一個 alpine container，對 `chall-manager:8080`、`api:8000`、`ctfd-redis:6379`、`app-db:5432` 的 container IP（用 `docker inspect` 取得），以及 `ctfd` 的 container IP 的 8000 port 嘗試連線，全部必須失敗。結束時移除該 container 與 network。

- [ ] **Step 1：修改防火牆與隔離檢查，新增 `scripts/cleanup.sh`。**
- [ ] **Step 2：在 VM 上執行 `sudo ./install.sh`**，預期正常結束，`sudo nft list table inet challsmith_ops` 含有 3000 port 的規則。
- [ ] **Step 3：在 VM 上執行 `sudo tests/ops-isolation.sh`**，預期全部 PASS。如果 instance 網路的檢查失敗（代表 Docker 沒有隔離不同的 bridge），停下來在 report 中說明實際連得到的目標，並以 `DOCKER-USER` 鏈或 nft 規則補上「`challenge-*` 網路不能連到 compose 網路」的限制，再重跑。
- [ ] **Step 4：驗證防火牆的失敗關閉**：暫時把 `/etc/challsmith/ops-firewall.nft` 改成語法錯誤，`sudo systemctl restart challsmith-ops-firewall`，確認 unit 失敗且 `sudo chage -l ops` 顯示帳號已過期；改回正確內容再 restart，確認 `ops` 恢復未過期。記在 report。
- [ ] **Step 5：重開機後**，確認 web app 能登入、`sudo tests/ops-isolation.sh` 仍全部 PASS。
- [ ] **Step 6：commit** `feat(infra): firewall ops off the web app, fail closed, check instance isolation`

### Task 12：端對端測試與 README

**Files:**
- Create: `tests/e2e/test_webapp.py`、`tests/e2e/test_cleanup.py`
- Modify: `tests/e2e/conftest.py`、`tests/e2e/run.sh`、`README.md`、`README_ZH-TW.md`

**Interfaces:**
- Consumes: 整個系統。`run.sh` 從 env 檔多讀 `WEB_ADMIN_USER` 與 `WEB_ADMIN_PASSWORD` 傳進測試 container。
- Produces：`conftest.py` 新增 `web` fixture：一個 `requests.Session`，以 `Origin: http://127.0.0.1:3000` 登入 `http://127.0.0.1:3000/api/login`，測試結束時刪除自己建立的題目（`DELETE /api/challenges/<slug>`，連 CTFd 題目一起刪）。所有對 web app 的呼叫都經過 web 的 BFF，不直接打 api。

- [ ] **Step 1：寫測試**
  - `test_single_template_publish`：以 `php` 範本建立題目，用 `PUT /api/challenges/<slug>/files/services/app/index.php` 把內容改成 `<?php readfile('/flag.txt');`，發佈並輪詢到 `succeeded`；用 `register_user` 建立一位使用者，`start_instance` 拿到網址，讀到 `CTF{` 開頭的 flag，`submit` 回 `correct`；第二位使用者拿到的 flag 不同，用第一位的 flag 提交回 `incorrect`。
  - `test_multi_template_publish`：以 `nginx-php-db` 範本建題，把 php service 的 `index.php` 改成 `<?php echo getenv('FLAG');`，發佈後開 instance，讀到的 flag 提交回 `correct`。發佈後 `localhost:5000` 的 registry catalog（`GET /v2/_catalog`）包含 `challsmith/mirror/mariadb`。
  - `test_republish_updates_same_challenge`：發佈後改 `value` 再發佈，CTFd 上同一個 challenge ID 的分數變成新值，題目狀態從 `modified` 回到 `published`。
  - `test_publish_failure_keeps_ctfd`：發佈成功後，把 Dockerfile 改成 `FROM scratch\nRUN false`，再發佈，run 為 `failed` 且 log 有 docker 的錯誤，CTFd 上的題目 `additional` 與上一次相同。
  - `test_requires_login`：沒有 cookie 的 `GET http://127.0.0.1:3000/api/challenges` 回 401；帶錯誤 `Origin` 的 POST 回 403。
  - `test_backup_roundtrip`：下載 `/api/backup`，再上傳到 `/api/sync/archive/preview`，所有題目都是 `unchanged`。
  - `tests/e2e/test_cleanup.py::test_cleanup`：清理會刪掉所有 session 與一般使用者，會破壞其他測試的 fixture，所以放在獨立的檔案，`run.sh` 在其他測試都通過後另外執行一次 pytest 跑它。測試自己登入 web app，不用共用的 `web` fixture，建立使用者並開一個 instance 後 `POST /api/cleanup`，之後該使用者不存在於 CTFd，原本的 web session 回 401。`run.sh` 在這次 pytest 結束後以 `aps` 執行 `docker ps -a --filter name=^challenge-`，必須沒有任何 container。
- [ ] **Step 2：在 VM 上執行 `tests/e2e/run.sh`**，預期第 1 部分的 3 個測試加上這次新增的測試全部通過。
- [ ] **Step 3：更新兩份 README**：架構圖加上 web、api、app-db；新增「出題流程」（登入、從範本建題、編輯、發佈、看 log）、「git 與備份」（設定、匯入的五種狀態與衝突處理、下載備份不會改變比對基準的原因）、「發佈前清理」（按鈕與 `scripts/cleanup.sh`、清了什麼、沒清什麼）、範本清單；Security notes 補上 web app 的 session 設計、`ops` 被擋在 3000 port 之外、防火牆失敗時會鎖住 `ops`；Known limitations 補上：匯入預覽存在記憶體中，api 重啟後要重新預覽；在 CTFd 改了管理者密碼要同步改 `challsmith.env` 再重跑安裝指令。兩份內容一致，中文版依 zh-tw 寫作規範檢查。
- [ ] **Step 4：commit** `test(e2e): web app publish, sync and cleanup; docs: web app`

# challsmith 第 1 部分：基礎設施與 scenario 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 在一台全新的 Ubuntu 26.04 VM 上，用一個安裝指令架好 CTFd、chall-manager 與本機 registry，並提供 single、multi 兩個通用 scenario，讓手動建立的 `dynamic_iac` 題目能為每位使用者開出獨立的 instance，各自拿到不同的動態 flag。

**Architecture：** 所有服務由 `aps` 擁有的 docker compose 專案執行，對外 port 一律綁 `127.0.0.1`。兩個 scenario 是同一個 Go module 裡的兩個 Pulumi 程式，共用一個 `internal/scenario` 套件負責解析 `additional`、產生 flag 與 connection_info。scenario 用 `golang` container build，用 oras container 推到本機 registry，VM 上不安裝 Go 與 oras。

**Tech Stack：** Bash、Docker Engine 與 compose plugin（Ubuntu archive 的 `docker.io`、`docker-compose-v2`）、CTFd 3.8.8 + ctfd-chall-manager v0.10.1、chall-manager v0.6.7、Go 1.26、`github.com/ctfer-io/chall-manager/sdk` v0.6.7、`github.com/pulumi/pulumi-docker/sdk/v4`、`registry:3`、pytest（只用於端對端測試）。

**Spec：** `docs/superpowers/specs/2026-11-21-challsmith-design.md`（第 3、5、6、9.1 節）

**本計畫不包含：** 出題 web app、發佈前清理、git 與備份（第 2 份計畫），base images repo（第 3 份計畫）。

## Global Constraints

- 目標 OS：Ubuntu 26.04 Desktop。開發與測試在使用者提供的 Ubuntu 26.04 VM 上透過 SSH 進行，這台 VM 可以直接連外網。開始 Task 6 前向使用者要 IP 與帳密，不寫進 repo 或任何檔案。
- 帳號：`aps` 在 `docker` 群組，擁有所有服務。`ops` 沒有 sudo、不在 `docker` 群組。
- 所有發布到主機的 port 都只綁 `127.0.0.1`：CTFd `127.0.0.1:8000`、registry `127.0.0.1:5000`、題目 instance `127.0.0.1:<Docker 隨機分配>`。
- CTFd 採用 user mode，開放註冊。
- CTFd 上不建立靜態 flag，flag 只由 scenario 輸出。
- 開發 VM 的連線方式：`ssh -i ~/.ssh/challsmith_vm -o BatchMode=yes <user>@<dev-vm>（連線資訊在本機 .env）`，已裝 Docker 29.10（`docker-ce`）、Compose v5.8、Go 1.26.8、git、rsync。Windows 端沒有 rsync，用 `tar --exclude=./.env --exclude=./.git -cf - . | ssh -i ~/.ssh/challsmith_vm <user>@<dev-vm>（連線資訊在本機 .env） 'mkdir -p ~/challsmith && tar -xf - -C ~/challsmith'` 把 repo 同步到 VM 的 `~/challsmith`，再執行測試。不讀取、不印出 repo 根目錄的 `.env`，它含有 VM 的帳密且已列在 `.gitignore`。不安裝 shellcheck。
- 版本固定：`ctfd/ctfd:3.8.8`、ctfd-chall-manager `v0.10.1`、`ctferio/chall-manager:v0.6.7`、`ctferio/chall-manager-janitor:v0.6.7`、`ctferio/ctfd-setup:v1.7.1`、`registry:3`、`golang:1.26`。compose 裡每個 image 都寫明 tag。
- 公司內的 proxy 只有 Ubuntu apt、Docker Hub、git、pip、npm、apk、Go module 與 Burp 下載，安裝流程不能依賴其他外部網站。Pulumi docker provider plugin 由安裝指令從 GitHub release tarball 安裝（Task 7b）。oras image 在 ghcr.io，留給第 3 份計畫處理，這裡只要求能用設定覆寫來源。
- `additional` 是 string 對 string 的 map，所有數字與 JSON 都以字串傳入。
- 每個 repo 都要有 `README.md`（英文）與 `README_ZH-TW.md`（繁體中文），內容一致，開頭互相連結。
- commit 訊息結尾加上 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Review Focus

- 題目 instance 的 port 不小心綁到 `0.0.0.0`，等於把漏洞主機暴露到 OA 網路。端對端測試要用 `ss -ltn` 確認沒有任何 challsmith 相關的 port 綁在 `0.0.0.0` 或 `[::]`（Task 8）。
- 使用者 A 的 flag 由使用者 B 提交時必須判定錯誤，同一題兩位使用者拿到的 flag 必須不同（Task 8）。
- `additional` 缺少 `flag` 或 `image`、`port` 不是數字、`services` 不是合法 JSON 或沒有恰好一個入口服務時，scenario 要回傳清楚的錯誤，不能像上游範例那樣默默套用預設 image（Task 2）。
- VM 重開機後，所有服務自動回來，原本還在跑的 instance container 也會回來，chall-manager 仍能管理它（Task 7 的手動驗證）。重開機後 Docker 可能分配不同的 host port，要記錄實際觀察到的行為。
- 重複執行安裝指令不能失敗，也不能覆蓋已存在的 CTFd 資料（Task 7）。

---

## 檔案結構

```
challsmith/
├─ README.md / README_ZH-TW.md          Task 9
├─ .gitignore                           Task 1
├─ challsmith.env.example               Task 6（安裝設定範本）
├─ install.sh                           Task 7
├─ infra/
│  ├─ compose.yaml                      Task 6
│  └─ ctfd-setup.yaml.tmpl              Task 6（ctfd-setup 設定範本）
├─ scenarios/
│  ├─ go.mod / go.sum                   Task 2
│  ├─ Pulumi.yaml                       Task 5（build 時使用）
│  ├─ internal/scenario/
│  │  ├─ config.go / config_test.go     Task 2（解析 additional）
│  │  ├─ flag.go / flag_test.go         Task 2（產生 flag）
│  │  └─ conninfo.go / conninfo_test.go Task 2
│  ├─ single/main.go / main_test.go     Task 3
│  └─ multi/main.go / main_test.go      Task 4
├─ scripts/
│  └─ push-scenarios.sh                 Task 5
├─ examples/
│  ├─ hello-php/                        Task 8（single 範例題）
│  └─ hello-multi/                      Task 8（multi 範例題：nginx + php + mariadb）
└─ tests/e2e/
   ├─ requirements.txt                  Task 8
   ├─ conftest.py                       Task 8（CTFd API helper）
   ├─ test_single.py / test_multi.py    Task 8
   └─ run.sh                            Task 8
```

---

### Task 1：repo 骨架

**Files:**
- Create: `.gitignore`

- [ ] **Step 1：建立 `.gitignore`**，內容涵蓋 `challsmith.env`（真正的安裝設定，含密碼）、`infra/ctfd-setup.yaml`（由範本產生）、`scenarios/bin/`、`tests/e2e/.venv/`、`__pycache__/`。
- [ ] **Step 2：Commit**

```bash
git add .gitignore
git commit -m "chore: add gitignore"
```

---

### Task 2：`internal/scenario` 共用套件

**Files:**
- Create: `scenarios/go.mod`、`scenarios/internal/scenario/{config,flag,conninfo}.go` 與對應的 `_test.go`

**Interfaces:**
- Produces（Task 3、4 使用）：

```go
package scenario

type Service struct {
    Name  string            `json:"name"`
    Image string            `json:"image"`
    Port  int               `json:"port,omitempty"`
    Entry bool              `json:"entry,omitempty"`
    Env   map[string]string `json:"env,omitempty"`
}

type Common struct {
    Protocol   string  // "http" 或 "tcp"
    Flag       string  // flag 範本的內文
    FlagPrefix string  // 預設 "CTF"
    MemoryMB   int     // 由 "256m"、"1g" 這類字串換算，預設 256
    CPUs       float64 // 預設 0.5
}

type SingleConfig struct {
    Common
    Image string
    Port  int // 預設 80
}

type MultiConfig struct {
    Common
    Services []Service // 恰好一個 Entry，Entry 必須有 Port
}

func ParseSingle(additional map[string]string) (SingleConfig, error)
func ParseMulti(additional map[string]string) (MultiConfig, error)
func BuildFlag(identity string, c Common) string      // 回傳 "<prefix>{<variated>}"
func ConnectionInfo(protocol string, hostPort int) string
```

- [ ] **Step 1：`go mod init github.com/<使用者的 GitHub 帳號>/challsmith/scenarios`**，Go 版本 `1.26`，加入 `github.com/ctfer-io/chall-manager/sdk v0.6.7`。GitHub 帳號名稱先問使用者，不知道時用 `challsmith/scenarios` 當 module path。
- [ ] **Step 2：寫失敗的測試** `config_test.go`：

```go
func TestParseSingleDefaults(t *testing.T) {
    c, err := ParseSingle(map[string]string{"image": "localhost:5000/x:1", "flag": "abc"})
    require.NoError(t, err)
    assert.Equal(t, 80, c.Port)
    assert.Equal(t, "http", c.Protocol)
    assert.Equal(t, "CTF", c.FlagPrefix)
    assert.Equal(t, 256, c.MemoryMB)
    assert.Equal(t, 0.5, c.CPUs)
}
func TestParseSingleRequiresImageAndFlag(t *testing.T) // 分別缺 image、缺 flag，都要回傳 error，錯誤訊息含缺少的鍵名
func TestParseSingleRejectsBadPort(t *testing.T)       // "port": "abc"、"0"、"70000" 都回傳 error
func TestParseSingleRejectsBadProtocol(t *testing.T)   // "protocol": "udp" 回傳 error
func TestParseMemory(t *testing.T)                     // "512m"→512、"1g"→1024、"abc"→error
func TestParseMultiEntry(t *testing.T)                 // 合法 services JSON，回傳 3 個 Service，Entry 是 "web" 且 Port 80
func TestParseMultiRejects(t *testing.T)               // 非法 JSON、沒有 entry、兩個 entry、entry 沒有 port、name 重複、name 不符 ^[a-z0-9-]+$，都回傳 error
```

`flag_test.go`：

```go
func TestBuildFlagFormat(t *testing.T) {
    f := BuildFlag("0123456789abcdef", Common{Flag: "php_strcmp", FlagPrefix: "CTF"})
    assert.Regexp(t, `^CTF\{.+\}$`, f)
}
func TestBuildFlagDiffersByIdentity(t *testing.T) // 兩個不同 identity 產生不同 flag
func TestBuildFlagDeterministic(t *testing.T)     // 同一 identity 呼叫兩次結果相同
```

`conninfo_test.go`：`ConnectionInfo("http", 32768) == "http://localhost:32768"`，`ConnectionInfo("tcp", 32768) == "nc localhost 32768"`。

- [ ] **Step 3：執行測試確認失敗**

Run：`cd scenarios && go test ./internal/...`（在開發機上用 `docker run --rm -v "$PWD":/src -w /src/scenarios golang:1.26 go test ./internal/...`）
Expected：編譯失敗，函式未定義。

- [ ] **Step 4：實作。** `BuildFlag` 呼叫 `sdk.Variate(identity, c.Flag)`，用預設選項（不含特殊字元），外面包上 `c.FlagPrefix + "{" + ... + "}"`。`ParseMulti` 從 `additional["services"]` 用 `encoding/json` 解析。
- [ ] **Step 5：執行測試確認通過**，Expected：PASS。
- [ ] **Step 6：Commit**

```bash
git add scenarios
git commit -m "feat(scenarios): parse additional config and build dynamic flags"
```

---

### Task 3：single scenario

**Files:**
- Create: `scenarios/single/main.go`、`scenarios/single/main_test.go`

**Interfaces:**
- Consumes：Task 2 的 `ParseSingle`、`BuildFlag`、`ConnectionInfo`。
- Produces：`func deploy(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error`，`main()` 只呼叫 `sdk.Run(deploy)`。

建立的資源（以 ctfd-chall-manager `hack/docker-scenario/main.go` 為起點）：
- `docker.NewRemoteImage`：`Name` 為 `cfg.Image`，`KeepLocally: true`。
- `docker.NewContainer`，名稱 `challenge-<identity>`：
  - `Envs` 包含 `FLAG=<BuildFlag 的結果>`
  - `Ports` 一個：`Internal: cfg.Port`、`Ip: "127.0.0.1"`、`Protocol: "tcp"`
  - `Memory: cfg.MemoryMB`
  - CPU 上限：pulumi-docker v4 的 `ContainerArgs` 若有 `Cpus` 欄位就用它，沒有就用 `CpuShares: int(cfg.CPUs*1024)`，實作前查 provider 文件確認
  - `Restarts`／`Restart: "unless-stopped"`，`Rm: false`，讓 VM 重開機後 instance 會回來
- `resp.ConnectionInfo`：由 `container.Ports[0].External` 經 `ConnectionInfo(cfg.Protocol, port)` 產生。
- `resp.Flags`：`pulumi.ToStringArray([]string{flag}).ToStringArrayOutput()`。不使用已標示 deprecated 的 `resp.Flag`。

- [ ] **Step 1：寫失敗的測試** `main_test.go`，用 `pulumi.RunErr` 搭配 `pulumi.WithMocks`。mock 的 `NewResource` 記錄每個資源的 type 與 inputs，container 的 `ports` 輸出補上 `external: 32768`。建構 `sdk.Request` 時直接給 `Config: &sdk.Configuration{Identity: "0123456789abcdef", Additional: {...}}`：

```go
func TestSingleCreatesLockedDownContainer(t *testing.T)
// 斷言：恰好一個 docker:index/container:Container
//      inputs.ports[0].ip == "127.0.0.1"、inputs.ports[0].internal == 80
//      inputs.envs 含有以 "FLAG=CTF{" 開頭的項目
//      inputs.memory == 256
//      inputs.restart == "unless-stopped"
//      inputs.name == "challenge-0123456789abcdef"
func TestSingleOutputsFlagAndConnectionInfo(t *testing.T)
// 斷言：resp.Flags 只有一個值，等於 BuildFlag("0123456789abcdef", ...)，也等於 envs 中 FLAG 的值
//      resp.ConnectionInfo == "http://localhost:32768"
func TestSingleTCP(t *testing.T)           // protocol=tcp 時 ConnectionInfo == "nc localhost 32768"
func TestSingleInvalidConfigFails(t *testing.T) // 缺 flag 時 RunErr 回傳 error，且沒有建立任何資源
```

- [ ] **Step 2：執行測試確認失敗**，Run：`go test ./single/...`，Expected：FAIL。
- [ ] **Step 3：實作 `deploy`**。
- [ ] **Step 4：執行測試確認通過**，Expected：PASS。
- [ ] **Step 5：Commit**：`feat(scenarios): add single-container scenario`

---

### Task 4：multi scenario

**Files:**
- Create: `scenarios/multi/main.go`、`scenarios/multi/main_test.go`

**Interfaces:**
- Consumes：Task 2 的 `ParseMulti`、`BuildFlag`、`ConnectionInfo`。
- Produces：`func deploy(...) error`，簽章同 Task 3。

建立的資源：
- 一個 `docker.NewNetwork`，名稱 `challenge-<identity>`，`Internal: false`，不對外發布。
- 每個 service：一個 `RemoteImage` 與一個 `Container`，container 名稱 `challenge-<identity>-<service.Name>`，加入上述 network 並設定 `Aliases: [service.Name]`，讓服務之間以名稱互連。
- 每個 container 的 `Envs` 都含 `FLAG=<flag>`，再加上 `service.Env`（同名鍵以 `service.Env` 為準，但 `FLAG` 不可被覆寫）。
- 只有 entry service 設定 `Ports`，規則同 Task 3（`Ip: "127.0.0.1"`）。其他 service 不發布 port。
- 資源上限與 restart 規則同 Task 3，套用在每個 container。
- `resp.ConnectionInfo` 與 `resp.Flags` 同 Task 3，port 取自 entry container。

- [ ] **Step 1：寫失敗的測試**：

```go
func TestMultiOneNetworkAllAttached(t *testing.T)
// 3 個 service：恰好一個 Network、3 個 Container，每個 container 的 networksAdvanced 都指向該 network 並帶有自己的 alias
func TestMultiOnlyEntryPublishes(t *testing.T)
// 只有 web 有 ports，且 ip == "127.0.0.1"；php、db 的 ports 為空
func TestMultiFlagInAllContainers(t *testing.T)
// 3 個 container 的 envs 都含相同的 FLAG，且 db 的 service.Env 也在
func TestMultiServiceEnvCannotOverrideFlag(t *testing.T)
// service.Env 含 "FLAG": "x" 時，container 的 FLAG 仍是 BuildFlag 的結果
func TestMultiOutputs(t *testing.T) // ConnectionInfo == "http://localhost:32768"，Flags 一個值
```

- [ ] **Step 2：執行測試確認失敗**。
- [ ] **Step 3：實作 `deploy`**。
- [ ] **Step 4：執行測試確認通過**。
- [ ] **Step 5：Commit**：`feat(scenarios): add multi-container scenario`

---

### Task 5：build 並推送 scenario

**Files:**
- Create: `scenarios/Pulumi.yaml`、`scripts/push-scenarios.sh`

**Interfaces:**
- Produces：registry 中的兩個 scenario，CTFd 題目的 `scenario` 欄位填 `registry:5000/challsmith/scenarios/single:v1` 與 `registry:5000/challsmith/scenarios/multi:v1`（chall-manager 在 compose 網路內用服務名稱 `registry` 存取）。

`scripts/push-scenarios.sh [tag]` 的行為（tag 預設 `v1`）：
1. 對 `single`、`multi` 各執行一次：`docker run --rm -v <repo>/scenarios:/src -w /src -e CGO_ENABLED=0 -e GOPROXY golang:1.26 go build -o bin/<name>/main ./<name>`。`GOPROXY` 從環境變數傳入，未設定時用 Go 預設值。
2. 在 `bin/<name>/` 放一份 `Pulumi.yaml`，內容為：

```yaml
name: <name>
runtime:
  name: go
  options:
    binary: ./main
```

3. 用 oras container 推送：`docker run --rm --network host -v <repo>/scenarios/bin/<name>:/work -w /work "${ORAS_IMAGE:-ghcr.io/oras-project/oras:v1.3.0}" push --plain-http localhost:5000/challsmith/scenarios/<name>:<tag> --artifact-type application/vnd.ctfer-io.scenario main:application/vnd.ctfer-io.file Pulumi.yaml:application/vnd.ctfer-io.file`。實作前確認 oras image 的最新穩定 tag 與 `--plain-http` 旗標名稱。
4. 腳本用 `set -euo pipefail`，可重複執行。

- [ ] **Step 1：寫 `Pulumi.yaml` 與 `push-scenarios.sh`**，執行 `bash -n scripts/push-scenarios.sh`，Expected：沒有語法錯誤。不安裝 shellcheck。
- [ ] **Step 2：在開發 VM 上啟動暫時的 registry 驗證**：`docker run -d --rm -p 127.0.0.1:5000:5000 --name tmp-registry registry:3`，執行腳本，再執行 `curl -s localhost:5000/v2/challsmith/scenarios/single/tags/list`。Expected：`{"name":"challsmith/scenarios/single","tags":["v1"]}`，multi 同理。驗證完停掉暫時的 registry。
- [ ] **Step 3：Commit**：`feat(scenarios): build and push scenarios with containers`

---

### Task 6：compose 與安裝設定

**Files:**
- Create: `infra/compose.yaml`、`infra/ctfd-setup.yaml.tmpl`、`challsmith.env.example`

`challsmith.env.example` 的鍵（全部附註解，說明用途與預設值）：

| 鍵 | 用途 |
|---|---|
| `CTFD_ADMIN_NAME`、`CTFD_ADMIN_EMAIL`、`CTFD_ADMIN_PASSWORD` | CTFd 管理者 |
| `CTFD_SECRET_KEY` | CTFd 的 `SECRET_KEY`，留空時安裝指令自動產生 |
| `CTFD_DB_PASSWORD` | MariaDB 密碼，留空時自動產生 |
| `CM_MANA_TOTAL` | 每位使用者的 mana 上限，預設 `5` |
| `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` | 選填，套用到 apt 與 Docker daemon |
| `DOCKER_REGISTRY_MIRROR` | 選填，Docker Hub proxy 的位址，寫進 `daemon.json` 的 `registry-mirrors` |
| `GOPROXY` | 選填，build scenario 時使用 |
| `ORAS_IMAGE` | 選填，預設 `ghcr.io/oras-project/oras:v1.3.0` |
| `BURP_DOWNLOAD_URL` | 預設 portswigger 的 Linux Community 版下載網址 |

`infra/compose.yaml` 的服務，全部加上 `restart: unless-stopped`（ctfd-setup 除外）：

| 服務 | image | 重點設定 |
|---|---|---|
| `ctfd` | 見 Step 1 | `127.0.0.1:8000:8000`；`DATABASE_URL=mysql+pymysql://ctfd:${CTFD_DB_PASSWORD}@ctfd-db/ctfd`、`REDIS_URL=redis://ctfd-redis:6379`、`SECRET_KEY`、`PLUGIN_SETTINGS_CM_API_URL=http://chall-manager:8080`、`PLUGIN_SETTINGS_CM_MANA_TOTAL=${CM_MANA_TOTAL}`；volume `ctfd-uploads` |
| `ctfd-db` | `mariadb:11` | volume `ctfd-db` |
| `ctfd-redis` | `redis:7` | 無 port |
| `ctfd-setup` | `ctferio/ctfd-setup:v1.7.1` | `restart: "no"`；`URL=http://ctfd:8000`、`FILE=/ctfd-setup.yaml`；掛載 `./ctfd-setup.yaml`；等待 ctfd healthy |
| `chall-manager` | `ctferio/chall-manager:v0.6.7` | 無 port；`OCI_INSECURE=true`、`DIR=/var/lib/chall-manager`、`PULUMI_HOME=/var/lib/pulumi`；volume `cm-state`、`cm-pulumi`；掛載 `/var/run/docker.sock` |
| `chall-manager-janitor` | `ctferio/chall-manager-janitor:v0.6.7` | `URL=chall-manager:8080`、`TICKER=1m` |
| `registry` | `registry:3` | `127.0.0.1:5000:5000`；volume `registry` |

`ctfd` 的 healthcheck 沿用 ctfd-chall-manager `hack/docker-compose.yml` 的寫法。compose 專案名稱固定為 `challsmith`，讀取 repo 根目錄的 `challsmith.env`（`env_file` 與變數替換）。

`infra/ctfd-setup.yaml.tmpl`：以 ctfd-chall-manager 的 `hack/.ctfd.yaml` 為基礎，改成 `mode: users`，`admin` 三個欄位用 `${CTFD_ADMIN_NAME}` 等變數，`appearance.name: challsmith`，保留 `accounts.incorrect_submissions_per_minute` 的預設值（不要沿用上游的 9999）。

- [ ] **Step 1：決定 CTFd image。** 在開發 VM 上執行 `docker manifest inspect ctferio/ctfd:v0.10.1`（或查 Docker Hub 上 ctferio/ctfd 的 tag 清單），確認有沒有內含 ctfd-chall-manager v0.10.1、底層為 CTFd 3.8.8 的 tag。有的話直接使用該 tag。沒有的話，建立 `infra/ctfd/Dockerfile`：`FROM ctfd/ctfd:3.8.8`，用 `git clone --depth 1 --branch v0.10.1` 把 plugin 放到 `/opt/CTFd/CTFd/plugins/ctfd_chall_manager`，有 `requirements.txt` 時一併 `pip install`。在 commit 訊息記錄選了哪一種。
- [ ] **Step 2：寫三個檔案**。
- [ ] **Step 3：驗證設定**：`cp challsmith.env.example challsmith.env`，填入測試用的值，`envsubst < infra/ctfd-setup.yaml.tmpl > infra/ctfd-setup.yaml`，再執行 `docker compose -f infra/compose.yaml --env-file challsmith.env config`。Expected：沒有錯誤，輸出中每個 `published` port 都帶 `host_ip: 127.0.0.1`。
- [ ] **Step 4：在開發 VM 上啟動**：`docker compose ... up -d`，等兩分鐘後執行 `docker compose ... ps`。Expected：ctfd 為 healthy，ctfd-setup 以 exit 0 結束，其他服務為 running。用 `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/login` 確認回 `200`，用管理者帳號登入，確認管理介面有 chall-manager plugin 的設定頁。
- [ ] **Step 5：`docker compose ... down`（保留 volume），Commit**：`feat(infra): add compose stack and install config`

---

### Task 7：安裝指令

**Files:**
- Create: `install.sh`

`sudo ./install.sh` 的步驟，每一步都必須可重複執行：
1. 檢查以 root 執行、OS 為 Ubuntu 26.04，repo 根目錄有 `challsmith.env`，缺少時印出「先複製 `challsmith.env.example` 並填寫」後結束。
2. 若設定了 `HTTP_PROXY`／`HTTPS_PROXY`，寫入 `/etc/apt/apt.conf.d/90challsmith-proxy`。
3. `apt-get install -y curl gettext-base rsync openssl`。若 `docker` 與 `docker compose` 都已經可以使用（例如開發 VM 已裝 Docker 官方的 `docker-ce` 與 `docker-compose-plugin`），跳過 Docker 安裝。否則 `apt-get install -y docker.io docker-compose-v2`。不要在已裝 `docker-ce` 的機器上安裝 `docker.io`，兩者會衝突。
4. 寫入 `/etc/docker/daemon.json`：有 `DOCKER_REGISTRY_MIRROR` 時加 `registry-mirrors`。有 proxy 時寫 systemd drop-in `/etc/systemd/system/docker.service.d/http-proxy.conf`，`NO_PROXY` 必須包含 `localhost,127.0.0.1,registry`。重新載入並 `systemctl enable --now docker`。已存在的 `daemon.json` 先備份成 `daemon.json.bak`。
5. 建立 `aps`（加入 `docker` 群組）與 `ops`（不加入任何額外群組）。兩個帳號已存在時跳過。密碼不在腳本裡設定，結尾提示管理者用 `passwd` 設定。
6. 用 `rsync` 把 repo 複製到 `/opt/challsmith`，排除 `.git`，擁有者 `aps:aps`，權限 `750`，`challsmith.env` 權限 `600`。
7. 補上 `CTFD_SECRET_KEY`、`CTFD_DB_PASSWORD` 的自動產生值（`openssl rand -hex 32`），只在空白時寫回 `/opt/challsmith/challsmith.env`，已有值就不動，避免重跑時改掉資料庫密碼。
8. 以 `envsubst` 產生 `/opt/challsmith/infra/ctfd-setup.yaml`。
9. 以 `aps` 身分執行 `docker compose up -d`，等 registry 可以連線後，以 `aps` 身分執行 `scripts/push-scenarios.sh v1`。
10. Burp Suite：`/opt/BurpSuiteCommunity` 不存在時，用 `BURP_DOWNLOAD_URL` 下載安裝檔，以 `-q -dir /opt/BurpSuiteCommunity` 靜默安裝，並在 `/usr/share/applications` 建立桌面捷徑。
11. 最後印出 CTFd 網址 `http://127.0.0.1:8000` 與待辦事項（設定 `aps`、`ops` 密碼）。

- [ ] **Step 1：寫 `install.sh`**，`bash -n install.sh` 沒有語法錯誤。
- [ ] **Step 2：在開發 VM 上執行** `sudo ./install.sh`。Expected：exit 0，`docker compose -p challsmith ps` 同 Task 6 Step 4，`curl -s localhost:5000/v2/_catalog` 列出兩個 scenario。
- [ ] **Step 3：驗證帳號與權限**：

```bash
id ops                                    # Expected：沒有 docker 群組
sudo -u ops docker ps                     # Expected：permission denied
sudo -u ops cat /opt/challsmith/challsmith.env  # Expected：Permission denied
ss -ltn | grep -E ':(8000|5000)\s'        # Expected：只出現 127.0.0.1
```

- [ ] **Step 4：再執行一次** `sudo ./install.sh`。Expected：exit 0，`challsmith.env` 中的 `CTFD_DB_PASSWORD` 沒有變，CTFd 管理者仍能登入。
- [ ] **Step 5：重開機驗證**（Task 8 完成後再做一次，此時要有一個執行中的 instance）：`sudo reboot`，開機後不手動執行任何指令，確認 `docker compose -p challsmith ps` 全部 running，CTFd 可以登入。把觀察結果記錄在 commit 訊息。
- [ ] **Step 6：Commit**：`feat: add one-shot installer`

---

### Task 8：範例題與端對端測試

**Files:**
- Create: `examples/hello-php/{Dockerfile,index.php}`、`examples/hello-multi/{web/Dockerfile,web/default.conf,app/Dockerfile,app/index.php}`、`tests/e2e/{requirements.txt,conftest.py,test_single.py,test_multi.py,run.sh}`

範例題：
- `hello-php`：`FROM php:8.3-apache`，`index.php` 在 `?give=1` 時印出 `getenv('FLAG')`。
- `hello-multi`：`web` 是 `nginx:alpine`，`default.conf` 把請求 proxy 到 `app:80`。`app` 是 `php:8.3-apache`，裝 `pdo_mysql`，`index.php` 連到 `db`，把 `getenv('FLAG')` 寫進資料表再讀出來印出。`db` 直接用 `mariadb:11`，`env` 給 `MARIADB_ROOT_PASSWORD`、`MARIADB_DATABASE`。`app` 要能在 DB 尚未就緒時重試連線幾秒。

`tests/e2e/run.sh`：在已安裝的 VM 上以 `aps` 身分執行。先 build 兩個範例的 image 並推到 `localhost:5000/challsmith/examples/...:test`，再用 `docker run --rm --network host -v <repo>/tests/e2e:/t -w /t python:3.13-slim sh -c "pip install -r requirements.txt && pytest -v"` 執行測試，CTFd 管理者帳密由環境變數傳入。

`conftest.py` 提供的 fixture 與 helper：
- `admin`：以管理者帳號登入（取 `/login` 頁面的 nonce 再 POST），用 `POST /api/v1/tokens` 建立 API token，回傳帶 token 的 `requests.Session`。
- `register_user(name) -> requests.Session`：走 `/register` 註冊新使用者，回傳已登入的 session 與 CSRF nonce。
- `create_challenge(admin, name, scenario, additional: dict) -> int`：`POST /api/v1/challenges`，body 包含 `name`、`category: "e2e"`、`description`、`type: "dynamic_iac"`、`initial: 100`、`minimum: 100`、`decay: 0`、`function: "linear"`、`state: "visible"`、`scenario`、`additional`、`mana_cost: 1`、`timeout: 600`。不建立任何靜態 flag。測試結束時刪除題目。
- `start_instance(user, challenge_id) -> str`：`POST /api/v1/plugins/ctfd-chall-manager/instance`，body `{"challengeId": ...}`，再以 `GET` 輪詢直到拿到 `connectionInfo`，回傳該字串。實作時以 plugin 實際的回應格式為準。
- `submit(user, challenge_id, flag) -> str`：`POST /api/v1/challenges/attempt`，回傳 `data.status`。

- [ ] **Step 1：寫測試** `test_single.py`：

```python
def test_two_users_get_distinct_working_flags(admin, register_user, create_challenge):
    cid = create_challenge(admin, "hello-php", "registry:5000/challsmith/scenarios/single:v1",
                           {"image": "localhost:5000/challsmith/examples/hello-php:test",
                            "port": "80", "flag": "hello_php"})
    alice, bob = register_user("alice"), register_user("bob")
    url_a, url_b = start_instance(alice, cid), start_instance(bob, cid)
    flag_a = requests.get(url_a + "/?give=1").text.strip()
    flag_b = requests.get(url_b + "/?give=1").text.strip()
    assert flag_a.startswith("CTF{") and flag_b.startswith("CTF{")
    assert flag_a != flag_b
    assert submit(bob, cid, flag_a) == "incorrect"
    assert submit(alice, cid, flag_a) == "correct"

def test_instance_ports_bound_to_localhost_only(...):
    # 開一個 instance 後，解析 `ss -ltnH` 的輸出（測試 container 用 host network，可直接執行），
    # 斷言 connection_info 的 port 只出現在 127.0.0.1，且整台機器沒有 8000、5000 或該 port 綁在 0.0.0.0 / [::]
```

`test_multi.py`：

```python
def test_multi_container_flag_through_db(admin, register_user, create_challenge):
    # scenario 用 multi:v1，services 為 web（entry, port 80）、app、db（mariadb:11）
    # 取得 connection_info 後輪詢最多 60 秒，直到回應含 "CTF{"
    # 斷言該 flag 提交後為 "correct"
```

- [ ] **Step 2：在開發 VM 上執行** `tests/e2e/run.sh`。第一次執行前若還沒實作完範例或 helper，Expected：FAIL。
- [ ] **Step 3：補完範例題與 helper**，直到全部通過。
- [ ] **Step 4：執行** `tests/e2e/run.sh`。Expected：3 個測試全部 PASS。
- [ ] **Step 5：做 Task 7 Step 5 的重開機驗證。** 先手動開一個 hello-php instance 不要關，重開機後確認該 container 回來了，並用 `docker port` 記錄 host port 有沒有改變。若 port 改變，在 README 的「已知限制」寫明：重開機後請在 CTFd 上重新開啟 instance。
- [ ] **Step 6：Commit**：`test: add example challenges and end-to-end tests`

---

### Task 9：README（英文與繁體中文）

**Files:**
- Create: `README.md`、`README_ZH-TW.md`

兩份內容一致，開頭第一行互相連結（`[繁體中文](README_ZH-TW.md)`、`[English](README.md)`）。章節：

1. 這是什麼：一段話說明用途與架構，附第 5 節的架構圖。
2. 安裝：準備 Ubuntu 26.04 Desktop、複製並填寫 `challsmith.env`、`sudo ./install.sh`、設定 `aps` 與 `ops` 密碼。
3. 手動建立題目：在 CTFd 管理介面建立 `dynamic_iac` 題目，`scenario` 欄位的值，以及 single、multi 的 `additional` 鍵（照 spec 6.1、6.2 的表格）。強調不要建立靜態 flag。
4. 題目 image 怎麼讀 flag：環境變數 `FLAG`。
5. 測試：`scenarios` 的 `go test` 與 `tests/e2e/run.sh`。
6. 已知限制：Task 8 Step 5 的觀察結果，以及「公司內需要第 3 部分預先包好的 chall-manager 與 oras image」。

- [ ] **Step 1：寫 `README.md`**。
- [ ] **Step 2：寫 `README_ZH-TW.md`**，用 zh-tw-writing skill 的 `check_zh.py` 檢查，修正提示的問題。
- [ ] **Step 3：Commit**：`docs: add English and Traditional Chinese READMEs`

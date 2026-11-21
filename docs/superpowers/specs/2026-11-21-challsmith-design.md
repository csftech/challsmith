# challsmith 設計文件

日期：2026-11-21

## 1. 目的

challsmith 是公司新人資安訓練用的 CTF 環境。新人會拿到一份 vmdk，自己匯入 VMware，裡面已經裝好 CTFd 與所有 web 題，點開題目就會為他開一個獨立的 container，flag 也是每個人不一樣。

這套環境以 CTFd 加上 ctfd-chall-manager 為基礎。作者之前做過 PoC，遇到三個重複性很高的工作：

1. 每出一題都要寫或修改 Pulumi scenario。
2. 每出一題都要寫 Dockerfile 再 build 成 image。
3. 每出一題都要到 CTFd 一欄一欄填標題、描述、分類與標籤。

challsmith 的核心是一個出題用的 web app，把這三件事收斂成「選範本、放程式碼、填題目資訊、按發佈」。整個專案（程式碼與 docker 基礎設施）要包成在公司內的 Ubuntu VM 上用一個指令就能架起來的形式。

之所以每人發一份 vmdk，而不是架一台共用的題目機，是因為公司不允許架設含有各種漏洞的共用主機。

## 2. 目標、非目標與反目標

### 目標

- 在一台 Ubuntu 26.04 VM 上，用一個安裝指令完成所有元件的安裝，所有服務以 container 執行，重開機後自動啟動。
- 新人用低權限帳號登入，打開瀏覽器進 CTFd 自行註冊，點題目就開出自己的 instance，用 Burp Suite Community 解題。
- 每個 instance 的 flag 由 scenario 動態產生，新人之間互抄 flag 無效，即使大家的 VM 都是從同一份 vmdk 複製出來的也一樣。
- 作者在 web app 上完成出題：從範本建立題目、編輯 Dockerfile 與程式碼、設定 flag、填寫 CTFd 題目資訊，按一次發佈就完成 build image、推送 registry、建立或更新 CTFd 題目。
- 支援單一 container 與多 container（例如 nginx + php-fpm + DB）兩種題目。
- scenario 要能處理 TCP 服務，以後出 pwn 題時不用重寫。
- 題目資料以資料庫為正本，同時能和 git repo 互相匯入匯出，並提供備份壓縮檔。
- 提供「發佈前清理」，在匯出 vmdk 前清掉測試痕跡。
- 每個 repo（challsmith 與第 10 節的 base images repo）都提供中英兩版 README，`README.md` 是英文版，`README_ZH-TW.md` 是繁體中文版，兩版內容一致，開頭互相連結。

### 非目標

- 不防止新人拆解 vmdk。新人能拿到 VM 的磁碟，就能取得 root，讀到 image、題目原始碼與 web app 帳密，這是可以接受的風險，理由見第 3 節。
- 不做多人出題、角色權限或審核流程，web app 只有一個管理者帳號。
- 不做 vmdk 發出後的線上更新。有新題目時，作者重新匯出 vmdk，新人重新匯入。
- 不做 Kubernetes 支援，所有 instance 都跑在本機 Docker 上。
- 第一版不出 pwn 題，只確保 scenario 支援 TCP。
- 不做逐行合併，git 與資料庫衝突時以整題為單位二選一。

### 反目標

以下任何一項發生，即使功能都做出來也算失敗：

- 新人用低權限帳號就能讀到別人或自己 instance 的 flag 原始值，例如透過 docker.sock 或 web app 未登入的 API。
- 新增一題簡單的 php 題，仍然需要寫 Go、修改 scenario，或手動到 CTFd 填資料。
- VM 重開機後服務沒有自動回來，或要手動執行指令才能用。
- 在公司 OA 網路內安裝或 build 時，需要連到未開放 proxy 的外部網站。

## 3. 限制與前提

**執行環境**
- Ubuntu 26.04 Desktop，跑在公司 OA 網路的 VMware 上。新人需要桌面環境，才能使用瀏覽器與 Burp Suite。
- 每位新人一台 VM，服務與題目都在這台 VM 上，connection_info 的主機名稱用 `localhost`。
- CTFd 採用個人模式（user mode），新人各自註冊，instance 以使用者為單位，不使用隊伍。（實作者的判斷）
- 公司不允許有漏洞的主機暴露在網路上，所以 CTFd 與所有題目 instance 只綁在 `127.0.0.1`，從 OA 網路連不到。（實作者的判斷）

**網路**
- 公司 OA 有 Ubuntu apt、Docker Hub、git、pip、npm、apk、Go module 的 proxy，也能透過 proxy 下載 Burp Suite，但沒有 PECL 與 GitHub releases 的 proxy。
- 公司內禁止 git push 到外部。公司內的 git 只能 pull，在公司內修改的題目以備份壓縮檔保存。
- OA 網路上沒有 LLM 服務。

**帳號**
- `aps`：高權限帳號，在 `docker` 群組內，擁有並執行所有服務。
- `ops`：低權限帳號，給新人登入，不在 `docker` 群組，沒有 sudo。

**威脅模型**
- 動態 flag 防止的是新人之間互抄答案。
- 主要的防作弊機制在流程上，新人試用期要交每一題的 writeup，作者會抽問。
- 即使 vmdk 被拆開，新人拿到的是 image 與原始碼，不是解法。

**上游元件**（以 2026-11 查到的版本為準，實作時再確認）
- CTFd 3.8.8，ctfd-chall-manager plugin（文件標示測試到 chall-manager v0.6.6）。
- chall-manager v0.6.6 或之後的版本，搭配 chall-manager-janitor。
- scenario 是 Go 寫的 Pulumi 程式，以 oras 打包成 OCI artifact 推到 registry。
- ctfd-chall-manager repo 的 `hack/docker-scenario/` 是現成的 Docker scenario 範例，使用 `pulumi-docker` v4，從 `additional` 讀取 `image`、`port`、`hostname` 等參數，但沒有輸出 flag。
- `additional` 是 string 對 string 的 map。

**技術選擇**（作者指定）
- 前端用 Next.js，以 BFF 模式運作。
- 後端用 Python FastAPI，資料庫用 PostgreSQL。

## 4. 考慮過的做法

三種做法都共用同樣的基礎：兩個通用 scenario、VM 內的 registry，以及由 web app 呼叫 CTFd API 建立 `dynamic_iac` 題目。差別在於題目資料以哪一份為準。

**A. 以 web app 的資料庫為準**
題目資訊存在 PostgreSQL，題目檔案存在 volume，發佈時由 web app 負責 build、推送與同步 CTFd。好處是最符合作者原本的想像，出題全部在網頁上完成。缺點是本身沒有版本歷史，題目只存在出題 VM 裡。

**B. 以 git repo 為準，每題一個資料夾**
web app 是這些檔案的編輯器。好處是有版本歷史，在公司外也能出題。缺點是 web app 要處理檔案與 git 的同步，複雜很多。

**C. 不做 web app，只用 CLI 搭配範本**
不符合作者想在網頁上出題的需求，因此排除。

**作者的選擇是 A 為主，並納入 B 的 git 能力。** 作者在公司外可能用編輯器直接改題目並 push 到 GitHub，在公司內再透過 git proxy 拉進來。因此資料庫是唯一的正本，git repo 與備份壓縮檔都用同一種題目資料夾格式，作為匯入與匯出的管道（第 8 節）。

## 5. 系統架構

```
Ubuntu 26.04 VM
├─ ops（新人）──瀏覽器──> CTFd 127.0.0.1:8000 ──> 題目 instance 127.0.0.1:<隨機 port>
│                    └──> Burp Suite Community
└─ aps（docker 群組）
   └─ docker compose 專案 challsmith（restart: unless-stopped）
      ├─ ctfd               CTFd 3.8.8 + ctfd-chall-manager plugin，127.0.0.1:8000
      ├─ ctfd-db / ctfd-redis  CTFd 的資料庫與快取
      ├─ ctfd-setup         一次性，依設定檔建立 CTFd 管理者與 plugin 設定
      ├─ chall-manager      掛載 /var/run/docker.sock，只在內部網路
      ├─ chall-manager-janitor  定期回收逾時的 instance
      ├─ registry           registry:3，127.0.0.1:5000，存題目 image 與 scenario
      ├─ web                Next.js BFF，127.0.0.1:3000，作者使用
      ├─ api                FastAPI，只在內部網路，掛載 docker.sock 用來 build image
      └─ db                 PostgreSQL，challsmith 自己的資料
```

說明：

- 所有對外的 port 都只綁在 `127.0.0.1`，包括 CTFd、題目 instance、web app 與 registry，從 OA 網路連不到這台 VM 上的任何服務。新人也在同一台機器上，所以 web app 主要靠登入保護。
- chall-manager 與 api 都要掛載 docker.sock，這兩個 container 都屬於 `aps`，`ops` 碰不到。
- Docker daemon 預設允許 `localhost` 上的 registry 不使用 TLS，題目 image 與 scenario 都推到 `localhost:5000`。
- chall-manager 的狀態（instance 與 Pulumi state）放在 named volume，重開機後能接續管理還在跑的 instance。
- 開機自動啟動靠 Docker 的 systemd 服務與每個 compose 服務的 `restart: unless-stopped`。

## 6. Scenario

challsmith 只維護兩個通用 scenario，都以 ctfd-chall-manager 的 `hack/docker-scenario/` 為起點，用 Go 撰寫，在安裝時 build 並以 oras 推到本機 registry。出題時不需要碰 Go。

### 6.1 single：單一 container

用於 php、python、node 等單一 container 的 web 題，以及未來的 TCP 服務。

| `additional` 鍵 | 說明 | 預設 |
|---|---|---|
| `image` | 題目 image 的完整位置 | 必填 |
| `port` | container 內部的服務 port | `80` |
| `protocol` | `http` 或 `tcp`，決定 connection_info 的格式 | `http` |
| `flag` | flag 範本的內文，例如 `php_strcmp_array` | 必填 |
| `flag_prefix` | flag 外層的格式 | `CTF` |
| `memory` / `cpus` | 資源上限 | `256m` / `0.5` |

對外的 port 由 Docker 隨機分配，只綁在 `127.0.0.1`。connection_info 在 `http` 時為 `http://localhost:<port>`，在 `tcp` 時為 `nc localhost <port>`。

### 6.2 multi：多 container

用於 nginx + php-fpm + DB 這類題目。每個 instance 建立一個專屬的 docker network，所有 container 都接在上面，用服務名稱互相連線，只有入口服務對外發布 port。

`additional` 是 string 對 string 的 map，所以服務清單以 JSON 字串放在 `services` 鍵，例如：

```json
[
  {"name": "web", "image": "localhost:5000/challsmith/sqli-1-web:ab12", "port": 80, "entry": true},
  {"name": "php", "image": "localhost:5000/challsmith/sqli-1-php:ab12"},
  {"name": "db",  "image": "mariadb:11", "env": {"MARIADB_ROOT_PASSWORD": "x"}}
]
```

`flag`、`flag_prefix`、`protocol` 與資源上限的意義同 6.1，資源上限套用在每個 container。

### 6.3 動態 flag

1. 作者在 web app 設定 flag 範本，例如 `php_strcmp_array`，發佈時寫進 `additional.flag`。
2. scenario 以 `sdk.Variate(identity, flag)` 產生這個 instance 的 flag，再用 `flag_prefix` 包成 `CTF{...}`。
3. scenario 把 flag 以環境變數 `FLAG` 注入題目 container。多 container 時注入所有 container，由題目自己決定在哪裡使用，例如寫進 DB。
4. scenario 在回應中輸出這個 flag，交給 ctfd-chall-manager 驗證。

CTFd 端不建立靜態 flag。plugin 會把 CTFd 設定的 flag 與 instance 的 flag 一起接受，如果建立了靜態 flag，所有人都能用同一個 flag 過關，動態 flag 就失去意義。

範本的 entrypoint 負責在服務啟動前，把 `$FLAG` 放到題目需要的位置，例如寫成 `/flag.txt`。題目 image 裡不含 flag，同一個 image 可以重複使用。

identity 是 chall-manager 每開一個 instance 就用 crypto/rand 產生的隨機值（`pkg/identity/identity.go`），跟 CTFd 的使用者 ID 無關。因此即使所有新人的 VM 都從同一份 vmdk 複製，使用者 ID 都從 1 開始，每個 instance 的 flag 仍然不同，不需要額外的 VM secret。同一位新人刪掉 instance 再重開時也會拿到新的 flag，plugin 驗證的是當下這個 instance 的 flag。

## 7. 題目格式

資料庫、git repo 與備份壓縮檔都使用同一種資料夾格式：

```
challenges/
  php-strcmp/
    challenge.yml
    services/
      app/              ← 每個 service 一個資料夾，內含 Dockerfile 與題目檔案
        Dockerfile
        index.php
  sqli-1/
    challenge.yml
    services/
      web/ (nginx 設定與 Dockerfile)
      php/ (Dockerfile 與程式碼)
```

`challenge.yml` 範例：

```yaml
slug: php-strcmp
name: strcmp 的陷阱
category: Web
tags: [php, type-juggling]
description: |
  （Markdown）
value: 100
template: php
scenario: single          # single 或 multi
flag: php_strcmp_array
instance:
  timeout: 3600           # 秒，instance 存活時間
  mana: 1
services:
  - name: app
    port: 80
    entry: true
  # multi 題可以直接用官方 image，不需要資料夾
  # - name: db
  #   image: mariadb:11
  #   env: { MARIADB_ROOT_PASSWORD: x }
visible: true
```

這個格式是 challsmith 自己的定義，不對應任何上游工具。

## 8. web app 功能

### 8.1 登入

只有一個管理者帳號，帳密在安裝時設定。Next.js 以伺服器端 session 管理登入狀態，瀏覽器只跟 Next.js 溝通，FastAPI 不對外。

### 8.2 範本

範本是 repo 裡的資料夾，例如 `templates/<name>/`，內含 Dockerfile、entrypoint、範例程式碼與一份描述檔，說明預設的 scenario、port 與 service 組成。第一批範本：

| 範本 | scenario | 內容 |
|---|---|---|
| `php` | single | `php:<版本>-apache`，放 php 檔案即可 |
| `python-flask` | single | Python + Flask，`requirements.txt` 可指定套件版本 |
| `node-nextjs` | single | Node.js + Next.js，`package.json` 可指定套件版本 |
| `nginx-php-db` | multi | nginx、php-fpm（含常用 extension）、MariaDB |
| `tcp` | single | socat 把 TCP 連線接到一個程式，給 pwn 題預留 |

範本的 Dockerfile 可以使用 `RUN apk add`、`pip install`、`npm install`，透過公司的 proxy 安裝。需要 PECL extension 的 php，改用第 10 節預先包好的 image 當 base。

### 8.3 題目編輯

- 題目清單：顯示每題的狀態，例如草稿、已發佈、有未發佈的修改，以及 git 同步狀態。
- 從範本建立題目，複製範本檔案成為題目的初始檔案。
- 在網頁上編輯 `challenge.yml` 的各欄位與每個 service 的檔案，支援上傳單一檔案或 zip。
- 編輯 CTFd 題目資訊：標題、描述（Markdown）、分類、標籤、分數、instance timeout 與 mana。
- 設定 flag 範本。

### 8.4 發佈

按下「發佈」時，依序執行以下步驟，並在頁面上即時顯示 build log：

1. 依每個 service 的資料夾 build image，tag 為 `localhost:5000/challsmith/<slug>-<service>:<內容 hash>`。
2. 推送 image 到本機 registry。直接使用官方 image 的 service（例如 `mariadb:11`）也複製一份到本機 registry，並改用本機的位置，讓 vmdk 在完全離線時也能開 instance。（實作者的判斷）
3. 依 `scenario` 組出 `additional`。
4. 透過 CTFd API 建立或更新 `dynamic_iac` 題目，並設定標籤與可見性。web app 記錄 CTFd 題目 ID，之後的發佈都更新同一題。

任何一步失敗時停止，CTFd 上的題目維持上一次成功發佈的狀態。

題目的測試由作者用 CTFd 的管理者帳號開 instance 來進行，web app 不另外做試跑功能。

### 8.5 git 與備份

- 設定一個 git remote 網址與憑證，以及 repo 內的題目目錄（預設 `challenges/`）。
- 匯出到 git 時，把資料庫中的題目寫成第 7 節的格式，commit 之後可以選擇 push。在公司內 push 會失敗，web app 顯示錯誤並建議改用備份壓縮檔。
- 從 git 匯入時，先 pull，再逐題比對並列出狀態，由作者確認後才寫入：
  - 新題目：加入。
  - 沒有變動：跳過。
  - 只有 git 改過：採用 git 的版本。
  - 只有資料庫改過：保留資料庫的版本。
  - 兩邊都改過：標示為衝突，由作者逐題選擇保留資料庫版或採用 git 版。
- 每題記錄上次匯入或匯出時的內容 hash，與資料庫目前的 hash、git 目前的 hash 三方比較，藉此判斷是哪一邊改過。
- 備份壓縮檔是一個 `.tar.gz`，內容同第 7 節的格式，可以下載與上傳，上傳時走與 git 匯入相同的比對流程。

匯入只更新資料庫，不會自動發佈到 CTFd。

### 8.6 發佈前清理

在匯出 vmdk 前執行，web app 提供按鈕，也提供命令列指令。執行前要求再次確認：

1. 關閉所有還在跑的 instance（透過 chall-manager API），並移除殘留的題目 container 與 network。
2. 刪除 CTFd 中所有非管理者的使用者，以及其解題與提交紀錄。
3. 清除 web app 的登入 session。
清理不會刪除題目、image 或 web app 的資料。

## 9. 安裝與發放

### 9.1 安裝

repo 提供一個安裝指令，在全新的 Ubuntu 26.04 Desktop 上以 sudo 執行：

1. 透過 apt proxy 安裝 Docker Engine 與 compose plugin，透過 proxy 下載並安裝 Burp Suite Community。Go 與 oras 不裝在 VM 上，scenario 改用 `golang` 與 oras 的 container image 來 build 和推送，chall-manager 使用第 10 節預先包好 Pulumi docker provider plugin 的 image，全部透過 Docker Hub proxy 取得。（實作者的判斷）
2. 設定 Docker 使用公司的 Docker Hub proxy，並把 pip、npm、apk、Go 的 proxy 設定以 build args 傳給題目 build。
3. 建立 `aps`（加入 `docker` 群組）與 `ops`（無 sudo、不在 `docker` 群組）。
4. 把專案放到 `aps` 擁有的目錄，例如 `/opt/challsmith`，權限設為 `ops` 無法讀取，避免直接看到設定檔裡的密碼。
5. build 兩個 scenario 並以 oras 推到本機 registry。
6. 啟動 compose 專案，由 ctfd-setup 建立 CTFd 管理者與 plugin 設定。

公司的各種 proxy 位址與 web app、CTFd 的管理者帳密，集中在一份設定檔，安裝前填好。

### 9.2 發放流程

1. 作者在出題 VM 上出題並發佈到本機 CTFd。
2. 執行發佈前清理。
3. 關機，從 VMware 匯出 vmdk，發給新人。
4. 有新題目時重複以上步驟，新人重新匯入，之前的解題紀錄不保留。

## 10. 另一個 repo：base images

公司內沒有 PECL proxy，需要 PECL extension 的 php image 要在公司外先包好。另開一個 GitHub repo，用 GitHub Actions build 並推到作者的 Docker Hub 帳號，公司內再透過 Docker Hub proxy 拉取。

- 第一版只包 php-fpm 搭配常用的 PECL extension，涵蓋幾個 php 版本。
- extension 與版本清單放在設定檔，新增時只改設定檔。
- 不需要 PECL 的 image 一律直接用官方 image，在範本的 Dockerfile 裡安裝。
- 同一個 repo 也包一版預先裝好 Pulumi docker provider plugin 的 chall-manager image，以及 oras 的 image，因為公司內連不到 GitHub releases 與 Pulumi 的 plugin 下載站。
- 這個 repo 列入第一版的範圍。Docker Hub 帳號名稱與 php 版本清單放在設定檔，第一版涵蓋 php 7.4、8.1、8.3，搭配 redis、mongodb 等常用 extension。（實作者的判斷）

## 11. 留給實作者的部分

- web app 的畫面設計與程式碼編輯器的選擇。
- FastAPI 與 PostgreSQL 的資料表設計。
- build 的執行方式，例如在 api container 內直接呼叫 Docker API 或 `docker build`，以及 build log 的串流方式。
- 內容 hash 的計算方式，需要排除換行符號與檔案權限差異造成的誤判。
- CTFd 的資料庫選擇（MariaDB 或 PostgreSQL）。
- 各元件確切的版本，以實作當時的最新穩定版為準，並在 compose 檔中固定版本。
- scenario 的 Go 程式細節，包括多 container 時 network 與 container 的命名、資源上限的套用方式。

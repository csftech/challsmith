# web app 介面改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 出題 web app 換上可切換四種主題的新介面、支援列表與資訊卡切換、題目順序與 CTFd 一致並可拖拉同步，以及繁中與英文切換。

**Architecture:** 後端在 `challenges` 表加 `position`，排序規則集中在新的 `order_service` 純函式，`GET /challenges` 依 CTFd 校正順序，`PUT /challenges/order` 寫入資料庫與 CTFd，錯誤回應加上固定的 `code`。前端以 next-intl（cookie、不帶網址前綴）處理語言，以 `<html data-theme>` 加 CSS 變數處理主題，共用側欄版面，題目頁用 `@dnd-kit` 做兩層排序。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、PostgreSQL 19；Next.js 16.4.6、React 19.3.1、TypeScript 7、next-intl 4.15.3、@dnd-kit。

**Spec:** `docs/superpowers/specs/2026-11-23-webapp-redesign-design.md`（mockup 在 `docs/superpowers/specs/assets/2026-11-23-webapp-redesign/`）

## Global Constraints

- 分支 `feat/webapp-redesign`，每個 task 一個以上 commit，結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`，LF 行尾，不 push。
- 套件版本固定到確切數字：`next-intl` 4.15.3、`@dnd-kit/core` 6.3.1、`@dnd-kit/sortable` 10.0.0、`@dnd-kit/utilities` 3.2.2、`@fontsource/ibm-plex-sans` 5.3.0、`@fontsource/ibm-plex-mono` 5.3.0、`@fontsource/inter` 5.3.0、`@fontsource/noto-sans-tc` 5.3.1。不引入 Tailwind 或元件庫。
- 後端分層：api/routes → services → repositories／clients；只有 repositories 碰資料庫，services 負責 commit，只有 clients 呼叫 CTFd 或執行子程序；跨層用模組匯入，名稱帶層級後綴（`order_service`、`challenge_repository`、`ctfd_client`），不用 `as`。
- 主題 id：`signal`（預設）、`zinc`、`midnight`、`canvas`；cookie `theme`。語言：`zh-TW`（預設）、`en`；cookie `NEXT_LOCALE`。
- 主題的顏色、框線、圓角、字體數值以 mockup `visual-style-v2.html` 的 CSS 為準，卡片版面以 `card-view.html` 第 1 種為準。
- 不翻譯 docker build 與工具輸出、CLI 輸出；後端 `detail` 維持英文。
- README 與 README_ZH-TW 內容同步；中文以 `py "C:/Users/csf/.claude/skills/zh-tw-writing/scripts/check_zh.py" README_ZH-TW.md` 檢查。
- 不讀取任何 `.env` 或 `challsmith.env`。
- 測試在 dev VM 上執行：wrapper `sh C:/Users/csf/AppData/Local/Temp/claude/ed852000a11ccdaa/61ae99bd-d86b-46ed-a2a2-6d396a278f29/scratchpad/vm.sh '<cmd>'`；同步程式碼用 `cd D:/projects/challsmith && tar --exclude=./.env --exclude=./challsmith.env --exclude=./.git --exclude=./.superpowers --exclude=./frontend/node_modules --exclude=./frontend/.next --exclude=./infra/scenarios/bin -cf - . | sh <vm.sh> 'tar -xf - -C ~/challsmith'`。後端：`cd ~/challsmith && sh backend/tests/run.sh`。前端：`cd ~/challsmith && docker build frontend`（Dockerfile 會跑 typecheck、`npm test`、build）。整體：`sudo ./install.sh`，端對端 `sudo -u aps -H /opt/challsmith/tests/e2e/run.sh`。

## Review Focus

1. CTFd 裡有 web app 不認得的題目（直接在 CTFd 後台建的）時，`GET /challenges` 忽略它們，不出錯也不顯示。→ Task 3 測試 `test_list_ignores_foreign_ctfd_challenges`。
2. 頁面開著時另一個分頁新增了題目，拖拉存檔得到 400 `order_mismatch`，前端要提示並重新載入清單，不能卡住。→ Task 5 的 `onDragEnd` 錯誤處理與 Task 7 的手動驗證。
3. 分類是空字串的題目，分組與驗證都要當成一個正常的分類。→ Task 2 測試 `test_reconcile_empty_category_is_a_group`。
4. cookie 的 `theme` 或 `NEXT_LOCALE` 值不合法（舊值、手改）時，退回 `signal` 與 `zh-TW`，不出錯。→ Task 4 測試 `pickTheme`／`pickLocale`。
5. 很長的題目名稱或中文名稱在卡片與列表中不撐破版面，以省略號截斷並保留完整名稱於 `title`。→ Task 5 CSS 與 Task 7 手動驗證。

---

### Task 1: 後端錯誤代碼

**Files:**
- Modify: `backend/app/services/errors.py`、`backend/app/main.py`、`backend/app/api/deps.py`（401）、所有拋出 `DomainError` 子類別的地方（約 40 處，`grep -rn "raise \(BadRequest\|Conflict\|NotFound\|BadGateway\|Unauthorized\|TooLarge\|Unprocessable\)" backend/app`）
- Test: `backend/tests/test_errors.py`（新增）

**Interfaces:**
- Produces: `DomainError(detail="error", code: str | None = None)`，屬性 `code`；每個子類別有預設 `code`（`BadRequest`→`bad_request`、`Unauthorized`→`unauthorized`、`NotFound`→`not_found`、`Conflict`→`conflict`、`TooLarge`→`too_large`、`Unprocessable`→`unprocessable`，`BadGateway` 若存在→`bad_gateway`）。錯誤回應 `{"detail": ..., "code": ...}`。
- 固定代碼（spec 6.3，前端會翻譯）：`unauthorized`、`not_found`、`slug_exists`、`slug_reserved`、`publish_running`、`cleanup_running`、`order_mismatch`、`order_category_split`、`ctfd_order_failed`、`ctfd_unreachable`。其他拋出點各自取一個 snake_case 代碼，描述錯誤本身（例如 `unknown_template`、`slug_immutable`、`orphan_files`、`confirm_mismatch`）。把完整清單寫進 `backend/app/services/errors.py` 頂端的註解，Task 4 依這份清單寫翻譯。

- [ ] **Step 1: 寫失敗的測試** `test_errors.py`：
  - `test_conflict_has_code`：POST `/challenges` 建立同一個 slug 兩次，第二次 `r.status_code == 409` 且 `r.json() == {"detail": "slug already exists", "code": "slug_exists"}`。
  - `test_not_found_has_code`：GET `/challenges/nope` → 404，`code == "not_found"`。
  - `test_unauthorized_has_code`：不帶 session GET `/challenges` → 401，`code == "unauthorized"`。
  - `test_default_code`：`errors.BadRequest("x").code == "bad_request"`。
- [ ] **Step 2: 在 VM 跑 `sh backend/tests/run.sh`，確認上述測試失敗。**
- [ ] **Step 3: 實作**：`DomainError.__init__` 收 `code`，`main.domain_error` 回傳 `code`；`deps.require_session` 的 401 回應帶 `code: "unauthorized"`（可改成拋 `Unauthorized` 讓 handler 處理，保留 `WWW-Authenticate`）；逐一替拋出點加上代碼。
- [ ] **Step 4: 跑後端測試，全部通過。**
- [ ] **Step 5: Commit** `feat(api): stable error codes in error responses`

### Task 2: 排序資料與排序規則

**Files:**
- Create: `backend/alembic/versions/0002_challenge_position.py`、`backend/app/services/order_service.py`
- Modify: `backend/app/models/challenge.py`、`backend/app/repositories/challenge_repository.py`、`backend/app/services/challenge_service.py`（`save_challenge` 新建時給位置）、`backend/app/services/sync_service.py`（匯入新建時給位置，透過同一個 repository 函式）、`backend/app/schemas/challenge_schema.py`（`RESERVED_SLUGS = {"order"}`）
- Test: `backend/tests/test_order.py`（新增）

**Interfaces:**
- Produces（repository）：`challenge_repository.list_all(db)` 改為依 `position, id` 排序；`next_position(db) -> int`（最大值加 1，空表為 1）；`set_positions(db, order: list[str]) -> None`（依序設為 1..N）；`add(...)` 新建時 `position=next_position(db)`。
- Produces（service，純函式，不碰資料庫與 CTFd）：
  - `Row = NamedTuple(slug: str, category: str, ctfd_id: int | None)`，輸入清單已依資料庫 `position` 排好。
  - `CtfdPos = NamedTuple(position: int, value: int)`。
  - `reconcile(rows: list[Row], ctfd: dict[int, CtfdPos]) -> list[str]`：spec 6.2 GET 第 2 到 4 步。已發佈＝`ctfd_id in ctfd`。已發佈題目依 `(position == 0, position, value, ctfd_id)` 排序後，依序填回它們原本佔的索引；接著依分類第一次出現的順序穩定分組。
  - `validate_order(order: list[str], rows: list[Row]) -> None`：缺、多、重複 → `BadRequest(..., code="order_mismatch")`；同分類不連續 → `BadRequest(..., code="order_category_split")`。
  - `move_to_category_end(rows: list[Row], slug: str, new_category: str) -> list[str]`：spec 6.2「在編輯器修改分類」。
- migration `0002`：加 `position INTEGER`，依 `created_at, id` 填 1..N，再設 `NOT NULL`。
- `challenge_schema.NewChallenge` 與匯入的 slug 驗證拒絕 `RESERVED_SLUGS`（`slug_reserved`）。

- [ ] **Step 1: 寫失敗的測試** `test_order.py`（`R = order_service.Row`、`P = order_service.CtfdPos`）：
  - `test_reconcile_follows_ctfd`：rows `[R("a","web",1), R("b","web",2), R("d","web",None)]`，ctfd `{1: P(2,100), 2: P(1,100)}` → `["b","a","d"]`。
  - `test_reconcile_keeps_draft_slots`：rows `[R("a","web",1), R("d","web",None), R("b","web",2)]`，ctfd `{1: P(2,0), 2: P(1,0)}` → `["b","d","a"]`。
  - `test_reconcile_zero_positions_by_value`：ctfd 全部 position 0、value 300/100/200 → 依 value 由小到大；同 value 依 ctfd_id。
  - `test_reconcile_regroups_split_category`：rows `[R("a","web",1), R("x","pwn",2), R("b","web",3)]`，ctfd `{1:P(1,0),2:P(2,0),3:P(3,0)}` → `["a","b","x"]`。
  - `test_reconcile_missing_ctfd_id_is_draft`：`ctfd_id=9` 不在 ctfd 中 → 位置不動。
  - `test_reconcile_empty_category_is_a_group`：分類 `""` 的題目和其他分類一樣分組。
  - `test_validate_order`：正確順序不拋錯；缺一題、多一題、重複各拋 `code == "order_mismatch"`；`["a","x","b"]`（web/pwn/web）拋 `code == "order_category_split"`。
  - `test_move_to_category_end`：移到既有分類最後；新分類 → 整份清單最後。
  - `test_new_challenge_goes_last`：連續建立兩題，`list_all` 順序與建立順序相同，position 為 1、2。
  - `test_order_slug_reserved`：POST `/challenges` slug `order` → 400，`code == "slug_reserved"`。
- [ ] **Step 2: 在 VM 跑後端測試，確認失敗。**
- [ ] **Step 3: 實作 migration、model、repository、`order_service`、保留 slug。**
- [ ] **Step 4: 跑後端測試，全部通過（含 alembic upgrade）。**
- [ ] **Step 5: Commit** `feat(api): challenge position and ordering rules`

### Task 3: 排序 API 與發佈

**Files:**
- Modify: `backend/app/clients/ctfd_client.py`、`backend/app/services/challenge_service.py`、`backend/app/services/publish_service.py`、`backend/app/api/routes/challenges.py`、`frontend/app/page.tsx`（只改讀取 `GET /challenges` 的那一行，配合新的回應形狀；完整改版在 Task 5）
- Test: `backend/tests/test_order_api.py`（新增）、`backend/tests/test_publish.py`

**Interfaces:**
- Consumes: Task 2 的 `order_service.reconcile/validate_order/move_to_category_end`、`challenge_repository.set_positions`。
- Produces（client）：`CtfdClient.list_positions() -> dict[int, tuple[int, int]]`（`GET /challenges?view=admin`，id → (position, value)，含隱藏題目）；`CtfdClient.set_position(cid: int, position: int) -> None`（`PATCH /challenges/{cid}`，只送 `{"position": position}`）。
- Produces（service）：
  - `challenge_service.list_summaries(db, ctfd) -> dict`：回傳 `{"items": [...], "ctfd_ok": bool}`。每筆 item 在現有欄位外加 `position`、`ctfd_id`、`ctfd_missing`、`template`（`meta.template`，可能為 null，前端此時顯示 `scenario`）、`services`（服務數）、`value`。CTFd 呼叫失敗（`CtfdError`、連線錯誤）→ 用資料庫順序、`ctfd_ok=False`。校正結果與資料庫不同時 `set_positions` 並 commit。
  - `challenge_service.save_order(db, ctfd, order: list[str]) -> None`：spec 6.2 PUT 第 1 到 5 步。CTFd 失敗 → rollback，拋 `BadGateway(detail, code="ctfd_order_failed")`，`detail` 列出失敗的 slug。
  - `challenge_service.push_positions(db, ctfd) -> list[str]`：把所有已發佈題目的 position 送到 CTFd，回傳失敗的 slug（不拋錯）。
  - `update_meta`：分類改變時呼叫 `move_to_category_end` 並 `set_positions`。
- Produces（route）：`GET /challenges` 加 `ctfd = Depends(get_ctfd_client)`；`PUT /challenges/order`，body `{"order": [slug, ...]}`，回 `{"ok": true}`，註冊在 `PUT /challenges/{slug}` 之前。
- 發佈：`ctfd_payload` 加 `position`，值在呼叫 `create_challenge`／`update_challenge` 前從資料庫重新讀取；發佈成功後呼叫 `push_positions`，失敗只 `log` 警告。

- [ ] **Step 1: 寫失敗的測試**（沿用 `test_cleanup.py` 的 `FakeCtfd` 寫法，新增有 `list_positions`、`set_position`、可設定失敗 id 的替身）：
  - `test_list_reorders_by_ctfd`：資料庫 a、b 都已發佈，CTFd 給 b 較小 position → `items` 的 slug 為 `["b","a"]`，且資料庫 position 已更新。
  - `test_list_ignores_foreign_ctfd_challenges`：CTFd 多一題 id 99 → 不出現在 items，不出錯。
  - `test_list_ctfd_down`：替身拋 `CtfdError` → 200，`ctfd_ok is False`，順序為資料庫順序。
  - `test_list_marks_missing`：`ctfd_id` 不在 CTFd → `ctfd_missing is True`。
  - `test_save_order_updates_db_and_ctfd`：PUT `{"order": ["b","a"]}` → 200；資料庫 position b=1、a=2；替身收到 `set_position` 對應的 (id, position)。
  - `test_save_order_skips_missing`：`ctfd_missing` 的題目不會收到 `set_position`。
  - `test_save_order_ctfd_failure_rolls_back`：替身對其中一題失敗 → 502，`code == "ctfd_order_failed"`，資料庫 position 不變。
  - `test_save_order_validation`：缺題 → 400 `order_mismatch`；分類不連續 → 400 `order_category_split`。
  - `test_category_change_moves_to_end`：PUT `/challenges/{slug}` 改分類 → `list_all` 中該題在新分類最後。
  - `test_publish_sends_current_position`（`test_publish.py`）：發佈時 `create_challenge` payload 的 `position` 等於資料庫目前的值；在發佈前改 position，payload 用新值。
- [ ] **Step 2: 跑後端測試，確認失敗。**
- [ ] **Step 3: 實作 client、service、route、發佈；`frontend/app/page.tsx` 改讀 `.items`。**
- [ ] **Step 4: 跑後端測試，全部通過。**
- [ ] **Step 5: Commit** `feat(api): order challenges like CTFd and save drag order`

### Task 4: 前端基礎：語言、主題、版面

**Files:**
- Modify: `frontend/package.json`、`frontend/package-lock.json`、`frontend/next.config.ts`（`createNextIntlPlugin`）、`frontend/app/layout.tsx`、`frontend/app/globals.css`、`frontend/lib/api.ts`、`frontend/app/login/page.tsx`
- Create: `frontend/i18n/request.ts`、`frontend/messages/zh-TW.json`、`frontend/messages/en.json`、`frontend/global.d.ts`（next-intl `AppConfig` 型別擴充）、`frontend/lib/prefs.ts`、`frontend/lib/prefs.test.ts`、`frontend/lib/messages.test.ts`、`frontend/app/shell.tsx`（側欄＋頂列）、`frontend/app/switchers.tsx`（語言與主題切換）、`frontend/app/themes.css`
- Delete: `frontend/app/nav.tsx`（由 `shell.tsx` 取代）

**Interfaces:**
- Produces（`lib/prefs.ts`，純函式）：`THEMES = ["signal","zinc","midnight","canvas"] as const`、`type Theme`、`pickTheme(v: string | undefined): Theme`（不合法 → `"signal"`）；`LOCALES = ["zh-TW","en"] as const`、`type Locale`、`pickLocale(v: string | undefined): Locale`（不合法 → `"zh-TW"`）。
- Produces（`lib/api.ts`）：`ApiError` 多一個 `code?: string`；`apiRaw` 從回應讀 `code`。新增 `errorText(e: unknown, t: (key: string, values?: Record<string, string>) => string): string`：有 `code` 且 `errors.<code>` 存在時回傳翻譯，否則回傳原本的訊息。
- Produces（`app/shell.tsx`）：`<Shell title: string, search?: ReactNode>{children}</Shell>`，所有已登入頁面用它包住內容。側欄項目：題目 `/`、新增題目 `/new`、Git 同步 `/sync`、發佈前清理 `/cleanup`、底部帳號與登出。寬度小於 900px 時側欄預設收合，頂列的按鈕可展開。
- `layout.tsx`：server component，讀 cookie `theme` 與 `NEXT_LOCALE`（經 `pickTheme`／`pickLocale`），輸出 `<html lang={locale} data-theme={theme}>`，用 `NextIntlClientProvider` 包住 children，匯入四套 `@fontsource` 字體 CSS（只匯入用到的字重：400、500、600、700）。
- `i18n/request.ts`：`getRequestConfig` 讀 cookie 決定語言並載入 `messages/<locale>.json`。
- 切換：`switchers.tsx` 寫 cookie（`path=/; max-age=31536000; samesite=lax`）後 `router.refresh()`。
- `themes.css`：每個主題一段 `[data-theme="..."] { --... }`，變數至少包含 spec 5.1 列出的項目，數值取自 mockup。`globals.css` 只用變數，不寫死顏色。
- 翻譯檔：依頁面分區（`common`、`nav`、`login`、`list`、`new`、`editor`、`publish`、`sync`、`cleanup`、`errors`、`themes`）。這個 task 寫好 `common`、`nav`、`login`、`themes` 與 Task 1 的全部 `errors.<code>`；其他分區由後續 task 補上。

- [ ] **Step 1: 寫失敗的測試**：
  - `lib/prefs.test.ts`：`pickTheme(undefined) === "signal"`、`pickTheme("zinc") === "zinc"`、`pickTheme("purple") === "signal"`；`pickLocale("en") === "en"`、`pickLocale("fr") === "zh-TW"`、`pickLocale(undefined) === "zh-TW"`。
  - `lib/messages.test.ts`：遞迴取出兩個 JSON 檔的所有 key 路徑，兩者集合相等；任何值都不是空字串。
- [ ] **Step 2: 在 VM 跑 `docker build frontend`，確認測試失敗。**
- [ ] **Step 3: 安裝套件（確切版本）、實作上述檔案，登入頁改用新版面（無側欄、置中、有切換按鈕）。其他頁面暫時把 `<Nav />` 換成 `<Shell>`，字串維持現狀，後續 task 再翻譯。**
- [ ] **Step 4: `docker build frontend` 通過（typecheck、test、build）。**
- [ ] **Step 5: Commit** `feat(web): i18n, themes and app shell`

### Task 5: 題目頁

**Files:**
- Modify: `frontend/app/page.tsx`、`frontend/lib/api.ts`（`Summary` 型別與 `ListResponse`）、`frontend/messages/*.json`（`list` 分區）、`frontend/app/globals.css`
- Create: `frontend/lib/order.ts`、`frontend/lib/order.test.ts`、`frontend/app/challenge-list.tsx`（列表模式）、`frontend/app/challenge-cards.tsx`（資訊卡模式）、`frontend/app/sortable.tsx`（dnd-kit 共用的拖拉包裝）

**Interfaces:**
- Consumes: Task 3 的 `GET /challenges` → `{items, ctfd_ok}`、`PUT /challenges/order` body `{order}`；Task 4 的 `Shell`、`errorText`。
- Produces（`lib/order.ts`，純函式）：
  - `type Group = { category: string; items: Summary[] }`
  - `groupByCategory(items: Summary[]): Group[]`：依第一次出現的順序分組，保持組內順序。
  - `flatten(groups: Group[]): string[]`：攤平成 slug 陣列。
  - `moveItem(groups: Group[], category: string, from: number, to: number): Group[]`
  - `moveGroup(groups: Group[], from: number, to: number): Group[]`
  - `matches(item: Summary, q: string, category: string | null, status: string | null): boolean`：搜尋比對名稱與 slug（不分大小寫）。
- 頁面行為：spec 5.3。檢視模式存在 localStorage `listView`（`list`／`cards`，讀寫都包 try/catch）。有搜尋或篩選條件、或 `ctfd_ok` 為 false 時停用拖拉並顯示提示。放下後先樂觀更新畫面，呼叫 `PUT /challenges/order`；任何錯誤（含 400 `order_mismatch`）都用 `errorText` 顯示並重新載入清單。刪除對話框要求輸入 slug，呼叫現有的刪除 API。名稱過長時以 CSS 省略號截斷，完整名稱放在 `title`。`ctfd_missing` 的題目顯示「CTFd 上找不到」標籤。題目頁的搜尋框支援快捷鍵 `/`（焦點不在輸入框時）。
- dnd-kit：外層 `SortableContext` 排分類，每組內層 `SortableContext` 排題目，啟用 `KeyboardSensor`（`sortableKeyboardCoordinates`）與 `PointerSensor`；題目不可跨組放下。

- [ ] **Step 1: 寫失敗的測試** `lib/order.test.ts`：
  - `groupByCategory` 對 `[web a, pwn x, web b]` → 兩組，web 在前且含 a、b。
  - `flatten(moveItem(groups, "web", 0, 1))` 把 a、b 對調。
  - `flatten(moveGroup(groups, 0, 1))` 讓 pwn 組排到前面。
  - 分類 `""` 自成一組。
  - `matches` 對名稱子字串、slug、分類篩選、狀態篩選各一個成立與不成立的案例。
- [ ] **Step 2: `docker build frontend`，確認失敗。**
- [ ] **Step 3: 實作頁面、兩種檢視、拖拉、搜尋與篩選、刪除對話框，以及 `list` 分區的翻譯。**
- [ ] **Step 4: `docker build frontend` 通過。**
- [ ] **Step 5: Commit** `feat(web): challenge list with cards, filters and drag ordering`

### Task 6: 其他頁面改版與翻譯

**Files:**
- Modify: `frontend/app/new/page.tsx`、`frontend/app/c/[slug]/page.tsx`、`frontend/app/c/[slug]/publish/page.tsx`、`frontend/app/sync/page.tsx`、`frontend/app/cleanup/page.tsx`、`frontend/messages/*.json`（`new`、`editor`、`publish`、`sync`、`cleanup` 分區）、`frontend/app/globals.css`

**Interfaces:**
- Consumes: Task 4 的 `Shell`、`errorText`、主題變數。
- 功能與流程不變（spec 5.4），只換版面、元件樣式與字串。所有 inline style 移到 CSS（必要的動態值例外）。編輯器的 CodeMirror 在 `midnight` 主題用深色配色，其他用淺色：從 `document.documentElement.dataset.theme` 讀取。發佈記錄的建置輸出不翻譯。相對時間與日期用 next-intl 的 `useFormatter`。

- [ ] **Step 1: 確認各頁面沒有殘留的硬寫中文字串**：`grep -rnP "[\x{4e00}-\x{9fff}]" frontend/app frontend/lib --include=*.tsx --include=*.ts` 只剩測試檔（此時應有多處命中，作為基準）。
- [ ] **Step 2: 逐頁改寫，補上翻譯。**
- [ ] **Step 3: 再跑 Step 1 的 grep，`app/` 與 `lib/` 的非測試檔沒有命中；`docker build frontend` 通過。**
- [ ] **Step 4: Commit** `feat(web): restyle and translate remaining pages`

### Task 7: 端對端測試、文件與整體驗證

**Files:**
- Modify: `tests/e2e/test_webapp.py`、`README.md`、`README_ZH-TW.md`
- Test: `tests/e2e/test_webapp.py`

**Interfaces:**
- Consumes: Task 3 的 API，e2e 既有的 `web`、`admin`、`new_challenge`、`publish` 等 fixture（`tests/e2e/conftest.py`）。

- [ ] **Step 1: 寫端對端測試** `test_reorder_syncs_to_ctfd`：建立並發佈兩題（同分類），`PUT /api/challenges/order` 交換兩題順序後：CTFd `GET /api/v1/challenges?view=admin` 中兩題的 `position` 與 web app 一致；CTFd 前台清單 `GET /api/v1/challenges`（一般使用者）中兩題的先後也交換了。再建立一題不同分類的題目並發佈，把該分類拖到最前面，確認 CTFd 前台清單中該分類的題目最先出現。結束時刪除測試題目。
- [ ] **Step 2: 在 VM `sudo ./install.sh` 後跑端對端測試，全部通過（現有的 9 + 1 加上新測試）。**
- [ ] **Step 3: README（兩種語言）更新 web app 段落：主題切換、語言切換、列表與卡片、拖拉排序會同步到 CTFd 的 `position`、`order` 不能當 slug；中文跑 `check_zh.py`。**
- [ ] **Step 4: 手動驗證並截圖**（Playwright 或瀏覽器皆可，截圖放 scratchpad，不 commit）：四種主題 × 兩種語言的題目頁（列表與卡片）、編輯器、清理頁；滑鼠與鍵盤各拖拉一次；製造 `order_mismatch`（開兩個分頁，一邊新增題目，另一邊拖拉）確認有提示並重新載入；長名稱不撐破版面；切換語言與主題時沒有閃爍。
- [ ] **Step 5: Commit** `test(e2e): drag order syncs to CTFd; docs: web app redesign`

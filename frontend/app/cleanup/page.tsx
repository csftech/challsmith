"use client";

import { useEffect, useState } from "react";

import { Shell } from "@/app/shell";
import { api, jsonInit } from "@/lib/api";

type Result = {
  instances: number;
  containers: number;
  networks: number;
  users: number;
  sessions: number;
  images: number;
  registry_tags: number;
  reclaimed_bytes: number;
};
type Plan = {
  images: { ref: string; id: string; size: number }[];
  registry: { repo: string; tag: string; digest: string }[];
  kept_images: Record<string, string[]>;
  kept_registry: Record<string, string[]>;
  reclaimable_bytes: number;
};

// reasons come from the api (image_cleanup_service) in English
const REASON: Record<string, string> = {
  "in use by a container": "container 使用中",
  "CTFd challenge": "CTFd 題目使用中",
  scenario: "scenario",
  "keep list": "保留清單 CLEANUP_KEEP_IMAGES",
  "template base image": "範本的基底 image",
  "outside challsmith/": "不在 challsmith/ 底下",
  "same digest as a kept tag": "與保留的 tag 同一個 digest",
};

const mb = (n: number) => `${(n / 1e6).toFixed(0)} MB`;

function Kept({ title, kept }: { title: string; kept: Record<string, string[]> }) {
  const total = Object.values(kept).reduce((n, refs) => n + refs.length, 0);
  return (
    <details>
      <summary>
        {title}：{total} 個
      </summary>
      <ul>
        {Object.entries(kept).map(([why, refs]) => (
          <li key={why}>
            {REASON[why] ?? why}（{refs.length}）：{[...refs].sort().join("、")}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function Cleanup() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState("");

  useEffect(() => {
    api<Plan>("/cleanup/images").then(setPlan, (e) => setPlanError((e as Error).message));
  }, []);

  async function go() {
    setBusy(true);
    setError("");
    try {
      setResult(await api<Result>("/cleanup", jsonInit("POST", { confirm: text })));
      setTimeout(() => {
        window.location.href = "/login";
      }, 3000);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Shell title="發佈前清理">
      <div className="card">
        <p>這會執行下列動作，無法復原：</p>
        <ul>
          <li>關閉所有 instance 並移除殘留 container 與 network</li>
          <li>刪除 CTFd 中所有非管理者使用者與其紀錄</li>
          <li>清除 web app 登入 session</li>
          <li>移除下列未使用的 image 與 registry tag，清掉 build cache 與匿名 volume，並整理 registry（會短暫重啟）</li>
        </ul>
        <h2>未使用的 image</h2>
        {planError && <div className="error">無法取得清單：{planError}</div>}
        {!plan && !planError && <p>載入中…</p>}
        {plan && (
          <>
            <p>
              將移除 {plan.images.length} 個 image（最多釋放 {mb(plan.reclaimable_bytes)}，這是各 image 大小相加，共用的 layer 會重複計算）與 {plan.registry.length} 個
              registry tag。清理時會在關閉 instance 之後重新計算一次。
            </p>
            <ul>
              {plan.images.map((i) => (
                <li key={i.id + i.ref}>
                  <code>{i.ref || `未標記 ${i.id.slice(7, 19)}`}</code>（{mb(i.size)}）
                </li>
              ))}
              {plan.registry.map((t) => (
                <li key={t.repo + t.tag}>
                  registry：<code>{`${t.repo}:${t.tag}`}</code>
                </li>
              ))}
            </ul>
            <Kept title="保留的 image" kept={plan.kept_images} />
            <Kept title="保留的 registry tag" kept={plan.kept_registry} />
          </>
        )}
        <label htmlFor="confirm">請輸入 CLEANUP 以確認</label>
        <div className="row">
          <input id="confirm" value={text} autoComplete="off" onChange={(e) => setText(e.target.value)} />
          <button className="danger" onClick={go} disabled={busy || text !== "CLEANUP"}>
            執行清理
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        {result && (
          <p>
            已完成：關閉 {result.instances} 個 instance，移除 {result.containers} 個 container 與{" "}
            {result.networks} 個 network，刪除 {result.users} 位使用者，清除 {result.sessions} 個 session，移除{" "}
            {result.images} 個 image 與 {result.registry_tags} 個 registry tag（最多 {mb(result.reclaimed_bytes)}）。即將回到登入頁。
          </p>
        )}
      </div>
    </Shell>
  );
}

"use client";

import { useState } from "react";

import { Nav } from "@/app/nav";
import { api, jsonInit } from "@/lib/api";

type Result = { instances: number; containers: number; networks: number; users: number; sessions: number };

export default function Cleanup() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);

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
    <>
      <header className="bar">
        <h1>發佈前清理</h1>
        <Nav />
      </header>
      <main>
        <div className="card">
          <p>這會執行下列動作，無法復原：</p>
          <ul>
            <li>關閉所有 instance 並移除殘留 container 與 network</li>
            <li>刪除 CTFd 中所有非管理者使用者與其紀錄</li>
            <li>清除 web app 登入 session</li>
          </ul>
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
              {result.networks} 個 network，刪除 {result.users} 位使用者，清除 {result.sessions} 個
              session。即將回到登入頁。
            </p>
          )}
        </div>
      </main>
    </>
  );
}

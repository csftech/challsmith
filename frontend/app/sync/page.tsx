"use client";

import { useEffect, useState } from "react";

import { Nav } from "@/app/nav";
import { api, ApiError, jsonInit } from "@/lib/api";

type Git = {
  remote_url: string;
  username: string;
  token_set: boolean;
  branch: string;
  dir: string;
  author_name: string;
  author_email: string;
};
type Item = { slug: string; status: string; error?: string };
type Preview = { preview_id: string; items: Item[] };
type Exported = { commit: string | null; pushed: boolean; error: string | null };

const STATUS: Record<string, string> = {
  new: "新題目",
  unchanged: "沒有變動",
  source_changed: "只有來源改過",
  db_changed: "只有資料庫改過",
  conflict: "衝突",
  invalid: "格式錯誤",
};
const FIELDS: [keyof Git, string][] = [
  ["remote_url", "遠端網址"],
  ["username", "使用者名稱"],
  ["branch", "分支"],
  ["dir", "資料夾"],
  ["author_name", "作者名稱"],
  ["author_email", "作者 email"],
];
const PUSH_HINT = "公司內無法 push 到外部時，請改用下載備份";

export default function Sync() {
  const [git, setGit] = useState<Git | null>(null);
  const [token, setToken] = useState("");
  const [gitMsg, setGitMsg] = useState("");
  const [push, setPush] = useState(true);
  const [exp, setExp] = useState<Exported | null>(null);
  const [expErr, setExpErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [decisions, setDecisions] = useState<Record<string, "source" | "db">>({});
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api<Git>("/settings/git").then(setGit, (e) => setGitMsg(e.message));
  }, []);

  async function run<T>(fn: () => Promise<T>, onErr: (m: string) => void): Promise<T | undefined> {
    setBusy(true);
    try {
      return await fn();
    } catch (e) {
      onErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!git) return;
    setGitMsg("");
    const saved = await run(
      () => api<Git>("/settings/git", jsonInit("PUT", { ...git, token: token || null })),
      setGitMsg,
    );
    if (saved) {
      setGit(saved);
      setToken("");
      setGitMsg("已儲存");
    }
  }

  async function doExport() {
    setExp(null);
    setExpErr("");
    const r = await run(() => api<Exported>("/sync/git/export", jsonInit("POST", { push })), setExpErr);
    if (r) setExp(r);
  }

  async function load(fn: () => Promise<Preview>) {
    setMsg("");
    setPreview(null);
    setDecisions({});
    const p = await run(fn, setMsg);
    if (p) setPreview(p);
  }

  function upload(f: File) {
    const form = new FormData();
    form.append("file", f);
    return load(() => api<Preview>("/sync/archive/preview", { method: "POST", body: form }));
  }

  async function apply() {
    if (!preview) return;
    setMsg("");
    setBusy(true);
    try {
      const r = await api<{ applied: string[] }>(
        "/sync/apply",
        jsonInit("POST", { preview_id: preview.preview_id, decisions }),
      );
      setPreview(null);
      setMsg(`已套用 ${r.applied.length} 題`);
    } catch (e) {
      const s = e instanceof ApiError ? e.status : 0;
      setMsg(
        s === 409 ? "資料已變動，請重新預覽" : s === 404 ? "預覽已過期，請重新預覽" : (e as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }

  const conflicts = preview?.items.filter((i) => i.status === "conflict") ?? [];
  const ready = conflicts.every((i) => decisions[i.slug]);

  return (
    <>
      <header className="bar">
        <h1>同步</h1>
        <Nav />
      </header>
      <main className="stack">
        <section className="panel">
          <h2>git 設定</h2>
          {git && (
            <>
              {FIELDS.map(([k, label]) => (
                <div key={k}>
                  <label htmlFor={k}>{label}</label>
                  <input
                    id={k}
                    size={40}
                    value={git[k] as string}
                    onChange={(e) => setGit({ ...git, [k]: e.target.value })}
                  />
                </div>
              ))}
              <label htmlFor="token">
                存取權杖（token）{git.token_set ? "：已設定，留空代表不變" : "：尚未設定"}
              </label>
              <input
                id="token"
                type="password"
                size={40}
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <div className="row" style={{ marginTop: 8 }}>
                <button className="primary" onClick={save} disabled={busy}>
                  儲存設定
                </button>
              </div>
            </>
          )}
          {gitMsg && <div className="error">{gitMsg}</div>}
        </section>

        <section className="panel">
          <h2>匯出到 git</h2>
          <div className="row">
            <label className="inline">
              <input type="checkbox" checked={push} onChange={(e) => setPush(e.target.checked)} />
              匯出後 push
            </label>
            <button onClick={doExport} disabled={busy}>
              匯出到 git
            </button>
          </div>
          {exp && (
            <>
              <p>
                commit：{exp.commit ?? "沒有新的變動"}；push：{exp.pushed ? "成功" : "未 push"}
              </p>
              {exp.error && (
                <div className="error">
                  {exp.error}
                  {"\n"}
                  {PUSH_HINT}
                </div>
              )}
            </>
          )}
          {expErr && (
            <div className="error">
              {expErr}
              {"\n"}
              {PUSH_HINT}
            </div>
          )}
        </section>

        <section className="panel">
          <h2>匯入</h2>
          <div className="row">
            <button onClick={() => load(() => api<Preview>("/sync/git/preview", { method: "POST" }))} disabled={busy}>
              從 git 匯入
            </button>
            <label className="inline">
              上傳備份（.tar.gz）
              <input
                type="file"
                accept=".gz,.tgz,application/gzip"
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload(f);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          {preview && (
            <>
              <table style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>slug</th>
                    <th>狀態</th>
                    <th>處理</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.map((i) => (
                    <tr key={i.slug}>
                      <td>{i.slug}</td>
                      <td>
                        {STATUS[i.status] ?? i.status}
                        {i.error && <div className="error">{i.error}</div>}
                      </td>
                      <td>
                        {i.status === "conflict" &&
                          (["db", "source"] as const).map((d) => (
                            <label key={d} className="inline" style={{ marginRight: 12 }}>
                              <input
                                type="radio"
                                name={`d-${i.slug}`}
                                checked={decisions[i.slug] === d}
                                onChange={() => setDecisions({ ...decisions, [i.slug]: d })}
                              />
                              {d === "db" ? "保留資料庫版" : "採用來源版"}
                            </label>
                          ))}
                      </td>
                    </tr>
                  ))}
                  {preview.items.length === 0 && (
                    <tr>
                      <td colSpan={3}>沒有題目</td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="row" style={{ marginTop: 8 }}>
                <button className="primary" onClick={apply} disabled={busy || !ready}>
                  套用
                </button>
              </div>
            </>
          )}
          {msg && <div className="error">{msg}</div>}
        </section>

        <section className="panel">
          <h2>備份</h2>
          <a className="btn" href="/api/backup">
            下載備份
          </a>
        </section>
      </main>
    </>
  );
}

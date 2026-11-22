"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Shell } from "@/app/shell";
import { api, ApiError, jsonInit } from "@/lib/api";
import { useErrorText } from "@/lib/errors";

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

const STATUS = ["new", "unchanged", "source_changed", "db_changed", "conflict", "invalid"] as const;
const FIELDS = ["remote_url", "username", "branch", "dir", "author_name", "author_email"] as const;

export default function Sync() {
  const t = useTranslations("sync");
  const nav = useTranslations("nav");
  const errorText = useErrorText();
  const [git, setGit] = useState<Git | null>(null);
  const [token, setToken] = useState("");
  const [gitMsg, setGitMsg] = useState("");
  const [gitOk, setGitOk] = useState(false);
  const [push, setPush] = useState(true);
  const [exp, setExp] = useState<Exported | null>(null);
  const [expErr, setExpErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [decisions, setDecisions] = useState<Record<string, "source" | "db">>({});
  const [msg, setMsg] = useState("");
  const [msgOk, setMsgOk] = useState(false);

  useEffect(() => {
    api<Git>("/settings/git").then(setGit, (e) => setGitMsg(errorText(e)));
  }, []);

  async function run<T>(fn: () => Promise<T>, onErr: (m: string) => void): Promise<T | undefined> {
    setBusy(true);
    try {
      return await fn();
    } catch (e) {
      onErr(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!git) return;
    setGitMsg("");
    setGitOk(false);
    const saved = await run(
      () => api<Git>("/settings/git", jsonInit("PUT", { ...git, token: token || null })),
      setGitMsg,
    );
    if (saved) {
      setGit(saved);
      setToken("");
      setGitMsg(t("saved"));
      setGitOk(true);
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
    setMsgOk(false);
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
    setMsgOk(false);
    setBusy(true);
    try {
      const r = await api<{ applied: string[] }>(
        "/sync/apply",
        jsonInit("POST", { preview_id: preview.preview_id, decisions }),
      );
      setPreview(null);
      setMsg(t("applied", { n: r.applied.length }));
      setMsgOk(true);
    } catch (e) {
      const s = e instanceof ApiError ? e.status : 0;
      setMsg(
        s === 409 ? t("changed") : s === 404 ? t("expired") : errorText(e),
      );
    } finally {
      setBusy(false);
    }
  }

  const conflicts = preview?.items.filter((i) => i.status === "conflict") ?? [];
  const ready = conflicts.every((i) => decisions[i.slug]);

  return (
    <Shell title={nav("sync")}>
      <div className="stack">
        <section className="panel">
          <h2>{t("gitSettings")}</h2>
          {git && (
            <>
              {FIELDS.map((k) => (
                <div key={k}>
                  <label htmlFor={k}>{t(`field.${k}`)}</label>
                  <input
                    id={k}
                    size={40}
                    value={git[k] as string}
                    onChange={(e) => setGit({ ...git, [k]: e.target.value })}
                  />
                </div>
              ))}
              <label htmlFor="token">
                {t("token")}{git.token_set ? t("tokenSet") : t("tokenUnset")}
              </label>
              <input
                id="token"
                type="password"
                size={40}
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <div className="row">
                <button className="primary" onClick={save} disabled={busy}>
                  {t("saveSettings")}
                </button>
              </div>
            </>
          )}
          {gitMsg && <div className={gitOk ? "note-ok" : "error"}>{gitMsg}</div>}
        </section>

        <section className="panel">
          <h2>{t("exportTitle")}</h2>
          <div className="row">
            <label className="inline">
              <input type="checkbox" checked={push} onChange={(e) => setPush(e.target.checked)} />
              {t("pushAfter")}
            </label>
            <button onClick={doExport} disabled={busy}>
              {t("export")}
            </button>
          </div>
          {exp && (
            <>
              <p>
                {t("result", { commit: exp.commit ?? t("noChanges"), push: exp.pushed ? t("pushed") : t("notPushed") })}
              </p>
              {exp.error && (
                <div className="error">
                  {exp.error}
                  {"\n"}
                  {t("pushHint")}
                </div>
              )}
            </>
          )}
          {expErr && (
            <div className="error">
              {expErr}
              {"\n"}
              {t("pushHint")}
            </div>
          )}
        </section>

        <section className="panel">
          <h2>{t("importTitle")}</h2>
          <div className="row">
            <button onClick={() => load(() => api<Preview>("/sync/git/preview", { method: "POST" }))} disabled={busy}>
              {t("fromGit")}
            </button>
            <label className="inline">
              {t("uploadArchive")}
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
              <table className="gap">
                <thead>
                  <tr>
                    <th>slug</th>
                    <th>{t("colStatus")}</th>
                    <th>{t("colAction")}</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.map((i) => (
                    <tr key={i.slug}>
                      <td>{i.slug}</td>
                      <td>
                        {(STATUS as readonly string[]).includes(i.status) ? t(`status.${i.status as (typeof STATUS)[number]}`) : i.status}
                        {i.error && <div className="error">{i.error}</div>}
                      </td>
                      <td>
                        {i.status === "conflict" &&
                          (["db", "source"] as const).map((d) => (
                            <label key={d} className="inline choice">
                              <input
                                type="radio"
                                name={`d-${i.slug}`}
                                checked={decisions[i.slug] === d}
                                onChange={() => setDecisions({ ...decisions, [i.slug]: d })}
                              />
                              {d === "db" ? t("keepDb") : t("useSource")}
                            </label>
                          ))}
                      </td>
                    </tr>
                  ))}
                  {preview.items.length === 0 && (
                    <tr>
                      <td colSpan={3}>{t("noChallenges")}</td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="row gap">
                <button className="primary" onClick={apply} disabled={busy || !ready}>
                  {t("apply")}
                </button>
              </div>
            </>
          )}
          {msg && <div className={msgOk ? "note-ok" : "error"}>{msg}</div>}
        </section>

        <section className="panel">
          <h2>{t("backupTitle")}</h2>
          <a className="btn" href="/api/backup">
            {t("download")}
          </a>
        </section>
      </div>
    </Shell>
  );
}

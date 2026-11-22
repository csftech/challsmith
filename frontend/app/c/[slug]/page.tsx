"use client";

import { css } from "@codemirror/lang-css";
import { html } from "@codemirror/lang-html";
import { javascript } from "@codemirror/lang-javascript";
import { php } from "@codemirror/lang-php";
import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import { StreamLanguage } from "@codemirror/language";
import { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";
import { nginx } from "@codemirror/legacy-modes/mode/nginx";
import CodeMirror from "@uiw/react-codemirror";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  apiRaw,
  ApiError,
  fileUrl,
  jsonInit,
  type Detail,
  type Meta,
} from "@/lib/api";
import { Nav } from "@/app/nav";
import { decode, encode, type Enc } from "@/lib/text";

type SvcForm = { name: string; port: string; entry: boolean; useImage: boolean; image: string; env: string };
type Form = { meta: Meta; tags: string; svcs: SvcForm[] };

function toForm(meta: Meta): Form {
  return {
    meta,
    tags: meta.tags.join(", "),
    svcs: meta.services.map((s) => ({
      name: s.name,
      port: s.port == null ? "" : String(s.port),
      entry: s.entry,
      useImage: s.image != null,
      image: s.image ?? "",
      env: Object.entries(s.env).map(([k, v]) => `${k}=${v}`).join("\n"),
    })),
  };
}

function toMeta(f: Form): Meta {
  return {
    ...f.meta,
    tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
    services: f.svcs.map((s) => ({
      name: s.name,
      port: s.port.trim() === "" ? null : Number(s.port),
      entry: s.entry,
      image: s.useImage ? s.image.trim() : null,
      env: Object.fromEntries(
        s.env.split("\n").filter((l) => l.includes("=")).map((l) => {
          const i = l.indexOf("=");
          return [l.slice(0, i).trim(), l.slice(i + 1)];
        }),
      ),
    })),
  };
}

function langFor(path: string) {
  const base = path.split("/").pop()!.toLowerCase();
  if (base === "dockerfile" || base.startsWith("dockerfile.")) return [StreamLanguage.define(dockerFile)];
  if (base.endsWith(".conf") || base.startsWith("nginx")) return [StreamLanguage.define(nginx)];
  switch (base.split(".").pop()) {
    case "php": return [php()];
    case "py": return [python()];
    case "js": case "mjs": case "cjs": case "json": return [javascript()];
    case "jsx": return [javascript({ jsx: true })];
    case "ts": return [javascript({ typescript: true })];
    case "tsx": return [javascript({ typescript: true, jsx: true })];
    case "html": case "htm": return [html()];
    case "css": return [css()];
    case "yml": case "yaml": return [yaml()];
    default: return [];
  }
}

export default function Editor() {
  const { slug } = useParams<{ slug: string }>();
  const [form, setForm] = useState<Form | null>(null);
  const [files, setFiles] = useState<Detail["files"]>([]);
  const [metaMsg, setMetaMsg] = useState("");
  const [fileMsg, setFileMsg] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null); // null = binary / not loaded
  const [dirty, setDirty] = useState(false);
  const [uploadSvc, setUploadSvc] = useState("");
  const [uploadSub, setUploadSub] = useState("");
  const want = useRef<string | null>(null); // path of the latest open() request
  const enc = useRef<Enc>({ bom: false, crlf: false });

  const load = useCallback(async () => {
    const d = await api<Detail>(`/challenges/${slug}`);
    setFiles(d.files);
    return d;
  }, [slug]);

  useEffect(() => {
    load().then((d) => setForm(toForm(d.meta)), (e) => setMetaMsg(e.message));
  }, [load]);

  if (!form) return <main><div className="error">{metaMsg || "載入中…"}</div></main>;
  const { meta, svcs } = form;
  const setMeta = (p: Partial<Meta>) => setForm({ ...form, meta: { ...meta, ...p } });
  const setSvc = (i: number, p: Partial<SvcForm>) =>
    setForm({ ...form, svcs: svcs.map((s, j) => (j === i ? { ...s, ...p } : s)) });
  const folders = svcs.filter((s) => !s.useImage && s.name).map((s) => s.name);

  async function saveMeta(prune = false) {
    setMetaMsg("");
    try {
      await api(`/challenges/${slug}${prune ? "?prune=true" : ""}`, jsonInit("PUT", toMeta(form!)));
      const d = await load();
      setForm(toForm(d.meta));
      setMetaMsg("已儲存");
    } catch (e) {
      const orphans = e instanceof ApiError && e.status === 409 ? (e.detail as { orphans?: string[] })?.orphans : null;
      if (orphans) {
        if (confirm(`這個變更會讓下列 service 檔案失去對應的 service，確認後會一併刪除：\n\n${orphans.join("\n")}`)) {
          return saveMeta(true);
        }
        setMetaMsg("已取消儲存");
      } else {
        setMetaMsg((e as Error).message);
      }
    }
  }

  async function open(path: string) {
    if (dirty && !confirm("目前的檔案尚未儲存，要放棄修改嗎？")) return;
    setFileMsg("");
    want.current = path;
    setSel(path);
    setDirty(false);
    setText(null); // editor stays hidden until this file has loaded
    try {
      const buf = new Uint8Array(await (await apiRaw(fileUrl(slug, path))).arrayBuffer());
      if (want.current !== path) return; // a newer open() superseded this one
      const d = decode(buf);
      if (!d) {
        setFileMsg("這個檔案不是 UTF-8 文字或換行符號混用，無法在此編輯（避免改動未編輯的位元組）");
        return;
      }
      enc.current = d.enc;
      setText(d.text);
    } catch (e) {
      if (want.current === path) setFileMsg((e as Error).message);
    }
  }

  async function saveFile() {
    if (sel == null || text == null) return;
    try {
      await apiRaw(fileUrl(slug, sel), {
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream" },
        body: encode(text, enc.current) as BodyInit,
      });
      setDirty(false);
      setFileMsg("已儲存");
      await load();
    } catch (e) {
      setFileMsg((e as Error).message);
    }
  }

  async function addFile() {
    const path = prompt("新檔案路徑（例如 services/web/app.py）");
    if (!path) return;
    if (files.some((f) => f.path === path)) return open(path); // never truncate an existing file
    try {
      await apiRaw(fileUrl(slug, path), { method: "PUT", body: "" });
      await load();
      await open(path);
    } catch (e) {
      setFileMsg((e as Error).message);
    }
  }

  async function removeFile() {
    if (sel == null || !confirm(`確定刪除 ${sel}？`)) return;
    try {
      await apiRaw(fileUrl(slug, sel), { method: "DELETE" });
      want.current = null;
      setSel(null);
      setText(null);
      setDirty(false);
      setFileMsg("");
      await load();
    } catch (e) {
      setFileMsg((e as Error).message);
    }
  }

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const input = e.target;
    if (!file) return;
    const svc = uploadSvc || folders[0];
    if (!svc) {
      setFileMsg("沒有可上傳的 service 資料夾");
      return;
    }
    const sub = uploadSub.trim().replace(/^\/+|\/+$/g, "");
    const body = new FormData();
    body.append("file", file);
    try {
      await apiRaw(`/challenges/${slug}/upload?dir=${encodeURIComponent(`services/${svc}${sub ? `/${sub}` : ""}`)}`, {
        method: "POST",
        body,
      });
      setFileMsg(`已上傳 ${file.name}`);
      await load();
    } catch (err) {
      setFileMsg((err as Error).message);
    }
    input.value = "";
  }

  async function removeChallenge() {
    if (!confirm(`確定刪除題目 ${slug}？這也會刪除 CTFd 上已發佈的題目。`)) return;
    try {
      await apiRaw(`/challenges/${slug}`, { method: "DELETE" });
      window.location.href = "/";
    } catch (e) {
      setMetaMsg((e as Error).message);
    }
  }

  return (
    <>
      <header className="bar">
        <h1>{meta.name}（{slug}）</h1>
        <Link className="btn primary" href={`/c/${slug}/publish`}>發佈</Link>
        <Nav />
      </header>
      <main className="editor">
        <section className="panel">
          <label htmlFor="name">標題</label>
          <input id="name" value={meta.name} onChange={(e) => setMeta({ name: e.target.value })} />
          <label htmlFor="cat">分類</label>
          <input id="cat" value={meta.category} onChange={(e) => setMeta({ category: e.target.value })} />
          <label htmlFor="tags">標籤（以逗號分隔）</label>
          <input id="tags" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
          <label htmlFor="desc">描述（Markdown）</label>
          <textarea id="desc" rows={8} value={meta.description} onChange={(e) => setMeta({ description: e.target.value })} />
          <div className="row">
            <div>
              <label htmlFor="value">分數</label>
              <input id="value" type="number" min={1} value={meta.value} onChange={(e) => setMeta({ value: Number(e.target.value) })} />
            </div>
            <div>
              <label htmlFor="scenario">scenario</label>
              <select id="scenario" value={meta.scenario} onChange={(e) => setMeta({ scenario: e.target.value as Meta["scenario"] })}>
                <option value="single">single</option>
                <option value="multi">multi</option>
              </select>
            </div>
            <div>
              <label htmlFor="protocol">協定</label>
              <select id="protocol" value={meta.protocol} onChange={(e) => setMeta({ protocol: e.target.value as Meta["protocol"] })}>
                <option value="http">http</option>
                <option value="tcp">tcp</option>
              </select>
            </div>
          </div>
          <label>範本</label>
          <input value={meta.template ?? ""} readOnly />
          <div className="row">
            <div>
              <label htmlFor="flag">flag</label>
              <input id="flag" value={meta.flag} onChange={(e) => setMeta({ flag: e.target.value })} />
            </div>
            <div>
              <label htmlFor="fp">flag 前綴</label>
              <input id="fp" value={meta.flag_prefix} onChange={(e) => setMeta({ flag_prefix: e.target.value })} size={8} />
            </div>
          </div>
          <label>執行個體</label>
          <div className="row">
            <label className="inline">逾時（秒）
              <input type="number" min={1} style={{ width: 90 }} value={meta.instance.timeout}
                onChange={(e) => setMeta({ instance: { ...meta.instance, timeout: Number(e.target.value) } })} />
            </label>
            <label className="inline">mana
              <input type="number" min={1} style={{ width: 60 }} value={meta.instance.mana}
                onChange={(e) => setMeta({ instance: { ...meta.instance, mana: Number(e.target.value) } })} />
            </label>
            <label className="inline">記憶體
              <input style={{ width: 70 }} value={meta.instance.memory}
                onChange={(e) => setMeta({ instance: { ...meta.instance, memory: e.target.value } })} />
            </label>
            <label className="inline">CPU
              <input style={{ width: 60 }} value={meta.instance.cpus}
                onChange={(e) => setMeta({ instance: { ...meta.instance, cpus: e.target.value } })} />
            </label>
          </div>
          <p>
            <label className="inline">
              <input type="checkbox" checked={meta.visible} onChange={(e) => setMeta({ visible: e.target.checked })} />
              在 CTFd 上可見
            </label>
          </p>

          <label>Services</label>
          {svcs.map((s, i) => (
            <div className="svc" key={i}>
              <div className="row">
                <input placeholder="名稱" value={s.name} size={12} onChange={(e) => setSvc(i, { name: e.target.value })} />
                <input placeholder="port" type="number" style={{ width: 80 }} value={s.port} onChange={(e) => setSvc(i, { port: e.target.value })} />
                <label className="inline">
                  <input type="radio" name="entry" checked={s.entry}
                    onChange={() => setForm({ ...form, svcs: svcs.map((x, j) => ({ ...x, entry: i === j })) })} />
                  入口
                </label>
                <label className="inline">
                  <input type="checkbox" checked={s.useImage} onChange={(e) => setSvc(i, { useImage: e.target.checked })} />
                  現成 image
                </label>
                <button className="danger" onClick={() => setForm({ ...form, svcs: svcs.filter((_, j) => j !== i) })}>刪除</button>
              </div>
              {s.useImage && (
                <input placeholder="image（例如 mariadb:11.8）" style={{ width: "100%", marginTop: 6 }} value={s.image}
                  onChange={(e) => setSvc(i, { image: e.target.value })} />
              )}
              <label>環境變數（每行 KEY=VALUE）</label>
              <textarea rows={3} value={s.env} onChange={(e) => setSvc(i, { env: e.target.value })} />
            </div>
          ))}
          <button onClick={() => setForm({ ...form, svcs: [...svcs, { name: "", port: "", entry: false, useImage: false, image: "", env: "" }] })}>
            新增 service
          </button>

          {metaMsg && <div className={metaMsg === "已儲存" ? "" : "error"}>{metaMsg}</div>}
          <p className="row">
            <button className="primary" onClick={() => saveMeta()}>儲存題目資訊</button>
            <button className="danger" onClick={removeChallenge}>刪除題目</button>
          </p>
        </section>

        <section className="panel">
          <div className="row">
            <button onClick={addFile}>新增檔案</button>
            <button className="danger" disabled={sel == null} onClick={removeFile}>刪除檔案</button>
          </div>
          <div className="tree">
            {files.map((f) => (
              <div key={f.path} className={f.path === sel ? "sel" : ""} onClick={() => open(f.path)}
                style={{ paddingLeft: 6 + 14 * (f.path.split("/").length - 1) }}>
                {f.path}
                <span style={{ color: "#8c959f" }}> ({f.size} B)</span>
              </div>
            ))}
          </div>
          <div className="row">
            <span>上傳到</span>
            <select value={uploadSvc || folders[0] || ""} onChange={(e) => setUploadSvc(e.target.value)}>
              {folders.map((n) => <option key={n} value={n}>services/{n}</option>)}
            </select>
            <input placeholder="子資料夾（可留空）" value={uploadSub} onChange={(e) => setUploadSub(e.target.value)} />
            <input type="file" onChange={upload} />
          </div>
          <p style={{ fontSize: 13, color: "#57606a", margin: "4px 0" }}>上傳 .zip 會解壓縮到選定的資料夾。</p>
          {fileMsg && <div className={fileMsg === "已儲存" || fileMsg.startsWith("已上傳") ? "" : "error"}>{fileMsg}</div>}
          {sel != null && text != null && (
            <>
              <div className="row" style={{ margin: "8px 0" }}>
                <strong>{sel}</strong>
                <button className="primary" disabled={!dirty} onClick={saveFile}>儲存檔案</button>
              </div>
              <CodeMirror key={sel} value={text} height="520px" extensions={langFor(sel)}
                onChange={(v) => { setText(v); setDirty(true); }} />
            </>
          )}
        </section>
      </main>
    </>
  );
}

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
import { useTranslations } from "next-intl";
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
import { Shell } from "@/app/shell";
import { useErrorText } from "@/lib/errors";
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

// CodeMirror is dark only in the midnight theme; the theme switcher changes this attribute
function useCmTheme(): "light" | "dark" {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const el = document.documentElement;
    const read = () => setTheme(el.dataset.theme === "midnight" ? "dark" : "light");
    read();
    const mo = new MutationObserver(read);
    mo.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);
  return theme;
}

export default function Editor() {
  const t = useTranslations("editor");
  const common = useTranslations("common");
  const errorText = useErrorText();
  const cmTheme = useCmTheme();
  const { slug } = useParams<{ slug: string }>();
  const [form, setForm] = useState<Form | null>(null);
  const [files, setFiles] = useState<Detail["files"]>([]);
  const [metaMsg, setMetaMsg] = useState("");
  const [metaOk, setMetaOk] = useState(false); // metaMsg is a success note, not an error
  const [fileMsg, setFileMsg] = useState("");
  const [fileOk, setFileOk] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null); // null = binary / not loaded
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(""); // last loaded/saved meta, to detect unsaved form changes
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
    load().then((d) => { setForm(toForm(d.meta)); setSaved(JSON.stringify(toMeta(toForm(d.meta)))); }, (e) => setMetaMsg(errorText(e)));
  }, [load]);

  const unsaved = dirty || (form != null && JSON.stringify(toMeta(form)) !== saved);
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    // capture phase: runs before Next's Link handler, so cancelling here stops the navigation
    const click = (e: MouseEvent) => {
      const a = (e.target as Element).closest("a[href]");
      if (!a || a.getAttribute("target") === "_blank") return;
      const publish = a.getAttribute("href")?.endsWith("/publish");
      if (publish ? (alert(t("unsavedPublish")), true) : !confirm(t("unsavedLeave"))) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", click, true);
    };
  }, [unsaved]);

  if (!form) {
    return (
      <Shell title={slug}>
        <div className={metaMsg ? "error" : "muted"}>{metaMsg || common("loading")}</div>
      </Shell>
    );
  }
  const { meta, svcs } = form;
  const setMeta = (p: Partial<Meta>) => setForm({ ...form, meta: { ...meta, ...p } });
  const setSvc = (i: number, p: Partial<SvcForm>) =>
    setForm({ ...form, svcs: svcs.map((s, j) => (j === i ? { ...s, ...p } : s)) });
  const folders = svcs.filter((s) => !s.useImage && s.name).map((s) => s.name);

  async function saveMeta(prune = false) {
    setMetaMsg("");
    setMetaOk(false);
    try {
      await api(`/challenges/${slug}${prune ? "?prune=true" : ""}`, jsonInit("PUT", toMeta(form!)));
      const d = await load();
      setForm(toForm(d.meta));
      setSaved(JSON.stringify(toMeta(toForm(d.meta))));
      setMetaMsg(t("saved"));
      setMetaOk(true);
    } catch (e) {
      const orphans = e instanceof ApiError && e.status === 409 ? (e.detail as { orphans?: string[] })?.orphans : null;
      if (orphans) {
        if (confirm(t("orphanConfirm", { list: orphans.join("\n") }))) {
          return saveMeta(true);
        }
        setMetaMsg(t("saveCanceled"));
      } else {
        setMetaMsg(errorText(e));
      }
    }
  }

  async function open(path: string) {
    if (dirty && !confirm(t("discardFile"))) return;
    setFileMsg("");
    setFileOk(false);
    want.current = path;
    setSel(path);
    setDirty(false);
    setText(null); // editor stays hidden until this file has loaded
    try {
      const buf = new Uint8Array(await (await apiRaw(fileUrl(slug, path))).arrayBuffer());
      if (want.current !== path) return; // a newer open() superseded this one
      const d = decode(buf);
      if (!d) {
        setFileMsg(t("notText"));
        return;
      }
      enc.current = d.enc;
      setText(d.text);
    } catch (e) {
      if (want.current === path) setFileMsg(errorText(e));
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
      setFileMsg(t("saved"));
      setFileOk(true);
      await load();
    } catch (e) {
      setFileMsg(errorText(e));
      setFileOk(false);
    }
  }

  async function addFile() {
    const path = prompt(t("newPath"));
    if (!path) return;
    if (files.some((f) => f.path === path)) return open(path); // never truncate an existing file
    try {
      await apiRaw(fileUrl(slug, path), { method: "PUT", body: "" });
      await load();
      await open(path);
    } catch (e) {
      setFileMsg(errorText(e));
      setFileOk(false);
    }
  }

  async function removeFile() {
    if (sel == null || !confirm(t("deleteFile", { path: sel }))) return;
    try {
      await apiRaw(fileUrl(slug, sel), { method: "DELETE" });
      want.current = null;
      setSel(null);
      setText(null);
      setDirty(false);
      setFileMsg("");
      await load();
    } catch (e) {
      setFileMsg(errorText(e));
      setFileOk(false);
    }
  }

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const input = e.target;
    if (!file) return;
    const svc = uploadSvc || folders[0];
    if (!svc) {
      setFileMsg(t("noUploadDir"));
      setFileOk(false);
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
      setFileMsg(t("uploaded", { name: file.name }));
      setFileOk(true);
      await load();
    } catch (err) {
      setFileMsg(errorText(err));
      setFileOk(false);
    }
    input.value = "";
  }

  async function removeChallenge() {
    if (!confirm(t("deleteChallenge", { slug }))) return;
    try {
      await apiRaw(`/challenges/${slug}`, { method: "DELETE" });
      window.location.href = "/";
    } catch (e) {
      setMetaMsg(errorText(e));
      setMetaOk(false);
    }
  }

  return (
    <Shell title={`${meta.name} (${slug})`}>
      <div className="row">
        <Link className="btn primary" href={`/c/${slug}/publish`}>{t("publish")}</Link>
      </div>
      <div className="editor">
        <section className="panel form">
          <label htmlFor="name">{t("name")}</label>
          <input id="name" value={meta.name} onChange={(e) => setMeta({ name: e.target.value })} />
          <label htmlFor="cat">{t("category")}</label>
          <input id="cat" value={meta.category} onChange={(e) => setMeta({ category: e.target.value })} />
          <label htmlFor="tags">{t("tags")}</label>
          <input id="tags" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
          <label htmlFor="desc">{t("description")}</label>
          <textarea id="desc" rows={8} value={meta.description} onChange={(e) => setMeta({ description: e.target.value })} />
          <div className="row">
            <div>
              <label htmlFor="value">{t("value")}</label>
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
              <label htmlFor="protocol">{t("protocol")}</label>
              <select id="protocol" value={meta.protocol} onChange={(e) => setMeta({ protocol: e.target.value as Meta["protocol"] })}>
                <option value="http">http</option>
                <option value="tcp">tcp</option>
              </select>
            </div>
          </div>
          <label>{t("template")}</label>
          <input value={meta.template ?? ""} readOnly />
          <div className="row">
            <div>
              <label htmlFor="flag">flag</label>
              <input id="flag" value={meta.flag} onChange={(e) => setMeta({ flag: e.target.value })} />
            </div>
            <div>
              <label htmlFor="fp">{t("flagPrefix")}</label>
              <input id="fp" value={meta.flag_prefix} onChange={(e) => setMeta({ flag_prefix: e.target.value })} size={8} />
            </div>
          </div>
          <label>{t("instance")}</label>
          <div className="row">
            <label className="inline">{t("timeout")}
              <input className="w90" type="number" min={1} value={meta.instance.timeout}
                onChange={(e) => setMeta({ instance: { ...meta.instance, timeout: Number(e.target.value) } })} />
            </label>
            <label className="inline">mana
              <input className="w60" type="number" min={0} value={meta.instance.mana}
                onChange={(e) => setMeta({ instance: { ...meta.instance, mana: Number(e.target.value) } })} />
            </label>
            <label className="inline">{t("memory")}
              <input className="w70" value={meta.instance.memory}
                onChange={(e) => setMeta({ instance: { ...meta.instance, memory: e.target.value } })} />
            </label>
            <label className="inline">CPU
              <input className="w60" value={meta.instance.cpus}
                onChange={(e) => setMeta({ instance: { ...meta.instance, cpus: e.target.value } })} />
            </label>
          </div>
          <p>
            <label className="inline">
              <input type="checkbox" checked={meta.visible} onChange={(e) => setMeta({ visible: e.target.checked })} />
              {t("visible")}
            </label>
          </p>

          <label>{t("services")}</label>
          {svcs.map((s, i) => (
            <div className="svc" key={i}>
              <div className="row">
                <input placeholder={t("svcName")} value={s.name} size={12} onChange={(e) => setSvc(i, { name: e.target.value })} />
                <input placeholder="port" type="number" className="w80" value={s.port} onChange={(e) => setSvc(i, { port: e.target.value })} />
                <label className="inline">
                  <input type="radio" name="entry" checked={s.entry}
                    onChange={() => setForm({ ...form, svcs: svcs.map((x, j) => ({ ...x, entry: i === j })) })} />
                  {t("entry")}
                </label>
                <label className="inline">
                  <input type="checkbox" checked={s.useImage} onChange={(e) => setSvc(i, { useImage: e.target.checked })} />
                  {t("useImage")}
                </label>
                <button className="danger" onClick={() => setForm({ ...form, svcs: svcs.filter((_, j) => j !== i) })}>{t("remove")}</button>
              </div>
              {s.useImage && (
                <input placeholder={t("imagePlaceholder")} className="full" value={s.image}
                  onChange={(e) => setSvc(i, { image: e.target.value })} />
              )}
              <label>{t("env")}</label>
              <textarea rows={3} value={s.env} onChange={(e) => setSvc(i, { env: e.target.value })} />
            </div>
          ))}
          <button onClick={() => setForm({ ...form, svcs: [...svcs, { name: "", port: "", entry: false, useImage: false, image: "", env: "" }] })}>
            {t("addService")}
          </button>

          {metaMsg && <div className={metaOk ? "note-ok" : "error"}>{metaMsg}</div>}
          <p className="row">
            <button className="primary" onClick={() => saveMeta()}>{t("saveMeta")}</button>
            <button className="danger" onClick={removeChallenge}>{t("removeChallenge")}</button>
          </p>
        </section>

        <section className="panel">
          <div className="row">
            <button onClick={addFile}>{t("addFile")}</button>
            <button className="danger" disabled={sel == null} onClick={removeFile}>{t("removeFile")}</button>
          </div>
          <div className="tree">
            {files.map((f) => (
              <div key={f.path} className={f.path === sel ? "sel" : ""} onClick={() => open(f.path)}
                style={{ paddingLeft: 6 + 14 * (f.path.split("/").length - 1) }}>
                {f.path}
                <span className="muted"> ({f.size} B)</span>
              </div>
            ))}
          </div>
          <div className="row">
            <span>{t("uploadTo")}</span>
            <select value={uploadSvc || folders[0] || ""} onChange={(e) => setUploadSvc(e.target.value)}>
              {folders.map((n) => <option key={n} value={n}>services/{n}</option>)}
            </select>
            <input placeholder={t("subfolder")} value={uploadSub} onChange={(e) => setUploadSub(e.target.value)} />
            <input type="file" onChange={upload} />
          </div>
          <p className="muted hint">{t("zipHint")}</p>
          {fileMsg && <div className={fileOk ? "note-ok" : "error"}>{fileMsg}</div>}
          {sel != null && text != null && (
            <>
              <div className="row filebar">
                <strong>{sel}</strong>
                <button className="primary" disabled={!dirty} onClick={saveFile}>{t("saveFile")}</button>
              </div>
              <CodeMirror key={sel} value={text} height="520px" theme={cmTheme} extensions={langFor(sel)}
                onChange={(v) => { setText(v); setDirty(true); }} />
            </>
          )}
        </section>
      </div>
    </Shell>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, jsonInit, type Template } from "@/lib/api";

export default function New() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [template, setTemplate] = useState("");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Template[]>("/templates").then(
      (t) => {
        setTemplates(t);
        setTemplate(t[0]?.name ?? "");
      },
      (e) => setError(e.message),
    );
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/challenges", jsonInit("POST", { slug, template, name }));
      window.location.href = `/c/${slug}`;
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const current = templates.find((t) => t.name === template);
  return (
    <>
      <header className="bar">
        <h1>新增題目</h1>
        <Link className="btn" href="/">回清單</Link>
      </header>
      <main>
        <form className="card" onSubmit={create}>
          <label htmlFor="t">範本</label>
          <select id="t" value={template} onChange={(e) => setTemplate(e.target.value)}>
            {templates.map((t) => (
              <option key={t.name} value={t.name}>{t.name}（{t.scenario}）</option>
            ))}
          </select>
          {current && <p>{current.description}</p>}
          <label htmlFor="s">slug（小寫英數與連字號，最長 48 字）</label>
          <input id="s" value={slug} onChange={(e) => setSlug(e.target.value)} pattern="[a-z0-9][a-z0-9\-]{0,47}" required />
          <label htmlFor="n">標題</label>
          <input id="n" value={name} onChange={(e) => setName(e.target.value)} required />
          {error && <div className="error">{error}</div>}
          <p><button className="primary" disabled={!template}>建立</button></p>
        </form>
      </main>
    </>
  );
}

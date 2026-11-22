"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Shell } from "@/components/shell";
import { api, jsonInit, type Template } from "@/lib/api";
import { useErrorText } from "@/lib/errors";

export default function New() {
  const t = useTranslations("new");
  const nav = useTranslations("nav");
  const errorText = useErrorText();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [template, setTemplate] = useState("");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Template[]>("/templates").then(
      (list) => {
        setTemplates(list);
        setTemplate(list[0]?.name ?? "");
      },
      (e) => setError(errorText(e)),
    );
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/challenges", jsonInit("POST", { slug, template, name }));
      window.location.href = `/c/${slug}`;
    } catch (err) {
      setError(errorText(err));
    }
  }

  const current = templates.find((x) => x.name === template);
  return (
    <Shell title={nav("new")}>
      <form className="card" onSubmit={create}>
        <label htmlFor="t">{t("template")}</label>
        <select id="t" value={template} onChange={(e) => setTemplate(e.target.value)}>
          {templates.map((x) => (
            <option key={x.name} value={x.name}>{x.name} ({x.scenario})</option>
          ))}
        </select>
        {current && <p>{current.description}</p>}
        <label htmlFor="s">{t("slug")}</label>
        <input id="s" value={slug} onChange={(e) => setSlug(e.target.value)} pattern="[a-z0-9][a-z0-9\-]{0,47}" required />
        <label htmlFor="n">{t("name")}</label>
        <input id="n" value={name} onChange={(e) => setName(e.target.value)} required />
        {error && <div className="error">{error}</div>}
        <p><button className="primary" disabled={!template}>{t("create")}</button></p>
      </form>
    </Shell>
  );
}

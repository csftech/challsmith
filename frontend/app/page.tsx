"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ChallengeCards } from "@/app/challenge-cards";
import { ChallengeList } from "@/app/challenge-list";
import { Icon, Shell } from "@/app/shell";
import { SortableTree } from "@/app/sortable";
import { api, apiRaw, jsonInit, type ListResponse, type Summary } from "@/lib/api";
import { useErrorText } from "@/lib/errors";
import { flatten, groupByCategory, matches, moveGroup, moveItem, type Group } from "@/lib/order";

type View = "list" | "cards";
const STATUSES = ["draft", "published", "modified"] as const;

export default function Home() {
  const t = useTranslations();
  const errorText = useErrorText();
  const [items, setItems] = useState<Summary[] | null>(null);
  const [ctfdOk, setCtfdOk] = useState(true);
  const [now, setNow] = useState(() => new Date());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [view, setView] = useState<View>("list");
  const [del, setDel] = useState<Summary | null>(null);
  const search = useRef<HTMLInputElement>(null);

  // refresh=true: a background refresh after a failed save, whose own failure must not hide the save error
  async function load(refresh = false) {
    try {
      const r = await api<ListResponse>("/challenges");
      setItems(r.items);
      setCtfdOk(r.ctfd_ok);
      setNow(new Date());
    } catch (e) {
      if (!refresh) setError(errorText(e));
    }
  }

  useEffect(() => {
    load();
    try {
      if (localStorage.getItem("listView") === "cards") setView("cards");
    } catch {}
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (el.closest("input, textarea, select") || el.isContentEditable) return;
      e.preventDefault();
      search.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function pickView(v: View) {
    setView(v);
    try {
      localStorage.setItem("listView", v);
    } catch {}
  }

  // optimistic: show the new order; on failure restore the previous one, then refresh from the server
  async function save(next: Group[]) {
    const prev = items;
    setItems(next.flatMap((g) => g.items));
    setSaving(true);
    setError("");
    try {
      await api("/challenges/order", jsonInit("PUT", { order: flatten(next) }));
    } catch (e) {
      setItems(prev);
      setError(errorText(e));
      await load(true);
    } finally {
      setSaving(false);
    }
  }

  const all = items ?? [];
  const filtering = q.trim() !== "" || cat !== null || status !== null;
  const visible = all.filter((i) => matches(i, q, cat, status));
  const groups = groupByCategory(visible);
  const locked = filtering || !ctfdOk || saving;
  const categories = [...new Set(all.map((i) => i.category))];
  const published = visible.filter((i) => i.publish !== "draft" && !i.ctfd_missing).length;
  const Body = view === "cards" ? ChallengeCards : ChallengeList;

  const searchBox = (
    <div className="search">
      <Icon name="search" />
      <input ref={search} type="search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder={t("list.search")} aria-label={t("list.search")} />
      <span className="kbd" aria-hidden="true">/</span>
    </div>
  );

  return (
    <Shell title={t("list.title")} search={searchBox}>
      <div className="panel clist">
        <div className="bar">
          <select aria-label={t("list.category")} value={cat === null ? "*" : `=${cat}`}
            onChange={(e) => setCat(e.target.value === "*" ? null : e.target.value.slice(1))}>
            <option value="*">{t("list.allCategories")}</option>
            {categories.map((c) => <option key={c} value={`=${c}`}>{c || t("list.noCategory")}</option>)}
          </select>
          <select aria-label={t("list.status")} value={status ?? "*"}
            onChange={(e) => setStatus(e.target.value === "*" ? null : e.target.value)}>
            <option value="*">{t("list.allStatus")}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{t(`list.publish.${s}`)}</option>)}
          </select>
          <span className="cnt">{t("list.count", { total: visible.length, published })}</span>
          <span className="seg">
            <button type="button" aria-pressed={view === "list"} aria-label={t("list.viewList")} title={t("list.viewList")}
              onClick={() => pickView("list")}><Icon name="list" /></button>
            <button type="button" aria-pressed={view === "cards"} aria-label={t("list.viewCards")} title={t("list.viewCards")}
              onClick={() => pickView("cards")}><Icon name="grid" /></button>
          </span>
          <Link className="btn primary" href="/new"><Icon name="plus" />{t("list.new")}</Link>
        </div>
        {saving && <div className="notice" role="status">{t("list.saving")}</div>}
        {!saving && items && items.length > 0 && (filtering || !ctfdOk) && (
          <div className="notice" role="status">{filtering ? t("list.lockedFilter") : t("list.lockedCtfd")}</div>
        )}
        {error && <div className="notice error" role="alert">{error}</div>}
        {!items && !error && <div className="notice">{t("common.loading")}</div>}
        {items && visible.length === 0 && (
          <div className="notice">{items.length === 0 ? t("list.empty") : t("list.noMatch")}</div>
        )}
        {visible.length > 0 && (
          <SortableTree groups={groups}
            onMoveGroup={(from, to) => save(moveGroup(groups, from, to))}
            onMoveItem={(category, from, to) => save(moveItem(groups, category, from, to))}>
            <Body groups={groups} locked={locked} now={now} onDelete={setDel} />
          </SortableTree>
        )}
      </div>
      {del && <DeleteDialog key={del.slug} target={del} onClose={() => setDel(null)}
        onDeleted={() => { setDel(null); load(); }} />}
    </Shell>
  );
}

function DeleteDialog({ target, onClose, onDeleted }: { target: Summary; onClose: () => void; onDeleted: () => void }) {
  const t = useTranslations("list");
  const errorText = useErrorText();
  const ref = useRef<HTMLDialogElement>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ref.current?.open) ref.current?.showModal();
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiRaw(`/challenges/${encodeURIComponent(target.slug)}`, { method: "DELETE" });
      onDeleted();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="dialog" aria-labelledby="del-title" onClose={onClose}
      onCancel={(e) => { if (busy) e.preventDefault(); }}>
      <form onSubmit={submit}>
        <h2 id="del-title">{t("deleteTitle", { name: target.name })}</h2>
        <p>{t("deleteBody")}</p>
        <label htmlFor="del-slug">{t("deleteConfirm", { slug: target.slug })}</label>
        <input id="del-slug" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" spellCheck={false} autoFocus />
        {error && <div className="error" role="alert">{error}</div>}
        <div className="row actions">
          <button type="button" onClick={() => ref.current?.close()} disabled={busy}>{t("cancel")}</button>
          <button className="danger" disabled={busy || text !== target.slug}>{busy ? t("deleting") : t("delete")}</button>
        </div>
      </form>
    </dialog>
  );
}

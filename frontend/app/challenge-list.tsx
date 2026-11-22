"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Icon } from "@/app/shell";
import { ItemContext, useGroupHandle, useItemHandle } from "@/app/sortable";
import type { Summary } from "@/lib/api";
import type { Group } from "@/lib/order";

export type ViewProps = { groups: Group[]; locked: boolean; now: Date; onDelete: (c: Summary) => void };

// stable palette slot per category; themes without --cat-N-* keep the neutral chip
const hue = (category: string) => [...category.toLowerCase()].reduce((s, ch) => s + ch.codePointAt(0)!, 0) % 6;

export function CategoryName({ category }: { category: string }) {
  const t = useTranslations("list");
  return <>{category || t("noCategory")}</>;
}

export function Status({ c }: { c: Summary }) {
  const t = useTranslations("list");
  if (c.ctfd_missing) return <span className="badge warn"><span className="dot" />{t("missing")}</span>;
  return <span className={c.publish === "published" ? "badge ok" : "badge warn"}><span className="dot" />{t(`publish.${c.publish}`)}</span>;
}

export const ctfdId = (c: Summary) => (c.ctfd_missing || c.ctfd_id === null ? "—" : `#${c.ctfd_id}`);

export function Updated({ c, now }: { c: Summary; now: Date }) {
  const format = useFormatter();
  return <>{format.relativeTime(new Date(c.updated_at), now)}</>;
}

export function Actions({ c, onDelete }: { c: Summary; onDelete: (c: Summary) => void }) {
  const t = useTranslations("list");
  const href = `/c/${encodeURIComponent(c.slug)}`;
  return (
    <span className="acts">
      <Link className="ia" href={href} aria-label={t("edit")} title={t("edit")}><Icon name="edit" /></Link>
      <Link className="ia" href={`${href}/publish`} aria-label={t("publishAction")} title={t("publishAction")}><Icon name="up" /></Link>
      <button type="button" className="ia danger" onClick={() => onDelete(c)} aria-label={t("delete")} title={t("delete")}>
        <Icon name="trash" />
      </button>
    </span>
  );
}

function Row({ c, locked, now, onDelete }: { c: Summary } & Omit<ViewProps, "groups">) {
  const t = useTranslations("list");
  const h = useItemHandle(c.slug, c.category, locked);
  return (
    <div className="tr" role="row" ref={h.setNodeRef} style={h.style}>
      <span role="cell">{h.handle}</span>
      <span role="cell" className="id">{ctfdId(c)}</span>
      <span role="cell" className="nm">
        <Link href={`/c/${encodeURIComponent(c.slug)}`} title={c.name}>{c.name}</Link>
        <span className="slug" title={c.slug}>{c.slug}</span>
      </span>
      <span role="cell"><span className="chip" data-c={hue(c.category)}><CategoryName category={c.category} /></span></span>
      <span role="cell" className="num">{c.value}</span>
      <span role="cell"><Status c={c} /></span>
      <span role="cell" className="muted">{t(`sync.${c.sync}`)}</span>
      <span role="cell" className="muted"><Updated c={c} now={now} /></span>
      <span role="cell"><Actions c={c} onDelete={onDelete} /></span>
    </div>
  );
}

function ListGroup({ group, ...rest }: { group: Group } & Omit<ViewProps, "groups">) {
  const t = useTranslations("list");
  const h = useGroupHandle(group.category, rest.locked);
  const [open, setOpen] = useState(true);
  return (
    <div role="rowgroup" ref={h.setNodeRef} style={h.style}>
      <div className="cat" role="row">
        <span role="cell" className="cat-cell">
          {h.handle}
          <button type="button" className="fold" aria-expanded={open} aria-label={t("fold")} title={t("fold")}
            onClick={() => setOpen(!open)}>
            <Icon name="chev" />
          </button>
          <CategoryName category={group.category} />
          <span className="n">{group.items.length}</span>
        </span>
      </div>
      {open && (
        <ItemContext group={group}>
          {group.items.map((c) => <Row key={c.slug} c={c} {...rest} />)}
        </ItemContext>
      )}
    </div>
  );
}

export function ChallengeList({ groups, ...rest }: ViewProps) {
  const t = useTranslations("list");
  return (
    <div className="scroll">
      <div className="ctable" role="table" aria-label={t("title")}>
        <div className="thead" role="row">
          <span role="columnheader"><span className="sr">{t("dragItem")}</span></span>
          <span role="columnheader">{t("colId")}</span>
          <span role="columnheader">{t("colName")}</span>
          <span role="columnheader">{t("colCategory")}</span>
          <span role="columnheader" className="num">{t("colValue")}</span>
          <span role="columnheader">{t("colPublish")}</span>
          <span role="columnheader">{t("colSync")}</span>
          <span role="columnheader">{t("colUpdated")}</span>
          <span role="columnheader" className="end">{t("colActions")}</span>
        </div>
        {groups.map((g) => <ListGroup key={g.category} group={g} {...rest} />)}
      </div>
    </div>
  );
}

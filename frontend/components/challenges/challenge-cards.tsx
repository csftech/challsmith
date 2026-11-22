"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { Actions, CategoryName, ctfdId, Status, Updated, type ViewProps } from "@/components/challenges/challenge-list";
import { ItemContext, useGroupHandle, useItemHandle } from "@/components/challenges/sortable";
import type { Summary } from "@/lib/api";
import type { Group } from "@/lib/order";

function Card({ c, locked, now, onDelete }: { c: Summary } & Omit<ViewProps, "groups">) {
  const t = useTranslations("list");
  const h = useItemHandle(c.slug, c.category, locked);
  return (
    <article className="ccard" ref={h.setNodeRef} style={h.style}>
      <div className="hd">
        {h.handle}
        <Link className="nm" href={`/c/${encodeURIComponent(c.slug)}`} title={c.name}>{c.name}</Link>
        <Status c={c} />
      </div>
      <div className="sub" title={c.slug}>{c.slug} · CTFd {ctfdId(c)}</div>
      <div className="meta">
        <span className="chip">{c.template ?? c.scenario}</span>
        <span className="chip">{t("services", { n: c.services })}</span>
      </div>
      <div className="ft">
        <span className="pts">{c.value}</span>
        <span className="muted"><Updated c={c} now={now} /></span>
        <Actions c={c} onDelete={onDelete} />
      </div>
    </article>
  );
}

function CardGroup({ group, ...rest }: { group: Group } & Omit<ViewProps, "groups">) {
  const h = useGroupHandle(group.category, rest.locked);
  return (
    <section ref={h.setNodeRef} style={h.style}>
      <h2 className="cat">{h.handle}<CategoryName category={group.category} /><span className="n">· {group.items.length}</span></h2>
      <ItemContext group={group} grid>
        <div className="cgrid">{group.items.map((c) => <Card key={c.slug} c={c} {...rest} />)}</div>
      </ItemContext>
    </section>
  );
}

export function ChallengeCards({ groups, ...rest }: ViewProps) {
  return <div className="cview">{groups.map((g) => <CardGroup key={g.category} group={g} {...rest} />)}</div>;
}

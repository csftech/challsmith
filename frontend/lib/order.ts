import type { Summary } from "./api.ts";

export type Group = { category: string; items: Summary[] };

// Groups in first-seen order; the server already keeps each category contiguous.
export function groupByCategory(items: Summary[]): Group[] {
  const by = new Map<string, Summary[]>();
  for (const it of items) {
    const list = by.get(it.category);
    if (list) list.push(it);
    else by.set(it.category, [it]);
  }
  return [...by].map(([category, items]) => ({ category, items }));
}

export const flatten = (groups: Group[]): string[] => groups.flatMap((g) => g.items.map((i) => i.slug));

function move<T>(list: T[], from: number, to: number): T[] {
  const out = [...list];
  out.splice(to, 0, ...out.splice(from, 1));
  return out;
}

export const moveItem = (groups: Group[], category: string, from: number, to: number): Group[] =>
  groups.map((g) => (g.category === category ? { ...g, items: move(g.items, from, to) } : g));

export const moveGroup = (groups: Group[], from: number, to: number): Group[] => move(groups, from, to);

export function matches(item: Summary, q: string, category: string | null, status: string | null): boolean {
  const needle = q.trim().toLowerCase();
  return (
    (category === null || item.category === category) &&
    (status === null || item.publish === status) &&
    (!needle || item.name.toLowerCase().includes(needle) || item.slug.toLowerCase().includes(needle))
  );
}

"use client";

// dnd-kit wrapper shared by the list and card views: categories sort in an outer context,
// challenges in one inner context per category, and a challenge never lands in another category.
import {
  closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors,
  type CollisionDetection, type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy, rectSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useTranslations } from "next-intl";
import type { CSSProperties, ReactNode } from "react";

import { Icon } from "@/app/shell";
import type { Group } from "@/lib/order";

type Data = { type: "group" } | { type: "item"; category: string };
const groupId = (category: string) => `group:${category}`; // slugs never contain ":"

// only consider targets of the same kind (and, for challenges, the same category)
const sameKind: CollisionDetection = (args) => {
  const a = args.active.data.current as Data | undefined;
  return closestCenter({
    ...args,
    droppableContainers: args.droppableContainers.filter((c) => {
      const d = c.data.current as Data | undefined;
      return d?.type === a?.type && (d?.type === "group" || (a?.type === "item" && d?.type === "item" && d.category === a.category));
    }),
  });
};

export function SortableTree({ groups, onMoveGroup, onMoveItem, children }: {
  groups: Group[];
  onMoveGroup: (from: number, to: number) => void;
  onMoveItem: (category: string, from: number, to: number) => void;
  children: ReactNode;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const t = useTranslations("list.dnd");
  const name = (id: string | number) => String(id).replace(/^group:/, "");
  const accessibility = {
    screenReaderInstructions: { draggable: t("instructions") },
    announcements: {
      onDragStart: ({ active }: { active: { id: string | number } }) => t("start", { id: name(active.id) }),
      onDragOver: ({ active, over }: { active: { id: string | number }; over: { id: string | number } | null }) =>
        over ? t("over", { id: name(active.id), over: name(over.id) }) : undefined,
      onDragEnd: ({ active, over }: { active: { id: string | number }; over: { id: string | number } | null }) =>
        over ? t("end", { id: name(active.id), over: name(over.id) }) : t("cancel", { id: name(active.id) }),
      onDragCancel: ({ active }: { active: { id: string | number } }) => t("cancel", { id: name(active.id) }),
    },
  };

  function end({ active, over }: DragEndEvent) {
    if (!over || active.id === over.id) return;
    const a = active.data.current as Data;
    const o = over.data.current as Data;
    if (a.type === "group" && o.type === "group") {
      const ids = groups.map((g) => groupId(g.category));
      onMoveGroup(ids.indexOf(String(active.id)), ids.indexOf(String(over.id)));
    } else if (a.type === "item" && o.type === "item" && a.category === o.category) {
      const slugs = groups.find((g) => g.category === a.category)!.items.map((i) => i.slug);
      onMoveItem(a.category, slugs.indexOf(String(active.id)), slugs.indexOf(String(over.id)));
    }
  }

  return (
    <DndContext sensors={sensors} collisionDetection={sameKind} onDragEnd={end} accessibility={accessibility}>
      <SortableContext items={groups.map((g) => groupId(g.category))} strategy={verticalListSortingStrategy}>
        {children}
      </SortableContext>
    </DndContext>
  );
}

type Handle = { handle: ReactNode; setNodeRef: (el: HTMLElement | null) => void; style: CSSProperties; dragging: boolean };

function useHandle(id: string, data: Data, disabled: boolean, label: string): Handle {
  const s = useSortable({ id, data, disabled });
  return {
    setNodeRef: s.setNodeRef,
    dragging: s.isDragging,
    style: { transform: CSS.Translate.toString(s.transform), transition: s.transition, zIndex: s.isDragging ? 2 : undefined, position: "relative" },
    handle: (
      <button type="button" className="grip" ref={s.setActivatorNodeRef} disabled={disabled}
        aria-label={label} title={label} {...s.attributes} {...s.listeners}>
        <Icon name="grip" />
      </button>
    ),
  };
}

export function useGroupHandle(category: string, disabled: boolean): Handle {
  const t = useTranslations("list");
  return useHandle(groupId(category), { type: "group" }, disabled, t("dragGroup"));
}

export function useItemHandle(slug: string, category: string, disabled: boolean): Handle {
  const t = useTranslations("list");
  return useHandle(slug, { type: "item", category }, disabled, t("dragItem"));
}

// inner context for one category's challenges; cards wrap, rows stack
export const ItemContext = ({ group, grid, children }: { group: Group; grid?: boolean; children: ReactNode }) => (
  <SortableContext items={group.items.map((i) => i.slug)} strategy={grid ? rectSortingStrategy : verticalListSortingStrategy}>
    {children}
  </SortableContext>
);

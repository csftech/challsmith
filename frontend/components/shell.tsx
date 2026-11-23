"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";

import { Switchers } from "@/components/switchers";
import { api, logout } from "@/lib/api";

// stroke icons from the mockups
const ICON = {
  flag: <path d="M4 22V4a1 1 0 0 1 1-1h11l-2 4 2 4H5" />,
  plus: <path d="M12 5v14M5 12h14" />,
  git: <><circle cx="6" cy="6" r="2.5" /><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="8" r="2.5" /><path d="M6 8.5v7M18 10.5c0 4-6 3-11 6" /></>,
  broom: <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />,
  side: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  chev: <path d="m6 9 6 6 6-6" />,
  grip: <><circle cx="9" cy="6" r="1" /><circle cx="15" cy="6" r="1" /><circle cx="9" cy="12" r="1" /><circle cx="15" cy="12" r="1" /><circle cx="9" cy="18" r="1" /><circle cx="15" cy="18" r="1" /></>,
  edit: <path d="M4 20h4L19 9l-4-4L4 16z" />,
  up: <path d="M12 19V5M5 12l7-7 7 7" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
};
export const Icon = ({ name }: { name: keyof typeof ICON }) => (
  <svg className="i" viewBox="0 0 24 24" aria-hidden="true">{ICON[name]}</svg>
);

export function Shell({ title, search, children }: { title: string; search?: ReactNode; children: ReactNode }) {
  const t = useTranslations("nav");
  const path = usePathname();
  const [toggled, setToggled] = useState(false);
  const [user, setUser] = useState("");

  useEffect(() => {
    api<{ username: string }>("/auth/me").then((r) => setUser(r.username), () => {});
  }, []);

  const item = (href: string, icon: keyof typeof ICON, label: string) => {
    const on = href === "/" ? path === "/" || path.startsWith("/c/") : path.startsWith(href);
    return (
      <Link className={on ? "nav on" : "nav"} href={href} aria-current={on ? "page" : undefined}>
        <Icon name={icon} />{label}
      </Link>
    );
  };

  return (
    <div className={toggled ? "app toggled" : "app"}>
      {toggled && <div className="scrim" onClick={() => setToggled(false)} />}
      <aside className="side">
        <button className="ib close" aria-label={t("closeSidebar")} onClick={() => setToggled(false)}>
          <Icon name="x" />
        </button>
        <div className="brand"><span className="logo">cs</span>challsmith</div>
        <nav>
          <div className="grp">{t("groupAuthor")}</div>
          {item("/", "flag", t("challenges"))}
          {item("/new", "plus", t("new"))}
          <div className="grp">{t("groupSystem")}</div>
          {item("/sync", "git", t("sync"))}
          {item("/cleanup", "broom", t("cleanup"))}
        </nav>
        <div className="foot">
          <span className="av" aria-hidden="true">{user.slice(0, 1).toUpperCase()}</span>
          <span className="who">{user}</span>
          <button onClick={logout}>{t("logout")}</button>
        </div>
      </aside>
      <div className="main">
        <header className="top">
          <button className="ib" aria-label={t("toggleSidebar")}
            onClick={() => setToggled(!toggled)}>
            <Icon name="side" />
          </button>
          <h1 title={title}>{title}</h1>
          {search}
          <Switchers />
        </header>
        <main className="body">{children}</main>
      </div>
    </div>
  );
}

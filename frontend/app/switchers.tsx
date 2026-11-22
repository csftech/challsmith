"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { createContext, useContext, useState, type ReactNode } from "react";

import { LOCALES, THEMES } from "@/lib/prefs";

const save = (name: string, value: string) => {
  document.cookie = `${name}=${value}; path=/; max-age=31536000; samesite=lax`;
};

// The layout passes the cookie's theme down so the select is right in the server HTML too.
const ThemeCtx = createContext<string>("signal");
export const ThemeProvider = ({ theme, children }: { theme: string; children: ReactNode }) => (
  <ThemeCtx value={theme}>{children}</ThemeCtx>
);

export function Switchers() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [theme, setTheme] = useState(useContext(ThemeCtx));

  return (
    <div className="switchers">
      <select aria-label={t("common.language")} value={locale}
        onChange={(e) => { save("NEXT_LOCALE", e.target.value); router.refresh(); }}>
        {LOCALES.map((l) => <option key={l} value={l}>{t(`common.localeNames.${l}`)}</option>)}
      </select>
      <select aria-label={t("common.theme")} value={theme}
        onChange={(e) => {
          save("theme", e.target.value);
          setTheme(e.target.value);
          document.documentElement.dataset.theme = e.target.value; // repaint now, before the refresh returns
          router.refresh();
        }}>
        {THEMES.map((v) => <option key={v} value={v}>{t(`themes.${v}`)}</option>)}
      </select>
    </div>
  );
}

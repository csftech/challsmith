export const THEMES = ["signal", "zinc", "midnight", "canvas", "frost"] as const;
export type Theme = (typeof THEMES)[number];
export const pickTheme = (v: string | undefined): Theme =>
  (THEMES as readonly string[]).includes(v ?? "") ? (v as Theme) : "signal";

export const LOCALES = ["zh-TW", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const pickLocale = (v: string | undefined): Locale =>
  (LOCALES as readonly string[]).includes(v ?? "") ? (v as Locale) : "zh-TW";

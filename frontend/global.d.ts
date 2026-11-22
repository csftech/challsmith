import type messages from "./messages/zh-TW.json";
import type { Locale } from "./lib/prefs";

declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
    Messages: typeof messages;
  }
}

import { useTranslations } from "next-intl";

import { errorText } from "@/lib/api";

// errorText bound to the current locale, for client components.
export function useErrorText(): (e: unknown) => string {
  const t = useTranslations();
  // the error key is only known at run time, outside the typed message keys
  return (e) => errorText(e, (k) => t(k as never));
}

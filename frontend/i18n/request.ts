import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { pickLocale } from "@/lib/prefs";

// No URL prefix: the locale comes only from the NEXT_LOCALE cookie.
export default getRequestConfig(async () => {
  const locale = pickLocale((await cookies()).get("NEXT_LOCALE")?.value);
  return { locale, messages: (await import(`../messages/${locale}.json`)).default };
});

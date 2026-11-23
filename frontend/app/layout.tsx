import type { Metadata } from "next";
import { cookies } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";

import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/noto-sans-tc/400.css";
import "@fontsource/noto-sans-tc/500.css";
import "@fontsource/noto-sans-tc/600.css";
import "@fontsource/noto-sans-tc/700.css";
import "./themes.css";
import "./globals.css";
import { ThemeProvider } from "@/components/switchers";
import { pickTheme } from "@/lib/prefs";

export const metadata: Metadata = { title: "challsmith" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // theme and locale are both rendered on the server, so the first paint is already right
  const theme = pickTheme((await cookies()).get("theme")?.value);
  const locale = await getLocale(); // i18n/request.ts: pickLocale(NEXT_LOCALE cookie)
  return (
    <html lang={locale} data-theme={theme}>
      <body>
        <NextIntlClientProvider>
          <ThemeProvider theme={theme}>{children}</ThemeProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

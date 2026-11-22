import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { COOKIE } from "@/lib/bff";

// Pages need a session cookie; /api/* answers 401 itself (route handlers).
export function proxy(req: NextRequest) {
  const p = req.nextUrl.pathname;
  if (p === "/login" || p.startsWith("/api/") || req.cookies.has(COOKIE)) return NextResponse.next();
  // build the URL from Host: req.url would carry the 0.0.0.0 bind address
  return NextResponse.redirect(new URL("/login", `http://${req.headers.get("host")}`), 307);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
